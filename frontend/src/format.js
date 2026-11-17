// Formato de los mensajes de src/locales/*.json (sin dependencias: se prueba también desde Node).

const PLURAL_CATEGORIES = new Set(['zero', 'one', 'two', 'few', 'many', 'other'])

export function isPlural(value) {
  return (
    value !== null &&
    typeof value === 'object' &&
    'other' in value &&
    Object.keys(value).every((k) => PLURAL_CATEGORIES.has(k))
  )
}

const pluralRules = {}

// Resuelve plurales y reemplaza {n} por el argumento n. Exportado para las pruebas.
export function formatMessage(value, lang, args = []) {
  if (isPlural(value)) {
    const rules = (pluralRules[lang] ??= new Intl.PluralRules(lang))
    value = value[rules.select(Number(args[0]))] ?? value.other
  }
  if (typeof value !== 'string') return value
  return value.replace(/\{(\d+)\}/g, (match, i) => (args[i] === undefined ? match : String(args[i])))
}
