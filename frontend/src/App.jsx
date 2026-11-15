import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Lock, TriangleAlert, X } from 'lucide-react'
import Header from './components/Header.jsx'
import InputPanel from './components/InputPanel.jsx'
import OptionsPanel from './components/OptionsPanel.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import EntitiesPanel from './components/EntitiesPanel.jsx'
import { backend, copyText, getApi } from './api.js'
import { useI18n } from './i18n.jsx'
import { loadPref, savePref } from './storage.js'

const DEFAULT_OPTIONS = {
  language: 'auto',
  output_format: 'markdown',
  replacement_style: 'numbered',
  anonymize_professionals: false,
  anonymize_all_dates: false,
  anonymize_addresses: true,
  remove_repeated: true,
  page_markers: true,
  custom_terms: [],
}

function initialTheme() {
  const saved = loadPref('theme')
  if (saved === 'dark' || saved === 'light') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function baseName(name) {
  return (name || 'documento').replace(/\.[^.]+$/, '')
}

export default function App() {
  const { t } = useI18n()
  const [theme, setTheme] = useState(initialTheme)
  const [info, setInfo] = useState(null)
  const [backendMissing, setBackendMissing] = useState(false)

  const [options, setOptions] = useState(() => ({ ...DEFAULT_OPTIONS, ...loadPref('options', {}) }))
  const [customDraft, setCustomDraft] = useState(() => (options.custom_terms || []).join('\n'))
  const [excluded, setExcluded] = useState([])

  const [mode, setMode] = useState('file')
  const [pasteText, setPasteText] = useState('')
  const [source, setSource] = useState(null)
  const [result, setResult] = useState(null)
  const [text, setText] = useState('')
  const [edited, setEdited] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null) // { kind: 'error' | 'warning', text }
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)

  const requestId = useRef(0)

  // ---------------------------------------------------------------- tema
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    savePref('theme', theme)
  }, [theme])

  // ---------------------------------------------------------------- backend
  useEffect(() => {
    getApi().then((api) => {
      if (!api) return setBackendMissing(true)
      backend.info().then((res) => res && !res.error && setInfo(res))
    })
    // Evita que soltar un archivo fuera de la zona navegue a él.
    const prevent = (e) => e.preventDefault()
    window.addEventListener('dragover', prevent)
    window.addEventListener('drop', prevent)
    return () => {
      window.removeEventListener('dragover', prevent)
      window.removeEventListener('drop', prevent)
    }
  }, [])

  useEffect(() => savePref('options', options), [options])

  const requestOptions = useMemo(
    () => ({ ...options, exclude: excluded.flatMap((e) => e.values) }),
    [options, excluded],
  )

  // ---------------------------------------------------------------- procesamiento
  const handleResponse = useCallback(
    (res, id, newSource) => {
      if (id !== requestId.current) return // respuesta obsoleta
      setLoading(false)
      if (!res?.ok) {
        if (res?.cancelled) return
        const key = `errors.${res?.error}`
        const msg = t(key) === key ? t('errors.generic') : t(key)
        setMessage({ kind: 'error', text: msg })
        return
      }
      setResult(res)
      setText(res.text)
      setEdited(false)
      if (newSource) setSource({ ...newSource, pages: res.pages })

      const warnings = (res.warnings || [])
        .map((w) => w.split(':')[0])
        .filter((w, i, arr) => arr.indexOf(w) === i)
        .map((w) => t(`warnings.${w}`))
      if (res.ocr_pages) warnings.push(t('warnings.ocr_used', res.ocr_pages))
      setMessage(warnings.length ? { kind: 'warning', text: warnings.join(' ') } : null)
    },
    [t],
  )

  const run = useCallback(
    async (fn, newSource) => {
      const id = ++requestId.current
      setLoading(true)
      setMessage(null)
      const res = await fn()
      handleResponse(res, id, newSource)
    },
    [handleResponse],
  )

  const pickFile = async () => {
    const path = await backend.openFileDialog()
    if (!path || typeof path !== 'string') {
      if (path?.error === 'no_backend') setMessage({ kind: 'error', text: t('errors.no_backend') })
      return
    }
    setExcluded([])
    const name = path.split(/[\\/]/).pop()
    run(() => backend.processFile(path, { ...options, exclude: [] }), { type: 'file', name })
  }

  const dropFile = (file) => {
    setExcluded([])
    run(() => backend.processDroppedFile(file, { ...options, exclude: [] }), { type: 'file', name: file.name })
  }

  const submitText = () => {
    setExcluded([])
    run(() => backend.processText(pasteText, { ...options, exclude: [] }), { type: 'text', name: 'texto' })
  }

  // Re-procesar al cambiar opciones o exclusiones (sin volver a leer el PDF).
  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    if (!source) return
    const timer = setTimeout(() => run(() => backend.reprocess(requestOptions)), 150)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestOptions])

  // ---------------------------------------------------------------- acciones
  const applyCustom = () => {
    const terms = customDraft
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    setOptions((o) => ({ ...o, custom_terms: terms }))
  }

  const copy = async () => {
    const ok = await copyText(text)
    if (ok) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } else {
      setMessage({ kind: 'error', text: t('errors.clipboard_error') })
    }
  }

  const save = async () => {
    const ext = result?.format === 'text' ? 'txt' : 'md'
    const res = await backend.save(text, `${baseName(source?.name)}_anonimizado.${ext}`)
    if (res?.ok) {
      setSaved(true)
      setTimeout(() => setSaved(false), 1800)
    } else if (!res?.cancelled) {
      setMessage({ kind: 'error', text: t(`errors.${res?.error}`) || t('errors.generic') })
    }
  }

  const exclude = (entity) => setExcluded((list) => [...list, { category: entity.category, values: entity.values }])
  const restore = (index) => setExcluded((list) => list.filter((_, i) => i !== index))

  // ---------------------------------------------------------------- render
  return (
    <div className="flex h-full flex-col">
      <Header theme={theme} onToggleTheme={() => setTheme((v) => (v === 'dark' ? 'light' : 'dark'))} version={info?.version} />

      {backendMissing && (
        <div className="border-b border-amber-200 bg-amber-50 px-5 py-2 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          {t('browserMode')}
        </div>
      )}

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-auto p-4 lg:grid-cols-[360px_minmax(0,1fr)] lg:overflow-hidden">
        <aside className="space-y-4 lg:min-h-0 lg:overflow-y-auto lg:pr-1">
          <InputPanel
            mode={mode}
            onModeChange={setMode}
            source={source}
            loading={loading}
            onPickFile={pickFile}
            onDropFile={dropFile}
            pasteText={pasteText}
            onPasteTextChange={setPasteText}
            onSubmitText={submitText}
          />
          <OptionsPanel
            options={options}
            onChange={setOptions}
            customDraft={customDraft}
            onCustomDraftChange={setCustomDraft}
            onApplyCustom={applyCustom}
          />
        </aside>

        <section className="flex min-h-[32rem] flex-col gap-4 lg:min-h-0">
          {message && (
            <div
              role="alert"
              className={
                message.kind === 'error'
                  ? 'flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300'
                  : 'flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300'
              }
            >
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="flex-1">{message.text}</span>
              <button type="button" onClick={() => setMessage(null)} className="opacity-60 hover:opacity-100">
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          <ResultPanel
            result={result}
            text={text}
            onTextChange={(v) => {
              setText(v)
              setEdited(true)
            }}
            edited={edited}
            loading={loading}
            onCopy={copy}
            onSave={save}
            copied={copied}
            saved={saved}
          />

          {result && (
            <EntitiesPanel entities={result.entities} excluded={excluded} onExclude={exclude} onRestore={restore} />
          )}

          <p className="flex items-start gap-1.5 px-1 text-xs text-slate-500 dark:text-slate-400">
            <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {t('privacyNote')}
          </p>
        </section>
      </main>
    </div>
  )
}
