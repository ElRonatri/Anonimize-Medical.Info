// Pruebas de interfaz en Chromium (Playwright) contra la compilación de producción (dist/).
// El backend de Python se reemplaza por un mock de window.pywebview.api con datos sintéticos.
//
//   npm run build && npm run test:e2e            (capturas en e2e/screenshots/ con --screenshots)
//
// Sin red: un servidor estático local sirve dist/ y toda petición a otro origen hace fallar la prueba.
import { createServer } from 'node:http'
import { readFileSync, existsSync, mkdirSync } from 'node:fs'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import responsibleUse from './responsible-use.mjs'
import ui from './ui.mjs'
import accessibility from './accessibility.mjs'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const DIST = join(ROOT, 'dist')
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }

if (!existsSync(join(DIST, 'index.html'))) {
  console.error('Falta dist/: ejecuta "npm run build" primero.')
  process.exit(2)
}

const server = createServer((req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^([/\\])+/, '')
  const file = join(DIST, path || 'index.html')
  if (!file.startsWith(DIST) || !existsSync(file)) return res.writeHead(404).end()
  res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(readFileSync(file))
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const url = `http://127.0.0.1:${server.address().port}/`

const screenshots = process.argv.includes('--screenshots') ? join(ROOT, 'e2e', 'screenshots') : null
if (screenshots) mkdirSync(screenshots, { recursive: true })

const fixture = JSON.parse(readFileSync(join(ROOT, 'e2e', 'fixtures', 'backend.json'), 'utf8'))
let failures = 0
const check = (ok, message) => {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${message}`)
  if (!ok) failures++
}

const browser = await chromium.launch()
try {
  for (const [name, suite] of [['Uso responsable', responsibleUse], ['Interfaz', ui], ['Accesibilidad (axe)', accessibility]]) {
    console.log(`\n== ${name}`)
    await suite({ browser, url, fixture, check, screenshots })
  }
} catch (err) {
  console.error(err)
  failures++
} finally {
  await browser.close()
  server.close()
}
console.log(failures ? `\n${failures} falla(s)` : '\nTodo OK')
process.exit(failures ? 1 : 0)
