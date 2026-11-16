import { Info, Languages, Moon, ShieldCheck, Sun } from 'lucide-react'
import { UI_LANGUAGES, useI18n } from '../i18n.jsx'

export default function Header({ theme, onToggleTheme, version, onOpenResponsible }) {
  const { t, lang, setLang } = useI18n()
  return (
    <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white/80 px-5 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-600 text-white shadow-sm dark:bg-teal-500 dark:text-slate-950">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold leading-tight text-slate-900 dark:text-white">
            Anonimize Medical
            {version && <span className="ml-2 text-xs font-normal text-slate-400">v{version}</span>}
          </h1>
          <p className="truncate text-xs text-slate-500 dark:text-slate-400">{t('appSubtitle')}</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onOpenResponsible}
          title={t('responsibleTitle')}
          aria-label={t('responsibleTitle')}
          aria-haspopup="dialog"
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          <Info className="h-4 w-4" aria-hidden />
          <span className="hidden md:inline">{t('responsibleTitle')}</span>
        </button>
        <label className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800">
          <Languages className="h-4 w-4 text-slate-500" aria-hidden />
          <span className="sr-only">{t('uiLanguage')}</span>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            className="cursor-pointer bg-transparent pr-1 text-sm text-slate-700 outline-none dark:text-slate-200"
          >
            {UI_LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="text-slate-900">
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onToggleTheme}
          title={t('themeToggle')}
          aria-label={t('themeToggle')}
          className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>
    </header>
  )
}
