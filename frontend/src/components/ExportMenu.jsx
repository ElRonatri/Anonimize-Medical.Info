import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Download, FileCode2, FileJson, FileText, FileType2, Loader2 } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { loadPref, savePref } from '../storage.js'
import { Button, cx } from './ui.jsx'

const FORMATS = [
  { id: 'md', icon: FileCode2 },
  { id: 'txt', icon: FileText },
  { id: 'docx', icon: FileType2 },
  { id: 'json', icon: FileJson },
]

export default function ExportMenu({ onExport, onExportAll, doneCount }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [generic, setGeneric] = useState(() => loadPref('exportGeneric', false))
  const ref = useRef(null)

  useEffect(() => savePref('exportGeneric', generic), [generic])

  useEffect(() => {
    if (!open) return
    const close = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const run = async (fn) => {
    setOpen(false)
    setBusy(true)
    try {
      await fn()
    } finally {
      setBusy(false)
    }
  }

  const item = (fmt, handler) => {
    const Icon = fmt.icon
    return (
      <button
        key={fmt.id}
        type="button"
        role="menuitem"
        onClick={() => run(handler)}
        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        <Icon className="h-4 w-4 text-slate-400" />
        {t(`exportFormats.${fmt.id}`)}
      </button>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <Button onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open} disabled={busy}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {t('exportLabel')}
        <ChevronDown className={cx('h-3.5 w-3.5 transition', open && 'rotate-180')} />
      </Button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-30 mt-1.5 w-72 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            {t('exportCurrent')}
          </div>
          {FORMATS.map((fmt) => item(fmt, () => onExport(fmt.id)))}

          {doneCount > 1 && (
            <>
              <div className="my-1.5 border-t border-slate-100 dark:border-slate-800" />
              <div className="px-2.5 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                {t('exportAll', doneCount)}
              </div>
              {FORMATS.map((fmt) => item(fmt, () => onExportAll(fmt.id, generic)))}
              <label className="mt-1 flex cursor-pointer items-start gap-2 rounded-md px-2.5 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/60">
                <input
                  type="checkbox"
                  checked={generic}
                  onChange={(e) => setGeneric(e.target.checked)}
                  className="mt-0.5 accent-teal-600"
                />
                <span>
                  <span className="block text-xs font-medium text-slate-700 dark:text-slate-200">
                    {t('exportGeneric')}
                  </span>
                  <span className="block text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                    {t('exportGenericHint')}
                  </span>
                </span>
              </label>
            </>
          )}
        </div>
      )}
    </div>
  )
}
