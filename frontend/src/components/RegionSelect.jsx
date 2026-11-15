import { useMemo } from 'react'
import { Globe2 } from 'lucide-react'
import { useI18n } from '../i18n.jsx'

const REGION_ORDER = ['latam', 'north_america', 'europe', 'asia']

function countryNamer(lang) {
  try {
    const names = new Intl.DisplayNames([lang], { type: 'region' })
    return (code) => names.of(code) || code
  } catch {
    return (code) => code
  }
}

// Selector desplegable de región / país para la detección de documentos de identidad.
export default function RegionSelect({ value, onChange, regions, countryFormats }) {
  const { t, lang } = useI18n()
  const nameOf = useMemo(() => countryNamer(lang), [lang])

  const groups = useMemo(
    () =>
      REGION_ORDER.filter((r) => regions?.[r]).map((r) => ({
        id: r,
        countries: [...regions[r]].sort((a, b) => nameOf(a).localeCompare(nameOf(b), lang)),
      })),
    [regions, nameOf, lang],
  )

  const isCountry = value && !['general', 'all', ...REGION_ORDER].includes(value)
  const formats = isCountry ? countryFormats?.[value] : null

  let hint = t('regionHintGeneral')
  if (value === 'all') hint = t('regionHintAll')
  else if (REGION_ORDER.includes(value)) hint = t('regionHintRegion')
  else if (isCountry) hint = formats?.length ? t('regionHintCountry', formats.join(', ')) : t('regionHintKeywordsOnly')

  return (
    <label className="block">
      <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">
        <Globe2 className="h-3.5 w-3.5" /> {t('region')}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-700 outline-none focus:border-teal-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
      >
        <option value="general">{t('regionGeneral')}</option>
        {groups.length > 0 && (
          <optgroup label={t('regionGroupRegions')}>
            <option value="all">{t('regionAll')}</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {t(`regions.${g.id}`)}
              </option>
            ))}
          </optgroup>
        )}
        {groups.map((g) => (
          <optgroup key={g.id} label={t(`regions.${g.id}`)}>
            {g.countries.map((code) => (
              <option key={code} value={code}>
                {nameOf(code)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <span className="mt-1 block text-[11px] leading-snug text-slate-400 dark:text-slate-500">{hint}</span>
    </label>
  )
}
