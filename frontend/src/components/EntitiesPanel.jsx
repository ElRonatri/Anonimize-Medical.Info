import { useState } from 'react'
import { Eye, EyeOff, ListChecks, RotateCcw, Undo2 } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { categoryClass } from '../categories.js'
import { Card, cx } from './ui.jsx'

function mask(value) {
  return value.replace(/[\p{L}\p{N}]/gu, '•')
}

export default function EntitiesPanel({ entities, excluded, onExclude, onRestore }) {
  const { t } = useI18n()
  const [reveal, setReveal] = useState(false)

  const toggle = (
    <button
      type="button"
      onClick={() => setReveal((v) => !v)}
      title={reveal ? t('hideValues') : t('showValues')}
      aria-label={reveal ? t('hideValues') : t('showValues')}
      className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
    >
      {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
    </button>
  )

  return (
    <Card title={`${t('entitiesTitle')} (${entities.length})`} icon={ListChecks} actions={toggle}>
      <div className="max-h-48 overflow-auto p-2">
        {entities.length === 0 && excluded.length === 0 && (
          <p className="p-2 text-sm text-slate-500 dark:text-slate-400">{t('entitiesEmpty')}</p>
        )}
        <ul className="grid grid-cols-1 gap-1 xl:grid-cols-2">
          {entities.map((e) => (
            <li
              key={e.placeholder + e.values.join('|')}
              className="group flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/50"
            >
              <span
                className={cx(
                  'mt-0.5 shrink-0 rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold ring-1 ring-inset',
                  categoryClass(e.category),
                )}
              >
                {e.placeholder}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                  {t(`categories.${e.category}`)} · {t('occurrences', e.count)}
                </div>
                <div className="break-words text-sm text-slate-700 dark:text-slate-200">
                  {e.values.map((v) => (reveal ? v : mask(v))).join(' · ')}
                </div>
              </div>
              <button
                type="button"
                onClick={() => onExclude(e)}
                title={t('keepVisible')}
                aria-label={t('keepVisible')}
                className="shrink-0 rounded-md p-1 text-slate-400 opacity-0 transition hover:bg-slate-200 hover:text-slate-700 group-hover:opacity-100 focus:opacity-100 dark:hover:bg-slate-700 dark:hover:text-slate-200"
              >
                <Undo2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>

        {excluded.length > 0 && (
          <div className="mt-2 border-t border-slate-100 pt-2 dark:border-slate-800">
            <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
              {t('excludedTitle')}
            </div>
            <ul className="space-y-1">
              {excluded.map((e, i) => (
                <li key={i} className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm">
                  <span className="min-w-0 flex-1 truncate text-slate-500 line-through dark:text-slate-400">
                    {e.values.map((v) => (reveal ? v : mask(v))).join(' · ')}
                  </span>
                  <button
                    type="button"
                    onClick={() => onRestore(i)}
                    title={t('restore')}
                    aria-label={t('restore')}
                    className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-teal-700 dark:hover:bg-slate-800"
                  >
                    <RotateCcw className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}
