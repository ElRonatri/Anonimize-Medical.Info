// "Ver original" y navegación con teclado (menú Exportar, filas de documentos, selectores).
import { anonymizeSample, newPage } from './mock.mjs'

export default async function ui({ browser, url, fixture, check, screenshots }) {
  for (const scheme of ['light', 'dark']) {
    const { ctx, page } = await newPage(browser, url, fixture, { scheme, prefs: { responsibleUseDismissed: true } })
    await page.goto(url)
    await anonymizeSample(page)
    const pre = page.locator('pre')
    const toggle = page.locator('[data-testid=toggle-original]')

    if (scheme === 'light') {
      check((await page.getAttribute('[data-testid=option-paste]', 'aria-pressed')) === 'true', 'selector segmentado con aria-pressed')
      const before = await pre.innerText()
      check(before.includes('[PACIENTE_1]') && !before.includes('María José'), 'por defecto se ven los marcadores')
      check((await toggle.getAttribute('aria-pressed')) === 'false', '"Ver original" desactivado por defecto')
      await toggle.focus()
      await page.keyboard.press('Enter')
      check((await toggle.getAttribute('aria-pressed')) === 'true', '"Ver original" se activa con el teclado')
      check((await pre.innerText()).includes('María José González Pérez'), 'muestra el valor original en el texto')
      check(
        (await page.locator('mark[data-placeholder="[PACIENTE_1]"]').getAttribute('title')) === '[PACIENTE_1] · Paciente',
        'el marcador sigue disponible en el título',
      )
      check((await page.getByRole('status').filter({ hasText: 'no compartas esta vista' }).count()) === 1, 'aviso mientras se ven originales')
      await page.click('[data-testid=copy-result]')
      await page.waitForTimeout(150)
      const copied = await page.evaluate(() => window.__calls.filter((c) => c[0] === 'copy_to_clipboard').map((c) => c[1][0]).pop())
      check(Boolean(copied?.includes('[PACIENTE_1]')) && !copied.includes('María'), 'Copiar entrega el texto anonimizado')
      if (screenshots) await page.screenshot({ path: `${screenshots}/ver-original-claro.png` })

      // Menú Exportar con teclado (patrón ARIA de menú).
      const trigger = page.getByRole('button', { name: 'Exportar' })
      await trigger.focus()
      await page.keyboard.press('ArrowDown')
      check((await page.evaluate(() => document.activeElement.getAttribute('role'))) === 'menuitem', 'Flecha abajo abre el menú en la primera opción')
      await page.keyboard.press('End')
      check(
        await page.evaluate(() => document.activeElement === [...document.querySelectorAll('[role=menu] [role^=menuitem]')].pop()),
        'Fin va a la última opción',
      )
      await page.keyboard.press('Escape')
      check(
        (await page.locator('[role=menu]').count()) === 0 && (await page.evaluate(() => document.activeElement.textContent.includes('Exportar'))),
        'Esc cierra y devuelve el foco al botón',
      )
      await page.keyboard.press('ArrowDown')
      await page.keyboard.press('ArrowDown')
      await page.keyboard.press('Enter')
      await page.waitForTimeout(150)
      const fmt = await page.evaluate(() => window.__calls.filter((c) => c[0] === 'export_file').map((c) => c[1][1]).pop())
      check(fmt === 'txt', `Enter exporta la opción enfocada (${fmt})`)

      const row = page.locator('li:has(button[aria-current])')
      check((await row.locator('button').count()) === 2 && (await row.locator('[role=button]').count()) === 0, 'fila de documento sin controles anidados')
      check((await row.locator('button').nth(1).getAttribute('aria-label')).startsWith('Quitar'), 'botón quitar nombra el documento')
    } else {
      await toggle.click()
      if (screenshots) await page.screenshot({ path: `${screenshots}/ver-original-oscuro.png` })
      check((await toggle.getAttribute('aria-pressed')) === 'true', '"Ver original" también en tema oscuro')
    }
    await ctx.close()
  }
}
