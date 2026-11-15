import { Loader2, ScanText, X } from 'lucide-react'
import { useI18n } from '../i18n.jsx'

// Indicador dinámico del lote en curso: avance global + archivo/página/etapa actual.
export default function JobProgress({ job, items, onCancel }) {
  const { t } = useI18n()
  if (!job) return null

  const current = items.find((i) => i.id === job.current)
  const total = job.total || items.length || 1
  const fraction = current?.pages ? current.page / current.pages : 0
  const percent = Math.min(100, Math.round(((job.completed + fraction) / total) * 100))
  const ocr = current?.stage === 'ocr'

  let detail = ''
  if (current) {
    detail = `${current.name} — ${t(`stage.${current.stage || 'text'}`)}`
    if (current.pages && current.stage !== 'anonymize') detail += ` · ${t('pageOf', current.page, current.pages)}`
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-teal-200 bg-white px-4 py-3 shadow-sm dark:border-teal-500/30 dark:bg-slate-900"
    >
      <div className="flex items-center gap-3">
        {ocr ? (
          <ScanText className="h-5 w-5 shrink-0 animate-pulse text-sky-600" />
        ) : (
          <Loader2 className="h-5 w-5 shrink-0 animate-spin text-teal-600" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              {t('jobProgress', job.completed, total)}
            </span>
            <span className="font-mono text-xs text-slate-500">{percent}%</span>
          </div>
          <div className="truncate text-xs text-slate-500 dark:text-slate-400">{detail || ' '}</div>
        </div>
        <button
          type="button"
          onClick={onCancel}
          title={t('cancel')}
          aria-label={t('cancel')}
          className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div
          className="h-full rounded-full bg-teal-500 transition-[width] duration-300 dark:bg-teal-400"
          style={{ width: `${Math.max(percent, 3)}%` }}
        />
      </div>
    </div>
  )
}
