# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[Versionado Semántico](https://semver.org/lang/es/). La versión se define en un solo lugar:
`backend/anonymizer/__init__.py` (`__version__`).

## [Unreleased]

### Añadido (UI/UX y accesibilidad)
- **«Ver original»** en la vista resaltada: muestra en pantalla los valores originales en lugar de
  los marcadores para revisar qué se ocultó, con aviso de no compartir la vista. Desactivado por
  defecto, no se guarda, y copiar/exportar siguen usando el texto anonimizado.
- Pruebas de interfaz en `frontend/e2e/` (`npm run test:e2e`, también en el CI): aviso de uso
  responsable, teclado, «Ver original» y auditoría **axe-core** WCAG 2.1 AA en 10 estados (claro y
  oscuro), hoy sin incumplimientos. Dependencias sólo de desarrollo, no van en el ejecutable:
  `playwright` 1.63.0 (Apache-2.0; Chromium se descarga sólo en el CI de pruebas) y `axe-core`
  4.10.3 (MPL-2.0, ~0,5 MB).

### Corregido (accesibilidad)
- Contraste AA en textos secundarios (antes 2,5–4,3:1) y en el anillo de foco (antes teal al 50 %).
- Filas de documentos sin controles anidados (`role="button"` con un botón dentro): ahora dos
  botones, con `aria-current` y «Quitar: <documento>».
- Menú Exportar con el patrón ARIA de menú: flechas, Inicio/Fin, Esc devuelve el foco, opción de
  nombres genéricos como `menuitemcheckbox`.
- `aria-pressed` en selectores segmentados y vista/edición; nombre accesible en el botón para
  cerrar avisos; íconos decorativos con `aria-hidden`; resultado enfocable para leer con teclado.

### Seguridad (rastros en disco)
- La ventana (WebView2) corre en **modo privado** con un perfil propio en
  `%LOCALAPPDATA%\AnonimizeMedical\WebView2`, que se borra al cerrar y, tras un cierre abrupto, al
  volver a abrir. Antes el perfil era persistente y genérico (`%APPDATA%\pywebview`): caché, Local
  Storage y posibles volcados de Crashpad.
- Informes de fallos de WebView2 desactivados (`--disable-breakpad --disable-crash-reporter`, añadidos
  a las propiedades de creación de pywebview antes de que WebView2 las lea: la variable de entorno
  sola no surtía efecto, según la sonda en el CI; el runtime igual lanza `crashpad-handler`, cuyos
  volcados quedarían dentro del perfil efímero) y
  Windows Error Reporting sin el heap del proceso (`WerSetFlags`).
- Preferencias en `%APPDATA%\AnonimizeMedical\prefs.json`, escritas por el backend con una lista
  cerrada de claves y tipos: cualquier otra cosa se descarta.
- Los procesos de extracción en paralelo terminan si el proceso principal muere (antes quedaban
  vivos, con documentos en memoria, tras un cierre abrupto; lo detectó la sonda en el CI).
- Sonda `--privacy-probe` y paso de CI en Windows: con el `.exe` real, un nombre centinela, OCR en
  procesos paralelos, exportación y un cierre abrupto simulado, busca el centinela (UTF-8/UTF-16)
  en `%TEMP%`, `%LOCALAPPDATA%` y `%APPDATA%`. Documentado en `docs/privacidad-en-disco.md`.

### Cambiado (mantenibilidad)
- Reglas de identificadores por país movidas a JSON (`backend/anonymizer/data/identifiers/`):
  un archivo por país, más `contextual.json` y `regions.json`. Se validan al cargar con mensajes
  que indican archivo y campo. Sin dependencias nuevas (JSON de la biblioteca estándar).
- Validadores de dígito verificador en `validators.py` con registro por clave (`@register`) y
  plugins por *entry points* (`anonimize_medical.validators`, sólo desde el código fuente).
- Reglas locales adicionales sin recompilar con `ANONIMIZE_RULES_DIR`. Guía en
  `docs/reglas-por-pais.md`; la autoprueba del ejecutable verifica que las reglas estén incluidas.
- Textos de la interfaz movidos de `i18n.jsx` a `frontend/src/locales/{es,en}.json` (argumentos
  `{0}` y plurales con `Intl.PluralRules`), aptos para herramientas de traducción. Prueba que
  ambos idiomas tengan las mismas claves y argumentos y que toda clave usada exista. Guía en
  `docs/traducciones.md`. Corrige «Se exportaron 1 archivo» → «Se exportó 1 archivo».
- `mypy --strict` (más `warn_unreachable`) en todo el backend, sin excepciones por módulo: tipos
  completos en las funciones que faltaban (páginas de pdfplumber, OCR, API con `JSONDict`).
  Detectó que `Api._window` se infería como `None`, lo que dejaba sin revisar el código de los
  diálogos de archivo.

### Añadido (privacidad y uso responsable)
- Diálogo de **primer uso** «Privacidad y uso responsable» (ES/EN): procesamiento 100 % local,
  herramienta de *apoyo* (no garantía de anonimización legal) y revisión obligatoria del resultado,
  más los límites por diseño. Accesible: `role="dialog"`, `aria-modal`, foco atrapado, Esc para
  cerrar, foco devuelto al cerrar y resto de la app `inert` mientras está abierto.
- Casilla «No volver a mostrar»: es lo **único** que se guarda (`responsibleUseDismissed`); nunca
  contenido clínico.
- Botón permanente «Privacidad y uso responsable» en el encabezado para reabrir el diálogo.
- Recordatorio no bloqueante («Revisa el resultado antes de compartirlo») en la primera copia o
  exportación de cada sesión, una sola vez.

### Cambiado
- Botón primario con contraste AA (`teal-700` + blanco, 5,4:1; antes `teal-600`, 3,7:1). Los
  avisos informativos usan `role="status"` y los errores `role="alert"`.
- Tamaño medido de la variante `--ner`: 278 MB (ZIP 98 MB).

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

### Añadido (releases)
- Workflow de release (`release.yml`, tags `vX.Y.Z`): compila y prueba las tres variantes,
  publica los ZIP con `SHA256SUMS.txt` y notas tomadas del CHANGELOG; ensayo sin publicar desde
  *Run workflow*. Build de Windows extraído a un workflow reutilizable (`build-windows.yml`).
- `scripts/checksums.py` (crear/verificar sumas) y `scripts/release_notes.py`.
- `docs/release.md` y `docs/signing.md` (firma Authenticode documentada, no activada).

### Añadido (detección con IA)
- Segunda pasada NER opcional (variante `build.bat --ner`, desactivada por defecto) para nombres
  sin etiqueta y organizaciones: modelo multilingüe `xx_ent_wiki_sm` (MIT; se descartó
  `es_core_news_sm` por GPL-3.0), confianza por *beam search* con umbral ajustable, filtro con
  léxico clínico editable (`data/clinical_terms.txt`), respeto de excepciones y de la opción de
  profesionales. Carga sólo los pesos NER sobre el tokenizador del idioma: 127 MB de memoria en
  lugar de 508 MB. Modelo fijado por hash en `requirements-ner.txt`; nunca se descarga en tiempo
  de ejecución. `scripts/eval_ner.py`, `docs/ner.md`; CI con job NER y variante Windows `ner`.

### Cambiado
- **OCR int8 evaluado y descartado:** los modelos cuantizados ahorran ≤23 MB (8 % de la variante
  `--ocr`) pero reconocen menos palabras, exponen más datos y son más lentos
  (`scripts/eval_ocr.py`, `docs/benchmarks.md`).
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
- Datos pegados por el OCR a la palabra siguiente («21/08/1985Edad:», «778201Previsión:») quedaban
  visibles aunque se detectaban por su etiqueta. Encontrado con `scripts/eval_ocr.py`.
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
