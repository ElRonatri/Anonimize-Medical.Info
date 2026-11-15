// Puente hacia el backend de Python expuesto por PyWebView en `window.pywebview.api`.

let apiPromise = null

export function getApi(timeoutMs = 4000) {
  if (!apiPromise) {
    apiPromise = new Promise((resolve) => {
      if (window.pywebview?.api) return resolve(window.pywebview.api)
      const onReady = () => resolve(window.pywebview?.api ?? null)
      window.addEventListener('pywebviewready', onReady, { once: true })
      setTimeout(() => {
        window.removeEventListener('pywebviewready', onReady)
        resolve(window.pywebview?.api ?? null)
      }, timeoutMs)
    })
  }
  return apiPromise
}

async function call(method, ...args) {
  const api = await getApi()
  if (!api || typeof api[method] !== 'function') {
    return { ok: false, error: 'no_backend' }
  }
  try {
    const result = await api[method](...args)
    return result ?? { ok: false, cancelled: true }
  } catch (err) {
    return { ok: false, error: 'generic', detail: String(err?.message ?? err) }
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

export const backend = {
  info: () => call('get_app_info'),
  openFileDialog: () => call('open_file_dialog'),
  processFile: (path, options) => call('process_file', path, options),
  processDroppedFile: async (file, options) =>
    call('process_base64', file.name, await fileToBase64(file), options),
  processText: (text, options) => call('process_text', text, options),
  reprocess: (options) => call('reprocess', options),
  save: (content, name) => call('save_result', content, name),
  copy: (text) => call('copy_to_clipboard', text),
}

export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* se intenta con el backend */
  }
  const res = await backend.copy(text)
  return Boolean(res?.ok)
}
