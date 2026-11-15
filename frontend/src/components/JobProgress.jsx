import { Cpu, Loader2, ScanText, X } from 'lucide-react'
import { useI18n } from '../i18n.jsx'

function formatEta(seconds, t) {
  if (seconds == null) return null
  if (seconds < 5) return t('etaSoon')
  const s = Math.round(seconds)
  if (s < 60) return t('etaSeconds', s)
  const m = Math.floor(s / 60)
  return t('etaMinutes', m, s % 60)
}

// Indicador dinámico del lote en curso: avance global ponderado, archivos en proceso, procesos
// en paralelo, tiempo restante estimado y cancelación.
export default function JobProgress({ job, items, onCancel }) {
  const { t } = useI18n()
  if (!job) return null

  const byId = new Map(items.map((i) => [i.id, i]))
  const active = (job.active?.length ? job.active : job.current ? [job.current] : [])
    .map((id) => byId.get(id))
    .filter(Boolean)
  const total = job.total || items.length || 1
  const fraction = active.reduce((acc, i) => acc + (i.pages ? Math.min(i.page, i.pages) / i.pages : 0), 0)
  const percent = Math.min(100, Math.round(((job.completed + fraction) / total) * 100))
  const ocr = active.some((i) => i.stage === 'ocr')
  const eta = formatEta(job.eta_seconds, t)

  const describe = (i) => {
    let text = `${i.name} — ${t(`stage.${i.stage || 'text'}`)}`
    if (i.pages && i.stage !== 'anonymize') text += ` · ${t('pageOf', i.page, i.pages)}`
    return text
  }

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="rounded-xl border border-teal-200 bg-white px-4 py-3 shadow-sm dark:border-teal-500/30 dark:bg-slate-900"
    >
      <div className="flex items-start gap-3">
        {ocr ? (
          <ScanText className="mt-0.5 h-5 w-5 shrink-0 animate-pulse text-sky-600" aria-hidden />
        ) : (
          <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-teal-600" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              {job.cancelling
                ? t('cancelling')
                : active.length > 1
                  ? t('jobProgressParallel', active.length, job.completed, total)
                  : t('jobProgress', job.completed, total)}
            </span>
            <span className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
              {job.mode === 'parallel' && (
                <span className="flex items-center gap-1" title={t('parallelWorkersHint')}>
                  <Cpu className="h-3.5 w-3.5" aria-hidden /> {t('parallelWorkers', job.workers)}
                </span>
              )}
              {eta && !job.cancelling && <span>{eta}</span>}
              <span className="font-mono">{percent}%</span>
            </span>
          </div>
          <ul className="mt-0.5 space-y-0.5">
            {active.length ? (
              active.map((i) => (
                <li key={i.id} className="truncate text-xs text-slate-500 dark:text-slate-400">
                  {describe(i)}
                </li>
              ))
            ) : (
              <li className="text-xs text-slate-400">{t('status.queued')}…</li>
            )}
          </ul>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={job.cancelling}
          className="flex shrink-0 items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <X className="h-3.5 w-3.5" aria-hidden /> {t('cancel')}
        </button>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div
          className="h-full rounded-full bg-teal-500 transition-[width] duration-300 dark:bg-teal-400"
          style={{ width: `${Math.max(percent, 3)}%` }}
        />
      </div>
    </div>
  )
}
