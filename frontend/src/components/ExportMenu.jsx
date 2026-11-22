import { useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronDown, Download, FileCode2, FileJson, FileLock, FileText, FileType2, Loader2 } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { loadPref, savePref } from '../storage.js'
import { Button, cx } from './ui.jsx'

const FORMATS = [
  { id: 'md', icon: FileCode2 },
  { id: 'txt', icon: FileText },
  { id: 'docx', icon: FileType2 },
  { id: 'json', icon: FileJson },
]
// PDF censurado: recrea el PDF original página por página con los datos tapados.
const PDF_FORMAT = { id: 'pdf', icon: FileLock }

export default function ExportMenu({ onExport, onExportAll, doneCount, pdfAvailable = false, pdfCount = 0 }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [generic, setGeneric] = useState(() => loadPref('exportGeneric', false))
  const ref = useRef(null)
  const triggerRef = useRef(null)
  const menuRef = useRef(null)
  const menuId = useId()

  const items = () => Array.from(menuRef.current?.querySelectorAll('[role^="menuitem"]') ?? [])
  const closeAndFocus = () => {
    setOpen(false)
    triggerRef.current?.focus()
  }

  // Patrón ARIA de menú: al abrir, foco en la primera opción; flechas, Inicio/Fin, Esc y Tab.
  useEffect(() => {
    if (open) items()[0]?.focus()
  }, [open])

  const onMenuKeyDown = (e) => {
    const list = items()
    const i = list.indexOf(document.activeElement)
    const go = (n) => {
      e.preventDefault()
      list[(n + list.length) % list.length]?.focus()
    }
    if (e.key === 'ArrowDown') go(i + 1)
    else if (e.key === 'ArrowUp') go(i - 1)
    else if (e.key === 'Home') go(0)
    else if (e.key === 'End') go(list.length - 1)
    else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      closeAndFocus()
    } else if (e.key === 'Tab') setOpen(false)
  }

  useEffect(() => savePref('exportGeneric', generic), [generic])

  useEffect(() => {
    if (!open) return
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const esc = (e) => e.key === 'Escape' && closeAndFocus()
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (fn) => {
    setOpen(false)
    setBusy(true)
    try {
      await fn()
    } finally {
      setBusy(false)
      triggerRef.current?.focus()
    }
  }

  const item = (fmt, handler) => {
    const Icon = fmt.icon
    return (
      <button
        key={fmt.id}
        type="button"
        role="menuitem"
        tabIndex={-1}
        onClick={() => run(handler)}
        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm text-slate-700 outline-none hover:bg-slate-100 focus-visible:bg-slate-100 focus-visible:ring-2 focus-visible:ring-teal-600 dark:text-slate-200 dark:hover:bg-slate-800 dark:focus-visible:bg-slate-800"
      >
        <Icon className="h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
        {t(`exportFormats.${fmt.id}`)}
      </button>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <Button
        ref={triggerRef}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && !open) {
            e.preventDefault()
            setOpen(true)
          }
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-busy={busy || undefined}
        disabled={busy}
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Download className="h-4 w-4" aria-hidden />}
        {t('exportLabel')}
        <ChevronDown className={cx('h-3.5 w-3.5 transition', open && 'rotate-180')} aria-hidden />
      </Button>
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={t('exportLabel')}
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 z-30 mt-1.5 w-72 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
            {t('exportCurrent')}
          </div>
          {FORMATS.map((fmt) => item(fmt, () => onExport(fmt.id)))}
          {pdfAvailable && item(PDF_FORMAT, () => onExport(PDF_FORMAT.id))}

          {doneCount > 1 && (
            <>
              <div className="my-1.5 border-t border-slate-100 dark:border-slate-800" />
              <div className="px-2.5 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
                {t('exportAll', doneCount)}
              </div>
              {FORMATS.map((fmt) => item(fmt, () => onExportAll(fmt.id, generic)))}
              {pdfCount > 0 && item(PDF_FORMAT, () => onExportAll(PDF_FORMAT.id, generic))}
              <button
                type="button"
                role="menuitemcheckbox"
                aria-checked={generic}
                tabIndex={-1}
                onClick={() => setGeneric((v) => !v)}
                className="mt-1 flex w-full cursor-pointer items-start gap-2 rounded-md px-2.5 py-1.5 text-left outline-none hover:bg-slate-50 focus-visible:bg-slate-100 focus-visible:ring-2 focus-visible:ring-teal-600 dark:hover:bg-slate-800/60 dark:focus-visible:bg-slate-800"
              >
                <span
                  aria-hidden
                  className={cx(
                    'mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border',
                    generic ? 'border-teal-700 bg-teal-700 text-white dark:border-teal-400 dark:bg-teal-400 dark:text-slate-950' : 'border-slate-400 dark:border-slate-500',
                  )}
                >
                  {generic && <Check className="h-3 w-3" />}
                </span>
                <span>
                  <span className="block text-xs font-medium text-slate-700 dark:text-slate-200">
                    {t('exportGeneric')}
                  </span>
                  <span className="block text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                    {t('exportGenericHint')}
                  </span>
                </span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
