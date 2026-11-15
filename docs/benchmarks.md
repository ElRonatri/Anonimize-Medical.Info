# Benchmarks

Todas las cifras se obtienen con `scripts/bench.py` sobre documentos **sintéticos** (datos ficticios).
Se reporta el **mejor de 5** ejecuciones de `anonymize_document` (extracción de etiquetas,
detección, búsqueda de valores, resolución de solapamientos y salida Markdown).

```bash
python scripts/bench.py --compare --repeat 5   # compara regex / aho / auto y verifica salida idéntica
```

Entorno de medición: contenedor Linux x86_64, 4 vCPU, Python 3.13. Los tiempos absolutos varían
según el equipo; las proporciones son las relevantes.

## Bloque 3: búsqueda de valores con Aho-Corasick

Tras detectar un nombre (o un identificador) el motor lo busca en todo el documento para
ocultar cada aparición («propagación»). Antes se usaba **una regex con una alternativa por valor**:
su costo es O(longitud × valores), así que crece mal con documentos que mencionan muchas personas
(registros, listados, lotes concatenados). Ahora, a partir de 100 valores de un mismo tipo, se usa
**Aho-Corasick** (`pyahocorasick`): una sola pasada, O(longitud + coincidencias).

Escenarios:

- **dense**: 1,25 M caracteres de evolución clínica de un paciente (caso habitual: pocos valores).
- **names N**: registro de N pacientes con RUT + 4·N notas que los mencionan (muchos valores distintos).

| Escenario | Caracteres | Valores | Antes (regex) | Después (`auto`) | Aceleración |
|---|---:|---:|---:|---:|---:|
| dense (1 paciente) | 1 251 599 | 11 | 894 ms | 903 ms | ×0,99 (igual) |
| names 20 pacientes | 12 536 | 86 | 9,7 ms | 9,5 ms | ×1,02 (igual) |
| names 100 pacientes | 63 388 | 284 | 65 ms | 52 ms | ×1,26 |
| names 500 pacientes | 318 199 | 1 086 | 800 ms | 253 ms | ×3,2 |
| names 2000 pacientes | 1 274 726 | 4 086 | **12 905 ms** | **1 004 ms** | **×12,9** |

En todos los escenarios la salida (texto y entidades) es **idéntica** byte a byte entre motores.

### Por qué `auto` y no siempre Aho-Corasick

Forzar Aho-Corasick con pocos valores es algo **más lento** (×0,80 en *dense*): plegar cada línea
y construir el autómata cuesta más que una regex de 11 alternativas. Medición del punto de cruce:

| Pacientes | Valores | regex | aho |
|---:|---:|---:|---:|
| 3 | 18 | 1,33 ms | 1,65 ms |
| 10 | 48 | 4,49 ms | 5,26 ms |
| 20 | 86 | 10,04 ms | 10,73 ms |
| 30 | 118 | 15,61 ms | 15,80 ms |
| 50 | 174 | 28,95 ms | 26,27 ms |

El cruce está en torno a 120 valores; `AHO_MIN_TERMS = 100` (por tipo: nombres y, por separado,
identificadores) en `backend/anonymizer/detector.py`.

### Equivalencia con la regex

`anonymizer/fastmatch.py` reproduce las reglas de las regex «difusas»:

- insensible a mayúsculas y tildes, con un plegado **de igual longitud** (las posiciones valen
  sobre el texto original, donde se verifican los límites de palabra y la mayúscula inicial);
- nombres completos: espacios y comas entre palabras equivalen a un espacio (`,?\s+`);
- identificadores: se ignoran espacios, puntos, guiones, barras y paréntesis.

Única diferencia conocida (a favor de la privacidad): con un espacio **antes** de la coma
(«PÉREZ , JUAN», típico de OCR) la regex no reconocía el nombre completo y lo ocultaba en partes;
Aho-Corasick lo reconoce como un solo marcador. Nunca oculta menos que la regex.

Verificación automática: los 13 *golden files* se ejecutan con ambos motores
(`tests/test_golden.py`) y 12 documentos aleatorios «sucios» (mayúsculas, sin tildes, comas,
espacios múltiples, tabuladores) deben producir salida idéntica (`tests/test_fastmatch.py`).

### Otra corrección encontrada al perfilar

La deduplicación de alternativas de la regex combinada usaba `if x not in lista` (O(n²): ~16
millones de comparaciones con 4 000 valores). Ahora usa `dict.fromkeys` (O(n)).

## Bloque 4: lotes en paralelo

`scripts/bench_batch.py` procesa lotes de documentos ficticios con 1, 2 y 3 procesos de extracción
(equipo de 4 núcleos). Tiempo total del lote, de la cola al último resultado:

```bash
python scripts/bench_batch.py --docs 8 --workers 1 2 3
```

| Lote | 1 proceso | 2 procesos | 3 procesos |
|---|---:|---:|---:|
| 8 PDFs escaneados, 3 páginas, OCR Tesseract | 38,1 s | 20,1 s (**×1,89**) | 13,7 s (**×2,78**) |
| 8 PDFs con texto (4 KB c/u) | 0,20 s | 0,38 s (×0,53) | 0,41 s (×0,50) |

- **El OCR escala casi linealmente** con los procesos. La lectura de PDF (pdfminer, Python puro)
  también se beneficia, pero en documentos livianos el arranque de los procesos (~0,2-0,4 s, una
  vez por sesión) cuesta más que el trabajo. Por eso el paralelo se usa sólo si vale la pena: con
  OCR forzado, lotes de 1 MB o más, o si los procesos ya están activos de un lote anterior.
- **Sobresuscripción de hilos:** sin límite, Tesseract (OpenMP) y onnxruntime intentan usar todos
  los núcleos en cada proceso; con 2 procesos se estorbaban hasta superar 180 s por página. Cada
  proceso usa ahora `núcleos / procesos` hilos (`OMP_THREAD_LIMIT`, `intra_op_num_threads`).
  Incluso con un solo proceso, Tesseract limitado a 1 hilo fue más rápido (4,2 s frente a 5,1 s
  en 3 páginas).
