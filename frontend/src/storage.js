// Preferencias (idioma, tema, opciones, aviso de uso responsable). Nunca contenido clínico.
//
// En la aplicación se guardan en prefs.json a través del backend, que sólo acepta claves y tipos
// permitidos (backend/appdata.py). La ventana corre en modo privado: nada se escribe en el perfil
// de WebView2. Sin backend (navegador, desarrollo) se usa localStorage.
import { getApi } from './api.js'

const PREFIX = 'anonimize-medical:'
let cache = null // preferencias del backend, cargadas por initPrefs() antes de mostrar la interfaz
let api = null

export async function initPrefs() {
  api = await getApi()
  if (!api || typeof api.get_prefs !== 'function') {
    api = null
    return
  }
  try {
    const res = await api.get_prefs()
    cache = res?.ok && res.prefs && typeof res.prefs === 'object' ? { ...res.prefs } : {}
  } catch {
    cache = {}
  }
}

export function loadPref(key, fallback = null) {
  if (cache) return key in cache ? cache[key] : fallback
  try {
    const raw = localStorage.getItem(PREFIX + key)
    return raw === null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function savePref(key, value) {
  if (cache) {
    cache[key] = value
    api?.set_pref(key, value)?.catch?.(() => {})
    return
  }
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    /* almacenamiento no disponible: se ignora */
  }
}
