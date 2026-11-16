# Reglas de identificadores por país

Los formatos de documentos de identidad, seguridad social y salud por país **son datos**, no
código: viven en `backend/anonymizer/data/identifiers/` y se cargan y validan al iniciar
(`backend/anonymizer/country_rules.py`). Añadir o corregir un país no requiere tocar
`identifiers.py`.

```
data/identifiers/
├── countries/          un archivo por país o grupo de países (capa estructural)
│   ├── cl.json         Chile: RUN/RUT con dígito verificador
│   ├── international.json   MRZ de pasaportes (se aplica en cualquier región)
│   └── ...
├── contextual.json     palabras clave de la capa «palabra clave + valor»
└── regions.json        regiones del selector de la interfaz -> códigos de país
```

Se eligió **JSON** (biblioteca estándar) y no YAML para no añadir dependencias al ejecutable.

## Archivo de país

```json
{
  "country": "Chile",
  "codes": ["CL"],
  "patterns": [
    {
      "label": "RUN_CL",
      "name": "RUN/RUT",
      "regex": "${B}\\d{1,2}(?:\\.\\d{3}\\.\\d{3}|\\d{6})-[\\dkK]${E}",
      "validator": "run_cl"
    }
  ],
  "keywords": { "ci": ["rol\\s+[uú]nico\\s+nacional"], "cs": ["RUN"] }
}
```

| Campo | Obligatorio | Descripción |
|---|---|---|
| `country` | sí | Nombre visible del país o grupo. |
| `codes` | sí | Códigos ISO 3166-1 alfa-2 en mayúsculas; `"*"` = cualquier región. |
| `patterns[].label` | sí | Etiqueta del reemplazo (`[RUN_CL]`): MAYÚSCULAS, dígitos y `_`. |
| `patterns[].name` | sí | Nombre del formato (se muestra en la interfaz). |
| `patterns[].regex` | sí | Expresión regular de Python. `${B}` / `${E}` = inicio / fin de token. |
| `patterns[].validator` | no | Clave de un validador registrado (dígito verificador). |
| `patterns[].flags` | no | `["IGNORECASE"]`. |
| `macros` | no | Fragmentos reutilizables: `{"MX_STATES": "AS\|BC\|..."}` → `${MX_STATES}`. |
| `keywords.ci` / `keywords.cs` | no | Palabras clave extra (insensibles / sensibles a mayúsculas). |

Al cargar se verifica todo: campos desconocidos, códigos, etiquetas, que cada expresión compile,
que las macros existan, que el validador esté registrado y que no haya patrones duplicados. Un
error indica archivo y campo, p. ej. `pe.json: patterns[0].validator: validador desconocido: 'x'`.

Para que el país aparezca en el selector de la interfaz basta con añadir su código a una región
de `regions.json`: el nombre se obtiene del sistema (`Intl.DisplayNames`) en el idioma de la
interfaz. Una región *nueva* necesita además su nombre en los textos de la interfaz
(`regions.<id>`) y su lugar en `REGION_ORDER` (`frontend/src/components/RegionSelect.jsx`).

## Validadores (dígito verificador)

Están en `backend/anonymizer/validators.py` y se registran con una clave:

```python
from anonymizer.validators import register

@register("ce_pe")
def v_ce_pe(s: str) -> bool:
    ...
```

Las funciones `v_<clave>` de ese módulo se registran solas. Un **plugin** (paquete instalado
aparte) puede aportar validadores sin modificar el proyecto, con un *entry point*:

```toml
[project.entry-points."anonimize_medical.validators"]
ce_pe = "mi_paquete.validadores:v_ce_pe"
```

Los plugins sólo se cargan al ejecutar desde el código fuente: el ejecutable no instala ni
descarga nada. Un plugin defectuoso se omite (con un aviso en el registro, sin contenido clínico).

## Reglas locales sin recompilar

La variable de entorno `ANONIMIZE_RULES_DIR` acepta una o más carpetas (separadas por `;` en
Windows) con archivos de país en el mismo formato; se suman a las incluidas. Sirve para probar
un formato nuevo, o para que una institución añada el suyo, sin recompilar. Sólo pueden usar
validadores ya registrados.

## Pruebas

`tests/test_country_rules.py` valida todos los archivos incluidos, los mensajes de error y que
un país nuevo (archivo JSON + validador) funcione de punta a punta sin tocar el código. Los
*golden files* (`tests/golden/`) aseguran que el resultado no cambió al mover las reglas a JSON.
