// Aviso de privacidad y uso responsable: primer uso, "no volver a mostrar", reapertura y recordatorio.
import { anonymizeSample, newPage } from './mock.mjs'

const CLINICAL = ['María José', 'González', '12.345.678', 'Neumonía']

export default async function responsibleUse({ browser, url, fixture, check, screenshots }) {
  const { ctx, page } = await newPage(browser, url, fixture)
  const dialog = page.getByRole('dialog')

  await page.goto(url)
  await dialog.waitFor({ timeout: 5000 })
  check((await dialog.getAttribute('aria-modal')) === 'true', 'diálogo con role=dialog y aria-modal en el primer uso')
  await page.waitForTimeout(100)
  check((await page.evaluate(() => document.activeElement?.textContent?.trim())) === 'Entendido', 'foco inicial en "Entendido"')
  check((await page.locator('[inert]').count()) === 1, 'el resto de la app queda inerte con el diálogo abierto')

  let inside = true
  for (const key of ['Tab', 'Tab', 'Tab', 'Tab', 'Shift+Tab', 'Shift+Tab', 'Shift+Tab']) {
    await page.keyboard.press(key)
    inside &&= await page.evaluate(() => !!document.activeElement.closest('[role=dialog]'))
  }
  check(inside, 'Tab / Shift+Tab no salen del diálogo')
  if (screenshots) await page.screenshot({ path: `${screenshots}/aviso-claro.png` })

  await page.keyboard.press('Escape')
  check((await dialog.count()) === 0, 'Esc cierra el diálogo')
  await page.reload()
  await dialog.waitFor({ timeout: 5000 })
  check(true, 'sin "No volver a mostrar" reaparece al recargar')

  await dialog.getByLabel('No volver a mostrar').check()
  await dialog.getByRole('button', { name: 'Entendido' }).click()
  await page.reload()
  await page.waitForTimeout(600)
  check((await dialog.count()) === 0, 'con "No volver a mostrar" no reaparece')

  const headerBtn = page.getByRole('button', { name: 'Privacidad y uso responsable' })
  // Esc inmediatamente después de abrir (antes de cualquier espera) también debe cerrar.
  await headerBtn.click()
  await page.keyboard.press('Escape')
  check((await dialog.count()) === 0, 'Esc cierra aunque se presione justo al abrir')
  await headerBtn.click()
  await dialog.waitFor()
  check(await dialog.getByLabel('No volver a mostrar').isChecked(), 'reabierto desde el encabezado refleja la preferencia')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(100)
  check(
    (await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))) === 'Privacidad y uso responsable',
    'el foco vuelve al botón del encabezado',
  )

  // Recordatorio: sólo la primera copia/exportación de la sesión.
  await anonymizeSample(page)
  const reminder = page.getByRole('status').filter({ hasText: 'Revisa el resultado antes de compartirlo' })
  await page.click('[data-testid=copy-result]')
  await page.waitForTimeout(200)
  check((await reminder.count()) === 1, 'recordatorio no bloqueante en la primera copia')
  await reminder.getByRole('button').click()
  await page.waitForTimeout(1700)
  await page.click('[data-testid=copy-result]')
  await page.waitForTimeout(200)
  check((await reminder.count()) === 0, 'no se repite en la segunda copia')
  await page.getByRole('button', { name: 'Exportar' }).click()
  await page.getByRole('menuitem').first().click()
  await page.waitForTimeout(200)
  check((await reminder.count()) === 0, 'ni al exportar en la misma sesión')

  await page.reload()
  await anonymizeSample(page)
  await page.getByRole('button', { name: 'Exportar' }).click()
  await page.getByRole('menuitem').first().click()
  await page.waitForTimeout(200)
  check((await reminder.count()) === 1, 'en una sesión nueva aparece con la primera exportación')

  const ls = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage)))
  check(Object.keys(ls).every((k) => k === '__mock_prefs_json'), 'la app no escribe en localStorage (preferencias vía backend)')
  const prefs = JSON.parse(ls.__mock_prefs_json || '{}')
  check(prefs.responsibleUseDismissed === true, 'se guarda responsibleUseDismissed vía set_pref')
  check(!('custom_terms' in (prefs.options || {})), 'custom_terms nunca se envía a guardar')
  check(!CLINICAL.some((s) => JSON.stringify(ls).includes(s)), 'ningún contenido clínico en las preferencias')
  check(page.external.length === 0, `sin peticiones fuera de la app (${page.external.length})`)
  await ctx.close()
}
