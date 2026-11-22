import { useMemo, useState } from 'react'
import { EyeOff, TriangleAlert } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { Button, Card, Toggle } from './ui.jsx'

// Igual que el backend: sin tildes, minúsculas y espacios normalizados.
const norm = (s) =>
  String(s)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .join(' ')

const parse = (text) =>
  text
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)

// Palabras a censurar: lo que el usuario escribe se oculta siempre (texto y PDF censurado).
// Con "Sólo estas palabras" se desactiva la detección automática. No se guardan al cerrar.
export default function CensorPanel({ terms, onlyCustom, onApply, onOnlyCustomChange, entities }) {
  const { t } = useI18n()
  const applied = (terms || []).join('\n')
  const [draft, setDraft] = useState(applied)
  const [lastApplied, setLastApplied] = useState(applied)
  if (applied !== lastApplied) {
    setLastApplied(applied)
    setDraft(applied)
  }
  const dirty = draft.trim() !== applied.trim()
  const apply = () => onApply(parse(draft))

  // Cuántas veces se ocultó cada palabra en el documento seleccionado (y cuáles no aparecen).
  const stats = useMemo(() => {
    if (!entities || !terms?.length) return null
    const custom = entities.filter((e) => e.category === 'CUSTOM')
    const count = custom.reduce((sum, e) => sum + (e.count || 0), 0)
    const found = new Set(custom.flatMap((e) => e.values.map(norm)))
    const missing = terms.filter((term) => !found.has(norm(term)))
    return { count, missing }
  }, [entities, terms])

  return (
    <Card title={t('censorTitle')} icon={EyeOff}>
      <div className="space-y-2 p-4">
        <label htmlFor="censor-terms" className="block text-xs font-medium text-slate-600 dark:text-slate-400">
          {t('censorLabel')}
        </label>
        <textarea
          id="censor-terms"
          data-testid="censor-terms"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.ctrlKey || e.metaKey) && apply()}
          placeholder={t('censorPlaceholder')}
          rows={4}
          spellCheck={false}
          aria-describedby="censor-hint"
          className="w-full resize-y rounded-lg border border-slate-200 bg-slate-50 p-2 text-sm text-slate-800 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
        />
        <div className="flex items-start justify-between gap-2">
          <p id="censor-hint" className="text-[11px] leading-snug text-slate-600 dark:text-slate-400">
            {t('censorHint')}
          </p>
          <Button onClick={apply} disabled={!dirty} className="shrink-0 px-2.5 py-1 text-xs" data-testid="censor-apply">
            {t('apply')}
          </Button>
        </div>

        {stats && (
          <p className="text-xs text-slate-700 dark:text-slate-300" role="status" data-testid="censor-stats">
            {t('censorFound', stats.count)}
            {stats.missing.length > 0 && ` ${t('censorMissing', stats.missing.join(', '))}`}
          </p>
        )}

        <Toggle
          id="only-custom"
          checked={onlyCustom}
          onChange={onOnlyCustomChange}
          label={t('censorOnly')}
          hint={t('censorOnlyHint')}
        />
        {onlyCustom && (
          <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            {t('censorOnlyWarning')}
          </p>
        )}
      </div>
    </Card>
  )
}
