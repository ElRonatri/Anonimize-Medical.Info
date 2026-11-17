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
- el navegador de WebView2 se inicia con `--disable-breakpad --disable-crash-reporter`. pywebview
  fija sus propios argumentos y la variable `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` no surtía
  efecto (lo mostró la sonda); se añaden a las propiedades de creación antes de que WebView2 las
  lea (`appdata.harden_edgechromium`). **Aun así, el runtime de WebView2 lanza su proceso
  `crashpad-handler`**: si el motor fallara, un volcado podría escribirse en
  `...\WebView2\EBWebView\Crashpad`, que se borra al cerrar o al volver a abrir la aplicación;
  su envío a Microsoft depende de la configuración de datos de diagnóstico de Windows;
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

## Evidencia del CI de Windows

Ejecución [43994290624](https://github.com/ElRonatri/Anonimize-Medical.Info/actions/runs/43994290624)
(commit `3eb01cb`), paso «Privacidad en disco» en las cuatro variantes (base, ocr, tesseract, ner),
con el `.exe` congelado y la ventana real de WebView2 en `windows-latest`:

| Comprobación | Resultado |
|---|---|
| Control positivo del escáner (centinela escrito a propósito en UTF-16) | encontrado ✔ (el escáner funciona) |
| Flujo real en la ventana: aviso → pegar texto con el centinela → anonimizar → copiar | ✔; el centinela no aparece en el resultado |
| OCR en procesos paralelos (variante ocr: RapidOCR; tesseract: Tesseract) | leyó el centinela ✔; salida anonimizada ✔ (en base/ner no hay motor OCR) |
| Exportaciones md/txt/docx/json | sin el centinela ✔ |
| Perfil de WebView2 durante el uso | 186 archivos, con Crashpad y Local Storage |
| Perfil al cerrar | borrado ✔ |
| Cierre abrupto simulado | el perfil queda → la siguiente ejecución lo borra ✔ |
| Procesos `AnonimizeMedical` vivos tras el cierre abrupto | 0 ✔ (antes de la corrección quedaban 2 y el paso se colgó 6 h) |
| Línea de comandos del navegador | `--user-data-dir=...\AnonimizeMedical\WebView2\EBWebView --disable-breakpad --disable-crash-reporter ...` ✔ |
| Proceso `crashpad-handler` | **sigue presente (1)**: lo lanza el runtime de WebView2 |
| Centinela en `%TEMP%`, `%LOCALAPPDATA%`, `%APPDATA%` (UTF-8/UTF-16) | **no encontrado** ✔ |
| Archivos de la aplicación tras cerrar | sólo `%APPDATA%\AnonimizeMedical\prefs.json` (586 bytes; claves: exportGeneric, options, responsibleUseDismissed, theme, uiLanguage) |

**Sólo documentado (no verificable en el CI):** portapapeles e historial (`Win + V`), archivos
recientes / MRU de los diálogos de Windows (el CI no los abre), archivo de paginación e
hibernación, nombres de archivos exportados, y el contenido de un volcado de Crashpad ante un
fallo real del motor (no se provoca en la prueba).
