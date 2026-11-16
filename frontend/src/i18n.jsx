import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { loadPref, savePref } from './storage.js'
import en from './locales/en.json'
import es from './locales/es.json'
import { formatMessage } from './format.js'

// Los textos viven en src/locales/<idioma>.json para poder traducirlos sin tocar código
// (ver docs/traducciones.md). Formato:
//   "clave": "texto con {0} y {1}"                  -> argumentos por posición
//   "clave": { "one": "{0} archivo", "other": "{0} archivos" }  -> plural según el 1.er argumento
//   "**texto**" marca énfasis donde el componente lo soporte.
const messages = { es, en }

export const UI_LANGUAGES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
]

const I18nContext = createContext(null)

function initialLanguage() {
  const saved = loadPref('uiLanguage')
  if (saved && messages[saved]) return saved
  const nav = (navigator.language || 'es').slice(0, 2)
  return messages[nav] ? nav : 'es'
}

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(initialLanguage)

  useEffect(() => {
    savePref('uiLanguage', lang)
    document.documentElement.lang = lang
  }, [lang])

  const t = useCallback(
    (key, ...args) => {
      const value = key.split('.').reduce((obj, k) => (obj ? obj[k] : undefined), messages[lang])
      if (value === undefined) return key
      return formatMessage(value, lang, args)
    },
    [lang],
  )

  const value = useMemo(() => ({ lang, setLang, t }), [lang, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  return useContext(I18nContext)
}
