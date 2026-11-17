# Qué deja la aplicación en el disco

Resumen: **durante el uso**, el texto de los documentos vive en la memoria del proceso y, mientras la
ventana está abierta, en el perfil temporal de WebView2. **Después de cerrar**, en el equipo quedan
sólo las preferencias (`prefs.json`) y los archivos que el usuario exportó. Esto se verifica en el
CI de Windows con el ejecutable real (ver [Verificación](#verificación)).

## Lo que escribe la aplicación

| Qué | Dónde (Windows) | Contenido | Al cerrar |
|---|---|---|---|
| Preferencias | `%APPDATA%\AnonimizeMedical\prefs.json` | idioma, tema, opciones, lista de excepciones, «no volver a mostrar» el aviso | se conserva |
| Perfil de WebView2 | `%LOCALAPPDATA%\AnonimizeMedical\WebView2` | lo que el motor de la ventana necesite (caché, Local Storage, IndexedDB, Service Workers, Crashpad) | **se borra**; si quedó tras un fallo, se borra al iniciar |
| Exportaciones | donde el usuario elija | texto anonimizado | del usuario |

Nada más: no hay archivos temporales ni de log (una prueba revisa que el backend no use
`tempfile` ni manejadores de log a archivo).

### Preferencias: sólo lo permitido

`prefs.json` lo escribe el backend (`backend/appdata.py`), que valida cada clave y su tipo contra una
lista cerrada: `uiLanguage` (`es`/`en`), `theme` (`light`/`dark`), `exportGeneric`,
`responsibleUseDismissed` (booleanos) y `options` (opciones conocidas: códigos cortos, booleanos,
números y la lista de excepciones). **Cualquier otra clave o valor se descarta**, aunque la interfaz
lo enviara por error; un archivo manipulado a mano también se filtra al leerlo. Los *términos
adicionales a ocultar* (suelen ser nombres de pacientes) nunca se envían.

La lista de excepciones contiene términos que el usuario decidió **no** ocultar (p. ej. «Hospital
Regional»); por definición no son datos del paciente, pero conviene no escribir ahí nombres.

### Perfil de WebView2

La ventana usa Microsoft Edge WebView2. Antes de este cambio, PyWebView guardaba un perfil
persistente en `%APPDATA%\pywebview` (carpeta genérica, compartida con cualquier otra aplicación
hecha con PyWebView) con caché, Local Storage y, si el motor fallaba, volcados de Crashpad que
pueden contener la página, es decir, texto clínico. Ahora:

- `webview.start(private_mode=True, storage_path=<perfil propio>)`: modo *InPrivate*, sin caché ni
  almacenamiento persistentes, en una carpeta propia;
- la carpeta se borra al cerrar (PyWebView y, además, la aplicación con reintentos) y también **al
  iniciar**, por si un cierre abrupto (corte de luz, proceso terminado) dejó restos;
- el navegador de WebView2 se inicia con `--disable-breakpad --disable-crash-reporter`
  (variable `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`);
- el proceso de Python llama a `WerSetFlags(WER_FAULT_REPORTING_FLAG_NOHEAP)`: si falla, el
  informe de Windows Error Reporting no incluye el *heap* (donde están los textos). Sólo afecta a
  este proceso; no cambia la configuración del sistema.

Como el modo privado no conserva `localStorage`, las preferencias pasaron al backend (arriba).

### Otros posibles rastros revisados

| Rastro | Resultado |
|---|---|
| `_MEI*` de PyInstaller en `%TEMP%` | No existe: el ejecutable es *onedir* (no se descomprime). Prueba: `test_build_is_onedir_without_temp_extraction`. |
| OCR con Tesseract | Imagen por la entrada estándar, texto por la salida estándar: sin archivos. |
| OCR con RapidOCR | En memoria. |
| PDF de entrada | Se leen en memoria (los arrastrados a la ventana llegan como datos, no se copian a disco). |
| Procesos en paralelo (*spawn*) | Reciben los datos por tuberías de `multiprocessing`; sin archivos. **Hallazgo de la sonda en el CI:** si el proceso principal moría de golpe, los procesos de extracción quedaban vivos (con documentos en memoria). Ahora cada uno vigila al principal y termina con él (`parallel.watch_parent`); prueba con control negativo en `tests/test_parallel.py` y verificación en el CI de Windows. |
| Exportación DOCX/JSON | Se genera en memoria y se escribe sólo en el destino elegido. |
| Logs | Sólo a la consola (el `.exe` no tiene) y sin contenido clínico: tipo de error y línea. |
| Volcados de Python | No se usa `faulthandler`; WER sin heap (arriba). |

## Fuera del control de la aplicación

Comportamiento de Windows o del usuario, que la aplicación no puede evitar:

- **Portapapeles e historial del portapapeles** (`Win + V`) y su sincronización entre dispositivos:
  el texto copiado (ya anonimizado) queda ahí.
- **Archivos exportados**, y su nombre: el nombre sugerido deriva del archivo original, que a
  veces incluye el nombre del paciente. Al exportar varios, usa los nombres genéricos.
- **Archivos recientes / MRU**: los diálogos «Abrir» y «Guardar como» de Windows registran las
  últimas rutas y nombres usados (registro `ComDlg32`, «Acceso rápido» del Explorador).
- **Archivo de paginación** (`pagefile.sys`) e **hibernación** (`hiberfil.sys`): Windows puede llevar
  memoria del proceso a disco.
- **Volcados y diagnósticos del sistema** según la configuración de Windows Error Reporting y de
  datos de diagnóstico de la organización.
- **Copias de seguridad, antivirus o indexación** que capturen los archivos de origen o exportados.

### Recomendaciones

- Desactiva el **historial del portapapeles** (Configuración → Sistema → Portapapeles) mientras
  trabajas con datos sensibles, o bórralo al terminar (`Win + V` → «Borrar todo»).
- Guarda las exportaciones en una carpeta cifrada (BitLocker) y bórralas cuando ya no se usen.
- Usa **nombres genéricos** al exportar varios documentos y evita nombres de archivo con datos
  del paciente.
- Si la política lo exige: cifrado de disco completo (cubre paginación e hibernación) y limpieza de
  «Acceso rápido» / archivos recientes.

## Verificación

**Automática en cada build de Windows** (`.github/workflows/build-windows.yml`, paso «Privacidad en
disco»), con el ejecutable congelado de cada variante y la ventana real de WebView2:

1. Genera un nombre centinela único (`Zxqwerty Centinela <azar>`), sin escribirlo en ningún archivo.
2. **Control positivo**: escribe otro centinela en UTF-16 y comprueba que el escáner lo encuentra.
3. Ejecuta `AnonimizeMedical.exe --privacy-probe ... --probe-crash`: maneja la interfaz real y
   termina de golpe (simula un fallo), dejando el perfil de WebView2.
4. Vuelve a ejecutarla sin `--probe-crash`. La sonda (`backend/privacy_probe.py`):
   acepta el aviso, cambia el tema (escribe `prefs.json`), pega un texto clínico sintético con el
   centinela, lo anonimiza y copia; procesa dos PDF escaneados sintéticos por **OCR en procesos
   paralelos**; exporta md/txt/docx/json, y cierra la ventana. Mientras corre, el CI registra las
   líneas de comando de los procesos `msedgewebview2.exe` (perfil usado, argumentos de fallos).
5. Tras el cierre abrupto exige que **no quede ningún proceso `AnonimizeMedical` vivo**. La sonda
   tiene un plazo máximo (`--probe-deadline`) e informa en qué etapa quedó si algo se cuelga.
6. Exige: resultados y exportaciones sin el centinela, perfil borrado al cerrar, y **ningún
   archivo con el centinela** (UTF-8 o UTF-16, mayúsculas o minúsculas) en `%TEMP%`,
   `%LOCALAPPDATA%` y `%APPDATA%` (archivos modificados desde el inicio de la prueba) ni en las
   carpetas de la aplicación (completas). El informe de la sonda nunca incluye el centinela.

**Alcance real**: la prueba cubre lo que la aplicación escribe en las carpetas del usuario durante
una sesión típica y tras un cierre abrupto. No cubre: los diálogos de archivo de Windows (no se
abren en el CI; las exportaciones se escriben como lo haría «Guardar como»), el portapapeles, el
archivo de paginación ni carpetas del sistema fuera del perfil del usuario.

**Pruebas unitarias** (`tests/test_disk_privacy.py`): validación de `prefs.json`, limpieza del perfil
(también si la ventana falla), argumentos de WebView2, WER sin heap, ausencia de temporales y logs a
archivo, y la sonda completa con la API real (OCR incluido) y una ventana simulada.
