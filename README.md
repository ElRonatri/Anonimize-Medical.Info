# Anonimize Medical

Aplicación de escritorio para **Windows** que lee documentos médicos (historias clínicas, exámenes,
epicrisis, informes, etc.), **anonimiza los datos del paciente** y devuelve el resultado en
**Markdown o texto plano** listo para copiar.

- **Backend:** Python (extracción de PDF y anonimización), sin servicios externos.
- **Interfaz:** React + Tailwind CSS, mostrada en una ventana nativa con [PyWebView](https://pywebview.flowrl.com/)
  (Edge WebView2 en Windows).
- **Idiomas:** español e inglés, tanto en la interfaz como en la detección de datos.
- **Privacidad:** todo se procesa localmente. No se guarda contenido clínico en disco salvo que
  uses el botón *Guardar*.

## Funciones

| | |
|---|---|
| Entrada | **varios PDF a la vez** (arrastrar y soltar o diálogo nativo), TXT, o texto pegado. Se procesan en cola y **en paralelo** (procesos configurables), con avance por archivo y página, tiempo restante estimado y cancelación inmediata |
| Salida | Markdown (títulos, listas, tablas de laboratorio) o texto plano; copiar o **exportar a `.md`, `.txt`, Word `.docx` o `.json`**, un documento o todos a una carpeta (con nombres genéricos opcionales) |
| Datos detectados | nombre del paciente, familiares y contactos, RUT/RUN, DNI, NIE, CURP, cédula, SSN, pasaporte, N° de ficha / historia clínica / MRN, fecha de nacimiento, teléfonos, correos, direcciones y localidades, URLs, IPs |
| Opcional | nombres de profesionales (médicos, firmantes), todas las fechas, términos personalizados a ocultar |
| Excepciones | lista de términos que **nunca** se anonimizan (instituciones, fármacos, palabras ocultadas por error) |
| Por país (opcional) | selector de región/país: formatos validados con dígito verificador (RUN/RUT, CUIL, CPF, CNS, CURP, RFC, CI de Venezuela/Uruguay/Ecuador, SSN, MBI, SIN, DNI/NIE, NIR, Codice Fiscale, NINO, NHS, personnummer, HETU, AHV, Aadhaar, PAN, ID china, RRN, NRIC, HKID, CNIC, Emirates ID), pasaportes MRZ y más de 150 palabras clave de documentos de todo el mundo |
| Números largos (opcional) | oculta cualquier secuencia de 7+ dígitos, respetando fechas |
| Marcadores | numerados y consistentes (`[PACIENTE_1]`, `[PERSONA_2]`) o genéricos (`[PACIENTE]`) |
| Revisión | lista de datos detectados (valores originales ocultos por defecto); marca falsos positivos para no anonimizarlos; edición manual del resultado |
| Limpieza | elimina encabezados/pies de página repetidos y números de página |
| OCR | PDFs escaneados o basados en imágenes, 100% sin conexión: **Tesseract** (español + inglés, invocado sin archivos temporales) o **RapidOCR** (ONNX). Modo automático (sólo páginas escaneadas), todas las páginas o desactivado |
| Rendimiento | expresiones regulares precompiladas y combinadas, y Aho-Corasick para propagar cientos o miles de nombres en una sola pasada; ~2 ms para una epicrisis de 2 páginas, ~1 s para 1,3 millones de caracteres o un registro de 2 000 pacientes ([benchmarks](docs/benchmarks.md)) |

### Cómo detecta los datos

1. **Etiquetas** en español e inglés (`Nombre:`, `Paciente:`, `RUT:`, `Ficha clínica N°`,
   `Fecha de nacimiento:`, `Patient Name:`, `MRN:`, `DOB:`, `Address:`, …), también dentro de tablas.
2. **Patrones** de identificadores (RUT con dígito verificador, SSN, DNI/NIE, CURP, teléfonos
   internacionales, correos, direcciones tipo *Av. Los Leones 1234* o *88 Oak Street*).
3. **Propagación:** cada nombre o apellido encontrado se busca en todo el documento, sin
   importar tildes ni mayúsculas (`PÉREZ`, `Perez`, `Sr. Pérez`), sólo cuando aparece con
   mayúscula inicial para no tocar palabras comunes (*rosa*, *blanco*).
4. **Por país (opcional):** al elegir un país o región se activan sus formatos estructurales
   (validados con dígito verificador, sin necesidad de etiqueta) y la detección por palabra
   clave (`CC 1020304050`, `PESEL 44051401359`, `Pasaporte N° AB1234567`). Ver
   `backend/anonymizer/identifiers.py`.
5. Los valores clínicos (resultados de laboratorio, signos vitales, dosis, fechas de atención) se
   conservan.

> ⚠️ La detección es automática y basada en reglas: **revisa siempre el resultado antes de
> compartirlo**. Usa *Términos adicionales a ocultar* para lo que no se haya detectado.

### Identificadores por país

Al elegir un país o región se activan sus formatos **estructurales** (se reconocen sin etiqueta).
✓ = se valida el dígito verificador; los demás se reconocen sólo por su estructura. En todos los
casos se activan además los pasaportes (zona MRZ, validada con ICAO 9303) y más de 150 palabras
clave (`CC 1020304050`, `PESEL 44051401359`, `Pasaporte N° AB1234567`…).

| Región | País | Formatos estructurales |
|---|---|---|
| Latinoamérica | Chile | RUN/RUT ✓ |
| | Argentina | CUIL/CUIT ✓, DNI con puntos |
| | Brasil | CPF ✓, Cartão Nacional de Saúde (CNS) ✓ |
| | México | CURP, RFC |
| | Venezuela | Cédula V-/E-, RIF |
| | Uruguay | Cédula de Identidad ✓ |
| | Ecuador | Cédula de Identidad ✓ |
| | Bolivia, Colombia, Costa Rica, Paraguay, Perú | sólo palabras clave (CI, CC, DNI, DIMEX…) |
| Norteamérica | EE. UU. | SSN (con rangos inválidos excluidos), Medicare MBI |
| | Canadá | SIN ✓ (Luhn) |
| Europa | España | DNI/NIF ✓, NIE ✓ |
| | Francia | NIR ✓ |
| | Italia | Codice Fiscale |
| | Reino Unido | National Insurance Number, NHS Number ✓ |
| | Suecia, Dinamarca, Noruega | Personnummer / CPR |
| | Finlandia | Henkilötunnus ✓ |
| | Suiza, Liechtenstein | AHV/AVS |
| | Alemania, Irlanda, Países Bajos, Polonia, Portugal | sólo palabras clave (Steuer-ID, PPSN, BSN, PESEL, NIF…) |
| Asia y Medio Oriente | China | Resident Identity Card ✓ |
| | India | Aadhaar ✓ (Verhoeff), PAN |
| | Corea del Sur | Resident Registration Number |
| | Singapur | NRIC/FIN |
| | Hong Kong | HKID |
| | Pakistán | CNIC |
| | Emiratos Árabes Unidos | Emirates ID ✓ (Luhn) |
| | Japón | sólo palabras clave (My Number) |

Sin región elegida («General») se usan las etiquetas y los formatos comunes (RUT, SSN, DNI/NIE,
CURP), sin validación de dígito verificador.

## Privacidad

Garantías del diseño, verificadas por pruebas automáticas (`tests/test_privacy.py`):

- **Todo es local y sin descargas.** No hay llamadas de red ni servicios externos, y **nada se
  descarga después del build** (ni modelos, ni paquetes, ni actualizaciones): todo lo que usa la
  aplicación va dentro del ejecutable. Se garantiza por partida doble:
  - el proceso de Python **bloquea cualquier conexión que no sea local** (un *audit hook* de
    Python que no se puede desactivar). También se anulan los proxies, para que el tráfico no
    pueda salir a través de un proxy local o del configurado en Windows;
  - a RapidOCR (que por diseño descargaría los modelos que le falten) se le pasan siempre las
    rutas de los modelos empaquetados; si falta alguno, el motor se desactiva.

  La interfaz se sirve desde un servidor interno de PyWebView en `127.0.0.1` que sólo entrega
  los archivos de la propia interfaz. La autoprueba del ejecutable verifica el bloqueo de red.
- **Sin archivos temporales.** Los PDF se leen en memoria. El OCR con Tesseract recibe la imagen
  por la entrada estándar y devuelve el texto por la salida estándar; RapidOCR trabaja en memoria.
  Lo único que se escribe en disco son las exportaciones que el usuario guarda.
- **Logs sin contenido clínico.** Nunca se registran textos, valores detectados ni nombres de
  archivo (suelen contener el nombre del paciente). De los errores sólo se guarda el tipo y la
  línea de código, no el mensaje. Las librerías que leen el PDF quedan en nivel WARNING incluso en
  modo desarrollo. El ejecutable no tiene consola ni archivo de log.
- **Memoria.** Los documentos cargados permanecen en RAM mientras la aplicación está abierta (para
  re-anonimizar al cambiar opciones) y se liberan al quitarlos de la lista o cerrar la aplicación.
- **Preferencias.** Idioma, tema, opciones y la lista de excepciones se guardan en el perfil de
  WebView2 del usuario. Los *términos adicionales a ocultar* **no** se guardan: duran la sesión.
- **Herramientas de desarrollo.** DevTools y el menú «Inspeccionar» sólo existen al ejecutar desde el
  código con `run-dev.bat`; en el `.exe`, `--dev` se ignora.
- **Exportaciones.** El JSON no incluye los valores originales detectados. Al exportar varios
  documentos se puede usar nombres genéricos (`documento_01…`) para no revelar el nombre del paciente.

### Limitaciones

- **Es una herramienta de apoyo, no una garantía de anonimización legal** (p. ej. HIPAA *Safe
  Harbor* o RGPD). Por diseño se conservan datos clínicos útiles (edad, sexo, fechas de atención,
  diagnósticos) que, combinados, pueden permitir reidentificar a una persona en casos raros.
- La detección se basa en reglas: no reconoce nombres sin etiqueta ni tratamiento («Juan consultó…»
  sólo se oculta si «Juan» apareció antes como nombre del paciente), apodos ni nombres en minúscula.
- La propagación de nombres puede ocultar instituciones que comparten una palabra con un nombre
  («Clínica Santa **Rosa**» si un familiar se llama Rosa). Para eso está la lista de excepciones.
- El OCR puede leer mal números y nombres; revisa con más cuidado las páginas escaneadas.
- Texto dentro de imágenes de un PDF con texto seleccionable (logos, firmas escaneadas) sólo se
  procesa con el OCR en modo «Todas las páginas».
- El texto copiado queda en el portapapeles de Windows (y en su historial, si está activado).

## Requisitos (para compilar)

- Windows 10/11 con **Microsoft Edge WebView2 Runtime** (incluido en Windows 11 y en Windows 10 actualizado).
- **Python 3.10+** y **Node.js 18+** en el `PATH`.

## Generar el ejecutable

```bat
build.bat                :: base (usa Tesseract si está instalado en el equipo)
build.bat --ocr          :: incluye el motor RapidOCR dentro del ejecutable (~100 MB más)
build.bat --tesseract    :: copia Tesseract instalado dentro del ejecutable (portable)
```

### Variantes de build

Regla del proyecto: **todo motor que aumente el tamaño del ejecutable es una variante opcional**
y se activa explícitamente; el build base nunca lo incluye, aunque esté instalado en el entorno.
Las opciones se pueden combinar (`build.bat --ocr --tesseract`).

| Variante | Comando | Incluye | OCR sin instalar nada más | Tamaño* |
|---|---|---|---|---:|
| base | `build.bat` | motor de anonimización, exportación | no (usa Tesseract si el equipo lo tiene) | 73 MB |
| ocr | `build.bat --ocr` | + RapidOCR con sus modelos ONNX | sí | 293 MB |
| tesseract | `build.bat --tesseract` | + Tesseract portable (con los idiomas instalados) | sí | 275 MB |

\* Carpeta `dist\AnonimizeMedical` sin comprimir, medida por el CI en Windows (la variante
tesseract con los idiomas que trae el instalador de Chocolatey; varía según los idiomas incluidos).

El CI compila y prueba las tres variantes en Windows (la autoprueba exige que el OCR de la
variante funcione sin conexión) e informa el tamaño de cada una.

El resultado queda en `dist\AnonimizeMedical\AnonimizeMedical.exe` (carpeta portable: puedes
comprimirla y copiarla a otro equipo).

### Descargas, verificación y firma

Cada release (tags `vX.Y.Z`) publica las tres variantes como ZIP con `SHA256SUMS.txt`. Para
verificar una descarga: `Get-FileHash <archivo> -Algorithm SHA256` en PowerShell y compararlo con
`SHA256SUMS.txt`. Proceso completo en [docs/release.md](docs/release.md). El ejecutable aún no
está firmado con Authenticode; cómo activarlo: [docs/signing.md](docs/signing.md).

### OCR con Tesseract en Windows

1. Instala Tesseract desde [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) y marca los
   idiomas **Spanish** e **English** durante la instalación.
2. La aplicación lo detecta sola en `C:\Program Files\Tesseract-OCR` (o en `TESSERACT_CMD` / el `PATH`).
3. Para distribuir el ejecutable a equipos sin Tesseract, compila con `build.bat --tesseract`.

Si no hay ningún motor OCR, las páginas escaneadas se marcan como «sin texto extraíble».

## Ejecutar desde el código fuente

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python backend\main.py
```

O simplemente `run.bat`.

### Modo desarrollo (recarga en caliente)

```bat
run-dev.bat
```

Levanta Vite en `http://localhost:5173` y abre la ventana de PyWebView apuntando a él, con DevTools.

## Pruebas y calidad

```bat
pip install -r requirements-dev.txt
ruff check backend tests scripts          :: lint
mypy                                      :: tipos (configuración en pyproject.toml)
pytest --cov                              :: pruebas + cobertura (mínimo 70 %)
python scripts\make_samples.py samples   :: genera PDFs de ejemplo con datos ficticios
```

- **Golden files** (`tests/golden/`): la salida esperada de documentos ficticios. Si un cambio de
  comportamiento es intencional, regenera con `UPDATE_GOLDEN=1 pytest tests/test_golden.py` y revisa el diff.
- **Autoprueba del ejecutable:** `AnonimizeMedical.exe --self-test --self-test-report informe.json`
  verifica el motor, las exportaciones y la interfaz empaquetada sin abrir la ventana.
- **CI** (`.github/workflows/ci.yml`): lint, tipos, pruebas en Python 3.10/3.12/3.13, build del
  frontend y build de Windows con autoprueba en cada push y pull request.

## Estructura

```
backend/
  main.py               ventana PyWebView
  api.py                API para JavaScript (window.pywebview.api): cola de lotes en hilo secundario
  anonymizer/
    extract.py          PDF/TXT -> líneas y tablas (pdfplumber), OCR por página con progreso
    ocr.py              motores OCR locales (Tesseract / RapidOCR)
    exporters.py        exportación a Markdown, texto, Word (.docx) y JSON
    rules.py            etiquetas ES/EN y patrones de identificadores
    identifiers.py      documentos por país (validadores, palabras clave, capa agresiva)
    detector.py         detección, propagación de nombres y reemplazo
    render.py           salida Markdown / texto, limpieza de encabezados
    pipeline.py         orquestación
    lang.py             marcadores por idioma y detección de idioma
    privacy.py          logging sin contenido clínico
    fastmatch.py        búsqueda de muchos valores en una pasada (Aho-Corasick)
    parallel.py         extracción en procesos paralelos (progreso, cancelación)
frontend/               React + Tailwind (Vite)
tests/                  pruebas (pytest); fixtures/ y golden/ para regresión
.github/workflows/      CI
scripts/make_samples.py PDFs de ejemplo ficticios
scripts/bench.py        benchmark del motor (docs/benchmarks.md)
scripts/bench_batch.py  benchmark de lotes en paralelo
anonimize.spec          configuración de PyInstaller
build.bat / run.bat / run-dev.bat
```

### Agregar otro idioma

1. Interfaz: agrega un bloque de traducciones en `frontend/src/i18n.jsx` y su entrada en `UI_LANGUAGES`.
2. Motor: agrega los marcadores en `backend/anonymizer/lang.py` (`PLACEHOLDERS`, `PAGE_LABEL`,
   palabras frecuentes para la detección) y las etiquetas del idioma en `backend/anonymizer/rules.py`.

## Licencia

Distribuido bajo la licencia [MIT](LICENSE). Se entrega «tal cual», sin garantías: la anonimización
automática puede omitir datos y el resultado siempre debe revisarse antes de compartirlo.

Los componentes de terceros que se incluyen en el ejecutable mantienen sus propias licencias
(pdfplumber: MIT; pywebview: BSD-3-Clause; python-docx: MIT; Tesseract y RapidOCR: Apache-2.0).

---

## English summary

Windows desktop app (Python + React/Tailwind via PyWebView) that reads medical documents (PDF/TXT),
de-identifies patient data (names, IDs, record numbers, birth dates, contact info, addresses) in
Spanish and English documents, and returns Markdown or plain text ready to copy. Everything runs
locally. Supports batch processing, offline OCR (Tesseract or RapidOCR), export to Markdown, text, Word and
JSON, and an exceptions list. Build with `build.bat` (`--ocr` / `--tesseract` to bundle OCR). Always review
the output before sharing.

Licensed under the [MIT License](LICENSE).
