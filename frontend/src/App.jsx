import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CircleCheck, Info, Lock, TriangleAlert, X } from 'lucide-react'
import Header from './components/Header.jsx'
import InputPanel from './components/InputPanel.jsx'
import OptionsPanel from './components/OptionsPanel.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import EntitiesPanel from './components/EntitiesPanel.jsx'
import JobProgress from './components/JobProgress.jsx'
import ResponsibleUseDialog from './components/ResponsibleUseDialog.jsx'
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
  region: 'general',
  aggressive_numbers: false,
  ocr_mode: 'auto',
  ocr_engine: 'auto',
  max_workers: 'auto',
  ner: false,
  ner_orgs: false,
  ner_threshold: 0.8,
  custom_terms: [],
  whitelist: [],
}

const POLL_MS = 250

// Privacidad: las preferencias se guardan (prefs.json, vía backend), pero NUNCA los términos a
// ocultar (suelen ser nombres de pacientes): sólo viven durante la sesión. El backend además
// descarta cualquier clave que no esté en su lista (backend/appdata.py).
function persistable({ custom_terms: _sessionOnly, ...rest }) {
  return rest
}

function initialTheme() {
  const saved = loadPref('theme')
  if (saved === 'dark' || saved === 'light') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const ocrKeyOf = (o) => `${o.ocr_mode}|${o.ocr_engine}`

export default function App() {
  const { t } = useI18n()
  const [theme, setTheme] = useState(initialTheme)
  const [info, setInfo] = useState(null)
  const [backendMissing, setBackendMissing] = useState(false)

  const [options, setOptions] = useState(() => ({ ...DEFAULT_OPTIONS, ...persistable(loadPref('options', {})) }))
  const [excluded, setExcluded] = useState([])

  const [mode, setMode] = useState('file')
  const [pasteText, setPasteText] = useState('')

  // Documentos: estado por archivo, resultado y texto (editable) por id.
  const [items, setItems] = useState([])
  const [results, setResults] = useState({})
  const [drafts, setDrafts] = useState({})
  const [selectedId, setSelectedId] = useState(null)
  const [job, setJob] = useState(null) // { id, total, completed, current }
  const [updating, setUpdating] = useState(false)

  const [message, setMessage] = useState(null) // { kind: 'error' | 'warning' | 'success', text }
  const [copied, setCopied] = useState(false)

  // Privacidad y uso responsable: diálogo de primer uso (sólo se guarda "no volver a mostrar")
  // y recordatorio, una vez por sesión, al copiar o exportar por primera vez.
  const [dontShowResponsible, setDontShowResponsible] = useState(() => loadPref('responsibleUseDismissed', false) === true)
  const [responsibleOpen, setResponsibleOpen] = useState(() => loadPref('responsibleUseDismissed', false) !== true)
  const reminderShown = useRef(false)

  const resultsRef = useRef(results)
  resultsRef.current = results
  const appliedKey = useRef('') // opciones con las que se calcularon los resultados actuales
  const appliedOcrKey = useRef('')
  const pastedCount = useRef(0)

  // ---------------------------------------------------------------- tema / backend
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    savePref('theme', theme)
  }, [theme])

  useEffect(() => {
    getApi().then((api) => {
      if (!api) return setBackendMissing(true)
      backend.info().then((res) => res && !res.error && setInfo(res))
    })
    const prevent = (e) => e.preventDefault() // soltar fuera de la zona no debe navegar al archivo
    window.addEventListener('dragover', prevent)
    window.addEventListener('drop', prevent)
    return () => {
      window.removeEventListener('dragover', prevent)
      window.removeEventListener('drop', prevent)
    }
  }, [])

  useEffect(() => savePref('options', persistable(options)), [options])

  const requestOptions = useMemo(
    () => ({ ...options, exclude: excluded.flatMap((e) => e.values) }),
    [options, excluded],
  )
  // max_workers sólo afecta a lotes nuevos: no requiere re-anonimizar lo ya procesado.
  const optionsKey = JSON.stringify({ ...requestOptions, max_workers: undefined })

  // ---------------------------------------------------------------- utilidades de estado
  const errorText = useCallback(
    (code) => {
      const key = `errors.${code}`
      return t(key) === key ? t('errors.generic') : t(key)
    },
    [t],
  )

  const mergeItems = useCallback((updates) => {
    if (!updates?.length) return
    const byId = Object.fromEntries(updates.map((u) => [u.id, u]))
    setItems((prev) => prev.map((it) => (byId[it.id] ? { ...it, ...byId[it.id] } : it)))
  }, [])

  const applyResults = useCallback((map) => {
    const entries = Object.entries(map || {}).filter(([, r]) => r?.ok)
    if (!entries.length) return
    setResults((prev) => ({ ...prev, ...Object.fromEntries(entries) }))
    setDrafts((prev) => ({
      ...prev,
      ...Object.fromEntries(entries.map(([id, r]) => [id, { text: r.text, edited: false }])),
    }))
  }, [])

  // ---------------------------------------------------------------- lotes
  const startJob = useCallback(
    (res, { append }) => {
      if (!res?.ok) {
        setMessage({ kind: 'error', text: errorText(res?.error) })
        return
      }
      appliedKey.current = optionsKey
      appliedOcrKey.current = ocrKeyOf(options)
      if (append) {
        setItems((prev) => [...prev, ...res.items.map((i) => ({ ...i, kind: 'file' }))])
        setSelectedId((cur) => cur ?? res.items[0]?.id ?? null)
      } else {
        mergeItems(res.items)
      }
      setJob({ id: res.job_id, total: res.items.length, completed: 0, current: null })
    },
    [errorText, mergeItems, optionsKey, options],
  )

  const pickFiles = async () => {
    const paths = await backend.openFileDialog()
    if (paths?.error) return setMessage({ kind: 'error', text: errorText(paths.error) })
    if (!Array.isArray(paths) || !paths.length) return
    setMessage(null)
    startJob(await backend.startBatchPaths(paths, requestOptions), { append: true })
  }

  const dropFiles = async (files) => {
    setMessage(null)
    startJob(await backend.startBatchFiles(files, requestOptions), { append: true })
  }

  const submitText = async () => {
    const res = await backend.processText(pasteText, requestOptions)
    if (!res?.ok) return setMessage({ kind: 'error', text: errorText(res?.error) })
    pastedCount.current += 1
    appliedKey.current = optionsKey
    setItems((prev) => [...prev, { ...res.item, name: t('pastedText', pastedCount.current), kind: 'text' }])
    applyResults({ [res.item.id]: res.result })
    setSelectedId(res.item.id)
    setMessage(null)
  }

  // Consulta periódica del avance mientras el backend procesa en su hilo secundario.
  useEffect(() => {
    if (!job?.id) return undefined
    let stopped = false
    let timer
    const tick = async () => {
      const state = await backend.getJob(job.id, Object.keys(resultsRef.current))
      if (stopped) return
      if (!state?.ok) {
        setJob(null)
        return
      }
      mergeItems(state.items)
      applyResults(state.results)
      if (state.done) {
        setJob(null)
        const errors = state.items.filter((i) => i.status === 'error').length
        const done = state.items.filter((i) => i.status === 'done').length
        if (state.items.length > 1 || errors) {
          setMessage(
            errors
              ? { kind: 'warning', text: `${t('jobDone', done)} · ${errors} ${t('status.error').toLowerCase()}` }
              : { kind: 'success', text: t('jobDone', done) },
          )
        }
        return
      }
      setJob((j) =>
        j?.id === job.id
          ? {
              ...j,
              total: state.total,
              completed: state.completed,
              current: state.current,
              active: state.active,
              workers: state.workers,
              mode: state.mode,
              eta_seconds: state.eta_seconds,
            }
          : j,
      )
      timer = setTimeout(tick, POLL_MS)
    }
    timer = setTimeout(tick, 80)
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [job?.id, mergeItems, applyResults, t])

  // Al cambiar opciones: re-anonimizar en memoria (ms) o, si cambió el OCR, releer archivos.
  const hasDone = items.some((i) => i.status === 'done')
  useEffect(() => {
    if (job || !hasDone || optionsKey === appliedKey.current) return undefined
    const timer = setTimeout(async () => {
      const ocrKey = ocrKeyOf(options)
      const fileIds = items.filter((i) => i.kind === 'file' && i.status === 'done').map((i) => i.id)
      if (ocrKey !== appliedOcrKey.current && fileIds.length) {
        startJob(await backend.reloadItems(fileIds, requestOptions), { append: false })
        return
      }
      appliedOcrKey.current = ocrKey
      appliedKey.current = optionsKey
      setUpdating(true)
      const res = await backend.reprocess(requestOptions)
      setUpdating(false)
      if (res?.ok) applyResults(res.results)
      else setMessage({ kind: 'error', text: errorText(res?.error) })
    }, 150)
    return () => clearTimeout(timer)
  }, [optionsKey, job, hasDone]) // eslint-disable-line react-hooks/exhaustive-deps

  const cancelJob = () => {
    if (!job) return
    setJob((j) => (j ? { ...j, cancelling: true } : j))
    backend.cancelJob(job.id)
  }

  const removeItem = (id) => {
    backend.removeItems([id])
    setItems((prev) => {
      const next = prev.filter((i) => i.id !== id)
      if (selectedId === id) setSelectedId(next[0]?.id ?? null)
      return next
    })
    setResults(({ [id]: _r, ...rest }) => rest)
    setDrafts(({ [id]: _d, ...rest }) => rest)
  }

  const clearAll = () => {
    backend.removeItems(items.map((i) => i.id))
    setItems([])
    setResults({})
    setDrafts({})
    setSelectedId(null)
    setExcluded([])
    setMessage(null)
  }

  // ---------------------------------------------------------------- acciones sobre el resultado
  const selected = items.find((i) => i.id === selectedId) ?? null
  const result = selected ? results[selected.id] : null
  const draft = selected ? drafts[selected.id] : null
  const doneItems = items.filter((i) => results[i.id])

  const docPayload = (item) => {
    const { text: _text, ...meta } = results[item.id] || {}
    return { id: item.id, name: item.name, text: drafts[item.id]?.text ?? '', edited: !!drafts[item.id]?.edited, meta }
  }

  const closeResponsible = (dontShowAgain) => {
    setResponsibleOpen(false)
    setDontShowResponsible(dontShowAgain)
    savePref('responsibleUseDismissed', !!dontShowAgain)
  }

  // Devuelve el recordatorio la primera vez en la sesión (y null después).
  const takeReminder = () => {
    if (reminderShown.current) return null
    reminderShown.current = true
    return t('reviewReminder')
  }

  const copy = async () => {
    if (!draft) return
    if (await copyText(draft.text)) {
      const reminder = takeReminder()
      if (reminder) setMessage({ kind: 'info', text: reminder })
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } else {
      setMessage({ kind: 'error', text: t('errors.clipboard_error') })
    }
  }

  const exportOne = async (fmt) => {
    if (!selected || !result) return
    const res = await backend.exportFile(docPayload(selected), fmt, requestOptions)
    if (res?.ok) {
      const reminder = takeReminder()
      if (reminder) setMessage({ kind: 'info', text: reminder })
    } else if (!res?.cancelled) setMessage({ kind: 'error', text: errorText(res?.error) })
  }

  const exportAll = async (fmt, generic) => {
    const res = await backend.exportBatch(doneItems.map(docPayload), fmt, requestOptions, generic)
    if (res?.ok) {
      const reminder = takeReminder()
      const done = `${t('exportedMany', res.count)} ${res.folder}`
      setMessage({ kind: 'success', text: reminder ? `${done} ${reminder}` : done })
    }
    else if (!res?.cancelled) setMessage({ kind: 'error', text: errorText(res?.error) })
  }

  const exclude = (entity) => setExcluded((list) => [...list, { category: entity.category, values: entity.values }])
  const restore = (index) => setExcluded((list) => list.filter((_, i) => i !== index))

  // Avisos del documento seleccionado (OCR, páginas sin texto...).
  const docWarnings = useMemo(() => {
    if (!result) return []
    const list = (result.warnings || [])
      .map((w) => w.split(':')[0])
      .filter((w, i, arr) => arr.indexOf(w) === i)
      .map((w) => t(`warnings.${w}`))
    if (result.ocr_pages) list.push(t('warnings.ocr_used', result.ocr_pages))
    return list
  }, [result, t])

  const banner = message ?? (docWarnings.length ? { kind: 'warning', text: docWarnings.join(' ') } : null)
  const bannerStyles = {
    error: 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300',
    warning: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300',
    success: 'border-teal-200 bg-teal-50 text-teal-800 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-300',
    info: 'border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100',
  }
  const BannerIcon = banner?.kind === 'success' ? CircleCheck : banner?.kind === 'info' ? Info : TriangleAlert

  // ---------------------------------------------------------------- render
  return (
    <>
    {/* Con el diálogo abierto, el resto de la app queda inerte (ni foco ni lector de pantalla). */}
    <div className="flex h-full flex-col" inert={responsibleOpen || undefined}>
      <Header
        theme={theme}
        onToggleTheme={() => setTheme((v) => (v === 'dark' ? 'light' : 'dark'))}
        version={info?.version}
        onOpenResponsible={() => setResponsibleOpen(true)}
      />

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
            items={items}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onRemove={removeItem}
            onClear={clearAll}
            busy={!!job}
            onPickFiles={pickFiles}
            onDropFiles={dropFiles}
            pasteText={pasteText}
            onPasteTextChange={setPasteText}
            onSubmitText={submitText}
          />
          <OptionsPanel options={options} onChange={setOptions} info={info} />
        </aside>

        <section className="flex min-h-[32rem] flex-col gap-4 lg:min-h-0">
          <JobProgress job={job} items={items} onCancel={cancelJob} />

          {banner && (
            <div
              role={banner.kind === 'error' ? 'alert' : 'status'}
              className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-sm ${bannerStyles[banner.kind]}`}
            >
              <BannerIcon className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1 break-words">{banner.text}</span>
              {message && (
                <button type="button" onClick={() => setMessage(null)} className="opacity-60 hover:opacity-100">
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          <ResultPanel
            result={result}
            title={result ? selected?.name : null}
            text={draft?.text ?? ''}
            onTextChange={(v) => setDrafts((prev) => ({ ...prev, [selectedId]: { text: v, edited: true } }))}
            edited={!!draft?.edited}
            loading={!!selected && !result && ['queued', 'processing'].includes(selected.status)}
            updating={updating}
            onCopy={copy}
            copied={copied}
            onExport={exportOne}
            onExportAll={exportAll}
            doneCount={doneItems.length}
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
    <ResponsibleUseDialog open={responsibleOpen} dontShowAgain={dontShowResponsible} onClose={closeResponsible} />
    </>
  )
}
