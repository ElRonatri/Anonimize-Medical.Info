// WCAG 2.1 A/AA (y buenas prácticas) con axe-core en los estados principales, tema claro y oscuro.
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { anonymizeSample, newPage } from './mock.mjs'

const AXE = readFileSync(createRequire(import.meta.url).resolve('axe-core/axe.min.js'), 'utf8')
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']

async function audit(page, label, check) {
  await page.addScriptTag({ content: AXE })
  const violations = await page.evaluate(async (tags) => {
    const res = await window.axe.run(document, { runOnly: tags })
    return res.violations.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.html.slice(0, 120)}`)
  }, TAGS)
  check(violations.length === 0, `axe · ${label}${violations.length ? '\n    ' + violations.join('\n    ') : ''}`)
}

export default async function accessibility({ browser, url, fixture, check }) {
  for (const scheme of ['light', 'dark']) {
    const name = scheme === 'light' ? 'claro' : 'oscuro'
    const { ctx, page } = await newPage(browser, url, fixture, { scheme })
    await page.goto(url)
    await page.getByRole('dialog').waitFor()
    await audit(page, `${name} · aviso de primer uso`, check)
    await page.click('[data-testid=responsible-ok]')
    await audit(page, `${name} · inicio`, check)
    await anonymizeSample(page)
    await audit(page, `${name} · resultado`, check)
    await page.click('[data-testid=toggle-original]')
    await audit(page, `${name} · ver original`, check)
    await page.getByRole('button', { name: 'Exportar' }).click()
    await audit(page, `${name} · menú exportar`, check)
    await ctx.close()
  }
}
