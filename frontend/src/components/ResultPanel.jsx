import { useMemo, useState } from 'react'
import { Check, Copy, Eye, EyeOff, FileCheck2, Loader2, Pencil, ScanEye, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { categoryClass } from '../categories.js'
import { Button, Card, cx } from './ui.jsx'
import ExportMenu from './ExportMenu.jsx'

const PLACEHOLDER_RE = /(\[[A-Z][A-Z_]*\d*\])/g

// Resalta los marcadores ([PACIENTE_1]...) por categoría. Con `showOriginal`, cada marcador muestra
// el valor original (para revisar qué se ocultó); sólo en pantalla: copiar y exportar usan siempre
// el texto anonimizado.
export function Highlighted({ text, entities, showOriginal = false, categoryLabel = (c) => c }) {
  const map = useMemo(() => {
    const m = new Map()
    for (const e of entities || []) m.set(e.placeholder, e)
    return m
  }, [entities])

  const parts = useMemo(() => text.split(PLACEHOLDER_RE), [text])
  return (
    <>
      {parts.map((part, i) => {
        const entity = i % 2 === 1 ? map.get(part) : undefined
        if (!entity) return <span key={i}>{part}</span>
        const original = (entity.values || []).join(' / ')
        const label = categoryLabel(entity.category)
        return (
          <mark
            key={i}
            data-placeholder={part}
            title={showOriginal ? `${part} · ${label}` : label}
            className={cx(
              'rounded px-1 py-px font-semibold ring-1 ring-inset',
              categoryClass(entity.category),
              showOriginal && original && 'underline decoration-dotted underline-offset-2',
            )}
          >
            {showOriginal && original ? original : part}
          </mark>
        )
      })}
    </>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-1.5 dark:bg-slate-800/60">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-600 dark:text-slate-400">{label}</div>
      <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{value}</div>
    </div>
  )
}

export default function ResultPanel({
  result,
  title,
  text,
  onTextChange,
  edited,
  loading,
  updating,
  onCopy,
  copied,
  onExport,
  onExportAll,
  doneCount,
}) {
  const { t } = useI18n()
  const [view, setView] = useState('preview')
  const [showOriginal, setShowOriginal] = useState(false)
  const canShowOriginal = view === 'preview' && !edited && (result?.entities?.length ?? 0) > 0
  const revealing = showOriginal && canShowOriginal

  const actions = result && (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => setShowOriginal((v) => !v)}
        disabled={!canShowOriginal}
        aria-pressed={revealing}
        title={t('showOriginalHint')}
        data-testid="toggle-original"
        className={cx(
          'flex items-center gap-1 rounded-lg border px-2 py-1 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 disabled:cursor-not-allowed disabled:opacity-50',
          revealing
            ? 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-100'
            : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700',
        )}
      >
        {revealing ? <EyeOff className="h-3.5 w-3.5" aria-hidden /> : <ScanEye className="h-3.5 w-3.5" aria-hidden />}
        {t('showOriginal')}
      </button>
      <div role="group" aria-label={t('viewMode')} className="flex rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800">
        {[
          { id: 'preview', icon: Eye, label: t('viewHighlighted') },
          { id: 'edit', icon: Pencil, label: t('viewEdit') },
        ].map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setView(id)}
            aria-pressed={view === id}
            className={cx(
              'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600',
              view === id
                ? 'bg-white text-teal-800 shadow-sm dark:bg-slate-950 dark:text-teal-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200',
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden /> {label}
          </button>
        ))}
      </div>
      <ExportMenu onExport={onExport} onExportAll={onExportAll} doneCount={doneCount} />
      <Button variant="primary" onClick={onCopy} data-testid="copy-result">
        {copied ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
        {copied ? t('copied') : t('copy')}
      </Button>
    </div>
  )

  return (
    <Card
      title={
        <span className="flex min-w-0 items-center gap-2">
          <span className="shrink-0">{t('resultTitle')}</span>
          {title && <span className="truncate font-normal text-slate-600 dark:text-slate-400">· {title}</span>}
          {updating && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-teal-600" aria-label={t('updating')} />}
        </span>
      }
      icon={FileCheck2}
      actions={actions}
      className="flex min-h-0 flex-1 flex-col"
    >
      {result && (
        <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-2.5 dark:border-slate-800">
          <Stat label={t('statPages')} value={result.pages} />
          <Stat label={t('statReplacements')} value={result.replacements} />
          <Stat label={t('statLanguage')} value={result.language.toUpperCase()} />
          <Stat label={t('statTime')} value={`${result.elapsed_ms} ms`} />
          {edited && (
            <p className="flex items-center text-xs text-amber-600 dark:text-amber-400">{t('editedNotice')}</p>
          )}
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 backdrop-blur-[1px] dark:bg-slate-900/70">
            <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-600 shadow dark:bg-slate-800 dark:text-slate-200">
              <Loader2 className="h-4 w-4 animate-spin text-teal-600" /> {t('processing')}
            </div>
          </div>
        )}

        {!result ? (
          <div className="flex h-full min-h-72 flex-col items-center justify-center gap-3 p-8 text-center">
            <div className="rounded-2xl bg-teal-50 p-4 dark:bg-teal-500/10">
              <ShieldCheck className="h-10 w-10 text-teal-600 dark:text-teal-400" />
            </div>
            <h3 className="text-base font-semibold text-slate-700 dark:text-slate-200">{t('emptyResultTitle')}</h3>
            <p className="max-w-sm text-sm text-slate-500 dark:text-slate-400">{t('emptyResultText')}</p>
          </div>
        ) : view === 'edit' ? (
          <textarea
            value={text}
            onChange={(e) => onTextChange(e.target.value)}
            spellCheck={false}
            className="absolute inset-0 h-full w-full resize-none bg-transparent p-4 font-mono text-[13px] leading-relaxed text-slate-800 outline-none dark:text-slate-200"
          />
        ) : (
          <div className="absolute inset-0 flex flex-col">
            {revealing && (
              <p
                role="status"
                className="flex shrink-0 items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100"
              >
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                {t('showingOriginal')}
              </p>
            )}
            <pre
              tabIndex={0}
              aria-label={t('resultTitle')}
              className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-[13px] leading-relaxed text-slate-800 select-text focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-600 dark:text-slate-200"
            >
              <Highlighted
                text={text}
                entities={result.entities}
                showOriginal={revealing}
                categoryLabel={(c) => t(`categories.${c}`)}
              />
            </pre>
          </div>
        )}
      </div>
    </Card>
  )
}
