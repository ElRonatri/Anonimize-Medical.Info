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
| Entrada | PDF (arrastrar y soltar o diálogo nativo), TXT, o texto pegado |
| Salida | Markdown (títulos, listas, tablas de laboratorio) o texto plano; copiar o guardar `.md`/`.txt` |
| Datos detectados | nombre del paciente, familiares y contactos, RUT/RUN, DNI, NIE, CURP, cédula, SSN, pasaporte, N° de ficha / historia clínica / MRN, fecha de nacimiento, teléfonos, correos, direcciones y localidades, URLs, IPs |
| Opcional | nombres de profesionales (médicos, firmantes), todas las fechas, términos personalizados |
| Por país (opcional) | selector de región/país: formatos validados con dígito verificador (RUN/RUT, CUIL, CPF, CNS, CURP, RFC, CI de Venezuela/Uruguay/Ecuador, SSN, MBI, SIN, DNI/NIE, NIR, Codice Fiscale, NINO, NHS, personnummer, HETU, AHV, Aadhaar, PAN, ID china, RRN, NRIC, HKID, CNIC, Emirates ID), pasaportes MRZ y más de 150 palabras clave de documentos de todo el mundo |
| Números largos (opcional) | oculta cualquier secuencia de 7+ dígitos, respetando fechas |
| Marcadores | numerados y consistentes (`[PACIENTE_1]`, `[PERSONA_2]`) o genéricos (`[PACIENTE]`) |
| Revisión | lista de datos detectados (valores originales ocultos por defecto); marca falsos positivos para no anonimizarlos; edición manual del resultado |
| Limpieza | elimina encabezados/pies de página repetidos y números de página |
| OCR | opcional, para PDFs escaneados (RapidOCR + ONNX, sin conexión) |

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

## Requisitos (para compilar)

- Windows 10/11 con **Microsoft Edge WebView2 Runtime** (incluido en Windows 11 y en Windows 10 actualizado).
- **Python 3.10+** y **Node.js 18+** en el `PATH`.

## Generar el ejecutable

```bat
build.bat          :: sin OCR
build.bat --ocr    :: incluye OCR para PDFs escaneados (~100 MB más)
```

El resultado queda en `dist\AnonimizeMedical\AnonimizeMedical.exe` (carpeta portable: puedes
comprimirla y copiarla a otro equipo).

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

## Pruebas

```bat
pip install -r requirements-dev.txt
pytest
python scripts\make_samples.py samples   :: genera PDFs de ejemplo con datos ficticios
```

## Estructura

```
backend/
  main.py               ventana PyWebView
  api.py                API expuesta a JavaScript (window.pywebview.api)
  anonymizer/
    extract.py          PDF/TXT -> líneas y tablas (pdfplumber), OCR opcional
    rules.py            etiquetas ES/EN y patrones de identificadores
    identifiers.py      documentos por país (validadores, palabras clave, capa agresiva)
    detector.py         detección, propagación de nombres y reemplazo
    render.py           salida Markdown / texto, limpieza de encabezados
    pipeline.py         orquestación
    lang.py             marcadores por idioma y detección de idioma
frontend/               React + Tailwind (Vite)
tests/                  pruebas (pytest)
scripts/make_samples.py PDFs de ejemplo ficticios
anonimize.spec          configuración de PyInstaller
build.bat / run.bat / run-dev.bat
```

### Agregar otro idioma

1. Interfaz: agrega un bloque de traducciones en `frontend/src/i18n.jsx` y su entrada en `UI_LANGUAGES`.
2. Motor: agrega los marcadores en `backend/anonymizer/lang.py` (`PLACEHOLDERS`, `PAGE_LABEL`,
   palabras frecuentes para la detección) y las etiquetas del idioma en `backend/anonymizer/rules.py`.

---

## English summary

Windows desktop app (Python + React/Tailwind via PyWebView) that reads medical documents (PDF/TXT),
de-identifies patient data (names, IDs, record numbers, birth dates, contact info, addresses) in
Spanish and English documents, and returns Markdown or plain text ready to copy. Everything runs
locally. Build with `build.bat` (add `--ocr` for scanned PDFs). Always review the output before sharing.
