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
