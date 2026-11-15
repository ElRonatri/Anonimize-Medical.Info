// Preferencias locales (idioma, tema, opciones). Nunca se guarda contenido clínico.
const PREFIX = 'anonimize-medical:'

export function loadPref(key, fallback = null) {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    return raw === null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function savePref(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    /* almacenamiento no disponible: se ignora */
  }
}
