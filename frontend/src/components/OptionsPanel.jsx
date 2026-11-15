import { useState } from 'react'
import { ScanText, ShieldOff, SlidersHorizontal } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { Button, Card, Segmented, Toggle, cx } from './ui.jsx'
import RegionSelect from './RegionSelect.jsx'

const selectClass =
  'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700 outline-none focus:border-teal-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200'

const ENGINE_LABELS = { tesseract: 'Tesseract', rapidocr: 'RapidOCR' }

function SectionTitle({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-1.5 border-t border-slate-100 pt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:border-slate-800">
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {children}
    </div>
  )
}

// Lista de términos (uno por línea) que se aplica con un botón, para no re-procesar en cada tecla.
function TermList({ id, label, hint, placeholder, value, onApply, tone = 'default' }) {
  const { t } = useI18n()
  const applied = (value || []).join('\n')
  const [draft, setDraft] = useState(applied)
  const [lastApplied, setLastApplied] = useState(applied)
  if (applied !== lastApplied) {
    // Cambió desde fuera (p. ej. preferencias restauradas): sincronizar el borrador.
    setLastApplied(applied)
    setDraft(applied)
  }
  const dirty = draft.trim() !== applied.trim()
  const apply = () =>
    onApply(
      draft
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
    )

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
        {label}
      </label>
      <textarea
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && (e.ctrlKey || e.metaKey) && apply()}
        placeholder={placeholder}
        rows={3}
        spellCheck={false}
        className={cx(
          'w-full resize-y rounded-lg border bg-slate-50 p-2 text-sm text-slate-800 outline-none focus:ring-2 dark:bg-slate-950 dark:text-slate-200',
          tone === 'allow'
            ? 'border-emerald-200 focus:border-emerald-500 focus:ring-emerald-500/20 dark:border-emerald-500/30'
            : 'border-slate-200 focus:border-teal-500 focus:ring-teal-500/20 dark:border-slate-700',
        )}
      />
      <div className="mt-1.5 flex items-start justify-between gap-2">
        <p className="text-[11px] leading-snug text-slate-400 dark:text-slate-500">{hint}</p>
        <Button onClick={apply} disabled={!dirty} className="shrink-0 px-2.5 py-1 text-xs">
          {t('apply')}
        </Button>
      </div>
    </div>
  )
}

export default function OptionsPanel({ options, onChange, info }) {
  const { t } = useI18n()
  const set = (key) => (value) => onChange({ ...options, [key]: value })
  const engines = info?.ocr?.engines ?? []
  const engineNames = engines
    .map((e) => (e === 'tesseract' && info?.ocr?.tesseract_languages ? `Tesseract (${info.ocr.tesseract_languages})` : ENGINE_LABELS[e]))
    .join(', ')

  return (
    <Card title={t('optionsTitle')} icon={SlidersHorizontal}>
      <div className="space-y-4 p-4">
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">
            {t('docLanguage')}
          </span>
          <select value={options.language} onChange={(e) => set('language')(e.target.value)} className={selectClass}>
            <option value="auto">{t('langAuto')}</option>
            <option value="es">{t('langEs')}</option>
            <option value="en">{t('langEn')}</option>
          </select>
        </label>

        <RegionSelect
          value={options.region}
          onChange={set('region')}
          regions={info?.regions}
          countryFormats={info?.country_formats}
        />

        <div className="grid grid-cols-2 gap-3">
          <Segmented
            label={t('outputFormat')}
            value={options.output_format}
            onChange={set('output_format')}
            options={[
              { value: 'markdown', label: t('formatMarkdown') },
              { value: 'text', label: t('formatText') },
            ]}
          />
          <Segmented
            label={t('replacementStyle')}
            value={options.replacement_style}
            onChange={set('replacement_style')}
            options={[
              { value: 'numbered', label: t('styleNumbered'), title: '[PACIENTE_1]' },
              { value: 'tag', label: t('styleTag'), title: '[PACIENTE]' },
            ]}
          />
        </div>

        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          <Toggle
            id="opt-professionals"
            checked={options.anonymize_professionals}
            onChange={set('anonymize_professionals')}
            label={t('optProfessionals')}
            hint={t('optProfessionalsHint')}
          />
          <Toggle
            id="opt-dates"
            checked={options.anonymize_all_dates}
            onChange={set('anonymize_all_dates')}
            label={t('optAllDates')}
            hint={t('optAllDatesHint')}
          />
          <Toggle
            id="opt-addresses"
            checked={options.anonymize_addresses}
            onChange={set('anonymize_addresses')}
            label={t('optAddresses')}
          />
          <Toggle
            id="opt-aggressive"
            checked={options.aggressive_numbers}
            onChange={set('aggressive_numbers')}
            label={t('optAggressive')}
            hint={t('optAggressiveHint')}
          />
          <Toggle
            id="opt-repeated"
            checked={options.remove_repeated}
            onChange={set('remove_repeated')}
            label={t('optRepeated')}
          />
          <Toggle
            id="opt-pages"
            checked={options.page_markers}
            onChange={set('page_markers')}
            label={t('optPageMarkers')}
          />
        </div>

        <SectionTitle icon={ScanText}>{t('ocrTitle')}</SectionTitle>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">{t('ocrMode')}</span>
            <select
              value={options.ocr_mode}
              onChange={(e) => set('ocr_mode')(e.target.value)}
              disabled={!engines.length}
              className={selectClass}
            >
              {['auto', 'force', 'off'].map((m) => (
                <option key={m} value={m}>
                  {t(`ocrModes.${m}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">{t('ocrEngine')}</span>
            <select
              value={options.ocr_engine}
              onChange={(e) => set('ocr_engine')(e.target.value)}
              disabled={engines.length < 2 || options.ocr_mode === 'off'}
              className={selectClass}
            >
              <option value="auto">{t('ocrEngineAuto')}</option>
              {engines.map((e) => (
                <option key={e} value={e}>
                  {ENGINE_LABELS[e] ?? e}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p
          className={cx(
            'text-[11px] leading-snug',
            engines.length ? 'text-slate-400 dark:text-slate-500' : 'text-amber-600 dark:text-amber-400',
          )}
        >
          {engines.length ? `${t('ocrStatusOk', engineNames)} ${t('ocrReloadHint')}` : t('ocrStatusNone')}
        </p>

        <SectionTitle icon={ShieldOff}>{t('sectionTerms')}</SectionTitle>
        <TermList
          id="whitelist-terms"
          label={t('whitelist')}
          hint={t('whitelistHint')}
          placeholder={t('whitelistPlaceholder')}
          value={options.whitelist}
          onApply={set('whitelist')}
          tone="allow"
        />
        <TermList
          id="custom-terms"
          label={t('customTerms')}
          hint={t('customTermsHint')}
          placeholder={t('customTermsPlaceholder')}
          value={options.custom_terms}
          onApply={set('custom_terms')}
        />
      </div>
    </Card>
  )
}
