# Detección con IA (NER) — variante opcional

Segunda pasada con un modelo de reconocimiento de entidades (spaCy) para **nombres sin etiqueta ni
tratamiento**, que las reglas no detectan («acude con su hija Bernardita Quiroga»). Los nombres
encontrados entran a la misma propagación de las reglas (se ocultan en todo el documento).
Opcionalmente, también **organizaciones** con nombre propio («Hospital del Salvador»).

## Cómo obtenerla y desactivarla

- Es una **variante de build**: `build.bat --ner`. El build base no la incluye (regla del proyecto:
  todo motor que aumente el tamaño del ejecutable es opcional).
- spaCy y el modelo se instalan **en tiempo de build** (`requirements-ner.txt`, con la URL del
  modelo fijada por hash SHA-256) y van dentro del ejecutable. **Nunca se descarga nada en tiempo
  de ejecución** (además, el proceso bloquea la red).
- En la aplicación: *Opciones → Detección con IA (NER) → Buscar nombres sin etiqueta*. Está
  **desactivada por defecto**. Sin la variante, la sección aparece deshabilitada y explica cómo
  obtenerla. Para no usarla nunca, basta con no compilar con `--ner`.

## Costo

| | Sin NER | Con NER |
|---|---:|---:|
| Tamaño del ejecutable (carpeta / ZIP) | 73 MB / 40 MB | 278 MB / 98 MB (medido por el CI) |
| Memoria del proceso (anonimizar una epicrisis) | 20 MB | 127 MB |
| Carga del modelo (una vez por sesión, al activar NER) | — | ~0,2 s |
| Tiempo por página (~1 000 caracteres) | 7 ms | ~30 ms (2 ms si el documento ya se analizó) |

El análisis del modelo se guarda en caché por documento: cambiar otras opciones no lo repite.
La pasada corre en el proceso principal (no en los procesos de extracción en paralelo), así que la
memoria no se multiplica por procesos.

## Modelo y licencias

| Modelo | Licencia | Cobertura ES / EN* | Falsos + ES / EN* | RAM al cargar |
|---|---|---:|---:|---:|
| **`xx_ent_wiki_sm`** (multilingüe) — **usado** | **MIT** | 100 % / 100 % | 0 / 0 | 403 MB completo · **30 MB** sólo NER |
| `es_core_news_sm` | **GPL-3.0** | 100 % / — | 0 / — | 66 MB |
| `en_core_web_sm` | MIT | — / 91,7 % | — / 0 | 49 MB |

\* `scripts/eval_ner.py`: 60 notas sintéticas por idioma con nombres sin etiqueta y términos
clínicos en mayúscula, umbral 0,8, con el filtro clínico.

- `es_core_news_sm` se descartó por su **licencia GPL-3.0** (entrenado con AnCora), incompatible
  con distribuir el ejecutable bajo MIT sin más trámite; además no mejoró los resultados.
- `xx_ent_wiki_sm` cubre ambos idiomas con un solo modelo (MIT). Su tokenizador multilingüe ocupa
  ~400 MB de RAM, así que se cargan **sólo los pesos del NER** sobre el tokenizador liviano del
  idioma: 30 MB y entidades idénticas en las pruebas.
- spaCy: MIT. El resto de dependencias de la variante (thinc, srsly, blis, cymem, preshed...) son
  MIT o BSD.

Si alguien instala explícitamente `es_core_news_sm` o `en_core_web_sm`, el motor los usa como
alternativa (ver `MODELS` en `backend/anonymizer/ner.py`) y asume sus licencias.

## Precisión: umbral y filtros

- **Umbral de confianza** (por defecto 0,80, ajustable en la interfaz): probabilidad de cada entidad
  según *beam search* del propio modelo. Más alto = menos falsos positivos, pero puede omitir nombres.
- **El modelo se equivoca con total seguridad**: marca «Diabetes Mellitus» como persona con
  confianza 1,00. Por eso el umbral no basta y hay filtros:
  - **léxico clínico** editable, `backend/anonymizer/data/clinical_terms.txt` (~750 términos ES/EN:
    patologías, epónimos como Parkinson o Hodgkin, fármacos, servicios, secciones). Sin este filtro
    la evaluación muestra 1–5 falsos positivos;
  - al menos **dos palabras con mayúscula** por persona («Ayer», «Durante» no son nombres);
  - cada entidad se divide en **tramos de palabras con mayúscula** («Médico tratante: Dra. Carolina
    Ibáñez Reyes» → «Carolina Ibáñez Reyes»), sin dígitos ni siglas;
  - en organizaciones se conserva sólo la parte identificatoria («Servicio de Urgencia del Hospital
    del Salvador» → «Hospital del Salvador»; «Hospital Regional» no se oculta);
  - se respetan la lista de excepciones y la opción de profesionales: si no se anonimizan
    profesionales, los nombres que las reglas identifican como tales no se ocultan por NER.

## Limitaciones

- El modelo multilingüe es pequeño: con texto clínico real produce muchos candidatos erróneos que
  los filtros descartan; puede omitir nombres poco frecuentes o escritos en minúscula.
- No distingue roles (paciente, familiar, profesional): los nombres que encuentra se marcan como
  `[PERSONA]`.
- Sigue siendo una herramienta de apoyo: **revisa el resultado**.

## Verificación

- `tests/test_ner.py`: filtros (sin modelo) y comportamiento con el modelo real; el CI tiene un job
  dedicado con la variante instalada que también ejecuta `scripts/eval_ner.py`.
- La autoprueba del ejecutable `--ner` (`--expect-ner`) verifica, sin red, que un nombre sin
  etiqueta se oculta y un término clínico no.
