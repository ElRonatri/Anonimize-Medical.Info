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

## [1.0.0] - 2026-11-15

### Añadido
- Aplicación de escritorio (PyWebView + React/Tailwind) para anonimizar documentos médicos en
  español e inglés, con salida Markdown o texto plano.
- Detección por etiquetas y patrones, propagación de nombres insensible a tildes.
- Documentos de identidad por país/región con validación de dígito verificador, MRZ y palabras clave.
- Procesamiento por lotes en segundo plano, OCR local (Tesseract / RapidOCR), exportación a
  Markdown, texto, Word y JSON, y lista de excepciones.
- Licencia MIT.
