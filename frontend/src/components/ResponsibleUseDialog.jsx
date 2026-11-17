import { useEffect, useId, useRef, useState } from 'react'
import { ClipboardCheck, Lock, ShieldCheck, TriangleAlert, X } from 'lucide-react'
import { useI18n } from '../i18n.jsx'

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'

// Resalta los fragmentos entre **asteriscos** de los textos de i18n.
function emphasize(text) {
  return String(text)
    .split(/(\*\*[^*]+\*\*)/)
    .map((part, i) =>
      part.startsWith('**') && part.endsWith('**') ? (
        <strong key={i} className="font-semibold text-slate-900 dark:text-white">
          {part.slice(2, -2)}
        </strong>
      ) : (
        part
      ),
    )
}

const POINTS = [
  { key: 'responsibleLocal', icon: Lock },
  { key: 'responsibleSupport', icon: ShieldCheck },
  { key: 'responsibleReview', icon: ClipboardCheck },
]

// Diálogo modal de privacidad y uso responsable: primer uso y acceso desde el encabezado.
// Accesible: role="dialog", aria-modal, foco atrapado, Esc para cerrar y foco devuelto al cerrar.
export default function ResponsibleUseDialog({ open, dontShowAgain, onClose }) {
  const { t } = useI18n()
  const [checked, setChecked] = useState(dontShowAgain)
  const dialogRef = useRef(null)
  const primaryRef = useRef(null)
  const returnFocusRef = useRef(null)
  const titleId = useId()
  const descId = useId()

  // Valores actuales para el manejador de teclado a nivel de documento.
  const latest = useRef({ checked, onClose })
  latest.current = { checked, onClose }

  useEffect(() => {
    if (!open) return undefined
    setChecked(dontShowAgain)
    returnFocusRef.current = document.activeElement
    primaryRef.current?.focus()
    // Esc se escucha en el documento: así cierra aunque el foco aún no haya entrado al diálogo
    // (justo al abrirlo, o si quedó en un elemento que pasó a estar inerte).
    const onDocumentKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        latest.current.onClose(latest.current.checked)
      } else if (e.key === 'Tab' && !dialogRef.current?.contains(document.activeElement)) {
        e.preventDefault()
        primaryRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onDocumentKeyDown)
    return () => {
      document.removeEventListener('keydown', onDocumentKeyDown)
      // Devolver el foco a donde estaba (p. ej. el botón del encabezado).
      const target = returnFocusRef.current
      if (target && typeof target.focus === 'function' && document.contains(target)) target.focus()
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null

  const close = () => onClose(checked)

  // Foco atrapado: Tab / Shift+Tab giran dentro del diálogo (Esc se maneja en el documento).
  const onKeyDown = (e) => {
    if (e.key !== 'Tab') return
    const nodes = Array.from(dialogRef.current?.querySelectorAll(FOCUSABLE) ?? [])
    if (!nodes.length) return
    const first = nodes[0]
    const last = nodes[nodes.length - 1]
    if (e.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        onKeyDown={onKeyDown}
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900"
      >
        <div className="flex items-start gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-800 dark:bg-teal-500/15 dark:text-teal-200">
            <ShieldCheck className="h-5 w-5" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-base font-semibold text-slate-900 dark:text-white">
              {t('responsibleTitle')}
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-300">{t('responsibleSubtitle')}</p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label={t('closeDialog')}
            title={t('closeDialog')}
            className="rounded-md p-1 text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <ul id={descId} className="space-y-3 px-5 py-4">
          {POINTS.map(({ key, icon: Icon }) => (
            <li key={key} className="flex items-start gap-3 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-teal-700 dark:text-teal-300" aria-hidden />
              <span>{emphasize(t(key))}</span>
            </li>
          ))}
        </ul>

        <p className="mx-5 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {t('responsibleLimits')}
        </p>

        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              className="h-4 w-4 accent-teal-700 focus-visible:ring-2 focus-visible:ring-teal-600"
            />
            {t('dontShowAgain')}
          </label>
          <button
            ref={primaryRef}
            type="button"
            data-testid="responsible-ok"
            onClick={close}
            className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 dark:bg-teal-400 dark:text-slate-950 dark:hover:bg-teal-300 dark:focus-visible:ring-offset-slate-900"
          >
            {t('understood')}
          </button>
        </div>
      </div>
    </div>
  )
}
