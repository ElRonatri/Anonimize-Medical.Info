import { useMemo, useState } from 'react'
import { Check, Copy, Eye, FileCheck2, Loader2, Pencil, Save, ShieldCheck } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { categoryClass } from '../categories.js'
import { Button, Card, cx } from './ui.jsx'

const PLACEHOLDER_RE = /(\[[A-Z][A-Z_]*\d*\])/g

function Highlighted({ text, entities }) {
  const map = useMemo(() => {
    const m = new Map()
    for (const e of entities || []) m.set(e.placeholder, e.category)
    return m
  }, [entities])

  const parts = useMemo(() => text.split(PLACEHOLDER_RE), [text])
  return (
    <>
      {parts.map((part, i) => {
        const category = i % 2 === 1 ? map.get(part) : undefined
        return category ? (
          <mark key={i} className={cx('rounded px-1 py-px font-semibold ring-1 ring-inset', categoryClass(category))}>
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      })}
    </>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-1.5 dark:bg-slate-800/60">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{value}</div>
    </div>
  )
}

export default function ResultPanel({ result, text, onTextChange, edited, loading, onCopy, onSave, copied, saved }) {
  const { t } = useI18n()
  const [view, setView] = useState('preview')

  const actions = result && (
    <div className="flex items-center gap-2">
      <div className="flex rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800">
        {[
          { id: 'preview', icon: Eye, label: t('viewHighlighted') },
          { id: 'edit', icon: Pencil, label: t('viewEdit') },
        ].map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setView(id)}
            className={cx(
              'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium',
              view === id
                ? 'bg-white text-teal-700 shadow-sm dark:bg-slate-950 dark:text-teal-300'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200',
            )}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>
      <Button onClick={onSave}>
        {saved ? <Check className="h-4 w-4 text-teal-600" /> : <Save className="h-4 w-4" />}
        {saved ? t('saved') : t('save')}
      </Button>
      <Button variant="primary" onClick={onCopy}>
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        {copied ? t('copied') : t('copy')}
      </Button>
    </div>
  )

  return (
    <Card title={t('resultTitle')} icon={FileCheck2} actions={actions} className="flex min-h-0 flex-1 flex-col">
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
          <pre className="absolute inset-0 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-[13px] leading-relaxed text-slate-800 select-text dark:text-slate-200">
            <Highlighted text={text} entities={result.entities} />
          </pre>
        )}
      </div>
    </Card>
  )
}
