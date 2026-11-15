# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/). La versión se define en un solo lugar:
`backend/anonymizer/__init__.py` (`__version__`).

## [Unreleased]

### Añadido
- Integración continua (GitHub Actions): `ruff`, `mypy`, `pytest` con cobertura mínima del 70 %
  en Python 3.10, 3.12 y 3.13, build del frontend y build de Windows con PyInstaller.
- Autoprueba del ejecutable sin ventana: `AnonimizeMedical.exe --self-test --self-test-report informe.json`.
- Información de versión de Windows en el `.exe`, inyectada desde `__version__`.
- Pruebas de regresión con *golden files* (`tests/golden/`).
- `CHANGELOG.md` y configuración centralizada en `pyproject.toml`.

### Añadido (lotes en paralelo)
- Extracción de PDF y OCR en paralelo con procesos (`ProcessPoolExecutor`, contexto *spawn*):
  hasta ×2,8 más rápido con 3 procesos en lotes escaneados. Límite configurable en la interfaz
  («Procesos en paralelo», por defecto `min(4, núcleos − 1)`); los archivos empiezan en el orden
  de la cola.
- Cancelación inmediata: un documento en curso se abandona en la página siguiente (también en
  modo secuencial). Tiempo restante estimado (ponderado por tamaño) y archivos en curso en la UI.
- Recuperación: si un proceso muere, sus archivos se reprocesan y el pool se recrea; si los
  procesos no pueden arrancar, el lote sigue en modo secuencial.
- Los procesos hijos aplican el bloqueo de red y el logging seguro; la autoprueba del `.exe`
  verifica el paralelismo (`freeze_support`).

### Cambiado
- **Sin descargas después del build:** el proceso bloquea toda conexión no local (audit hook de
  Python, proxies anulados) y a RapidOCR se le pasan siempre las rutas de los modelos empaquetados
  (antes los descargaba de internet si faltaban). La autoprueba lo verifica.
- **Variantes de build explícitas:** RapidOCR sólo se incluye con `build.bat --ocr`
  (`BUNDLE_RAPIDOCR=1`); el build base lo excluye aunque esté instalado. El CI compila y prueba
  las variantes base, ocr y tesseract, con OCR real sin conexión.
- **Rendimiento:** la propagación de nombres, apellidos, términos personalizados e
  identificadores usa Aho-Corasick (`pyahocorasick`, BSD-3-Clause, ~115 KB) cuando hay 100 o
  más valores: ×12,9 más rápido con 2 000 pacientes (12,9 s → 1,0 s), sin cambios con pocos
  valores y con salida idéntica. Si falta la dependencia se usa la regex anterior.
  Benchmark: `scripts/bench.py`, resultados en `docs/benchmarks.md`.
- **Privacidad:** el OCR con Tesseract envía la imagen por stdin y lee el texto por stdout, sin
  archivos temporales (antes `pytesseract` escribía la página en `%TEMP%`). Se elimina la
  dependencia `pytesseract`.
- **Privacidad:** los logs ya no incluyen nombres de archivo ni mensajes de excepción (sólo el
  tipo y la pila); las librerías que leen el PDF quedan en WARNING incluso en modo desarrollo.
- **Privacidad:** los «términos adicionales a ocultar» ya no se guardan entre sesiones.
- `--dev` (DevTools) se ignora en el ejecutable distribuido.
- README: secciones de privacidad, limitaciones y matriz de identificadores por país.

### Corregido
- Una dirección IP al final de una oración («ref 10.0.12.7.») no se detectaba.
- Con «Ocultar cualquier número largo» activo, un dato reconocido (p. ej. el N° de ficha) se
  marcaba como `[NUMERO]` en lugar de con su marcador específico.

## [1.0.0] - 2026-11-15

### Añadido
- Aplicación de escritorio (PyWebView + React/Tailwind) para anonimizar documentos médicos en
  español e inglés, con salida Markdown o texto plano.
- Detección por etiquetas y patrones, propagación de nombres insensible a tildes.
- Documentos de identidad por país/región con validación de dígito verificador, MRZ y palabras clave.
- Procesamiento por lotes en segundo plano, OCR local (Tesseract / RapidOCR), exportación a
  Markdown, texto, Word y JSON, y lista de excepciones.
- Licencia MIT.
