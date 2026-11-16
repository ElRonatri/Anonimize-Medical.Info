# Traducciones de la interfaz

Los textos de la interfaz están en `frontend/src/locales/<idioma>.json` (hoy `es.json` y
`en.json`), separados del código para que se puedan traducir con cualquier editor o herramienta
de traducción.

## Formato

```json
{
  "copy": "Copiar",
  "jobProgress": "Procesando {0} de {1}",
  "filesCount": { "one": "{0} archivo", "other": "{0} archivos" },
  "errors": { "read_error": "No se pudo leer el archivo." }
}
```

- `{0}`, `{1}`…: argumentos por posición (los entrega el código; no cambies su número).
- Plurales: objeto con categorías CLDR (`zero`, `one`, `two`, `few`, `many`, `other`); se elige
  según el primer argumento con `Intl.PluralRules` del idioma. `other` es obligatorio.
- Objetos anidados (`errors`, `warnings`, `status`…): grupos de claves (`t('errors.read_error')`).
- `**texto**` marca énfasis donde la interfaz lo soporta (diálogo de uso responsable).
- Sin código: nada de funciones ni `${...}`.

## Añadir un idioma

1. Copia `es.json` como `<código>.json` (p. ej. `pt.json`) y traduce los valores, no las claves.
2. Regístralo en `frontend/src/i18n.jsx`: importa el archivo, añádelo a `messages` y a `UI_LANGUAGES`.
3. Ejecuta `pytest tests/test_i18n.py`: verifica que todos los idiomas tengan las mismas claves,
   los mismos argumentos `{n}` y plurales válidos, y que toda clave usada en el código exista.
   (Para un idioma nuevo, añádelo a la comparación de la prueba.)

El idioma del **documento** (detección de etiquetas, marcadores `[PACIENTE]`) es independiente y
está en el backend (`backend/anonymizer/lang.py`).
