import { SlidersHorizontal } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { Button, Card, Segmented, Toggle } from './ui.jsx'

export default function OptionsPanel({ options, onChange, customDraft, onCustomDraftChange, onApplyCustom }) {
  const { t } = useI18n()
  const set = (key) => (value) => onChange({ ...options, [key]: value })
  const customDirty = customDraft.trim() !== (options.custom_terms || []).join('\n').trim()

  return (
    <Card title={t('optionsTitle')} icon={SlidersHorizontal}>
      <div className="space-y-4 p-4">
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">
            {t('docLanguage')}
          </span>
          <select
            value={options.language}
            onChange={(e) => set('language')(e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700 outline-none focus:border-teal-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            <option value="auto">{t('langAuto')}</option>
            <option value="es">{t('langEs')}</option>
            <option value="en">{t('langEn')}</option>
          </select>
        </label>

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

        <div>
          <label htmlFor="custom-terms" className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
            {t('customTerms')}
          </label>
          <textarea
            id="custom-terms"
            value={customDraft}
            onChange={(e) => onCustomDraftChange(e.target.value)}
            placeholder={t('customTermsPlaceholder')}
            rows={3}
            spellCheck={false}
            className="w-full resize-y rounded-lg border border-slate-200 bg-slate-50 p-2 text-sm text-slate-800 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          />
          <div className="mt-1.5 flex items-start justify-between gap-2">
            <p className="text-[11px] leading-snug text-slate-400 dark:text-slate-500">{t('customTermsHint')}</p>
            <Button onClick={onApplyCustom} disabled={!customDirty} className="shrink-0 px-2.5 py-1 text-xs">
              {t('apply')}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}
