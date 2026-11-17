// Mock de window.pywebview.api (el backend de Python) para las pruebas de interfaz.
// - Las preferencias simulan prefs.json: persisten entre recargas en una clave aparte.
// - Registra las llamadas en window.__calls para verificar qué se copió o exportó.
// - Sin portapapeles del navegador: la copia pasa por el backend simulado.
export function mockBackend(fixture, { prefs = null } = {}) {
  return `(() => {
    const D = ${JSON.stringify(fixture)};
    const KEY = '__mock_prefs_json';
    ${prefs ? `localStorage.setItem(KEY, ${JSON.stringify(JSON.stringify(prefs))});` : ''}
    const load = () => JSON.parse(localStorage.getItem(KEY) || '{}');
    window.__calls = [];
    const base = {
      get_app_info: async () => D.info,
      get_prefs: async () => ({ ok: true, prefs: load() }),
      set_pref: async (k, v) => { const p = load(); p[k] = v; localStorage.setItem(KEY, JSON.stringify(p)); return { ok: true } },
      process_text: async () => JSON.parse(JSON.stringify(D.process)),
      copy_to_clipboard: async () => ({ ok: true }),
      export_file: async () => ({ ok: true }),
      export_batch: async () => ({ ok: true, count: 1, folder: 'C:/tmp' }),
    };
    const api = new Proxy(base, { get(t, k) {
      if (k === 'then') return undefined;
      return async (...a) => { window.__calls.push([String(k), a]); return t[k] ? t[k](...a) : { ok: true } };
    }});
    window.pywebview = { api };
    try { Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true }) } catch {}
  })()`
}

export async function newPage(browser, url, fixture, options = {}) {
  const { scheme = 'light', locale = 'es-CL', prefs = null } = options
  const ctx = await browser.newContext({ locale, colorScheme: scheme, viewport: { width: 1280, height: 860 }, deviceScaleFactor: 2 })
  const external = []
  ctx.on('request', (r) => { if (!r.url().startsWith(url)) external.push(r.url()) })
  await ctx.addInitScript(mockBackend(fixture, { prefs }))
  const page = await ctx.newPage()
  page.external = external
  return { ctx, page }
}

export async function anonymizeSample(page) {
  await page.click('[data-testid=option-paste]')
  await page.fill('[data-testid=paste-text]', 'Paciente: María José González Pérez')
  await page.click('[data-testid=anonymize-text]')
  await page.waitForSelector('[data-testid=copy-result]')
}
