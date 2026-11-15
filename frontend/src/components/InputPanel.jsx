import { useState } from 'react'
import {
  Ban,
  CircleAlert,
  CircleCheck,
  Clock,
  FileText,
  FileUp,
  Loader2,
  Plus,
  ScanText,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { Button, Card, Segmented, cx } from './ui.jsx'

const ACCEPTED = /\.(pdf|txt)$/i

function StatusIcon({ item }) {
  const cls = 'h-4 w-4 shrink-0'
  switch (item.status) {
    case 'processing':
      return item.stage === 'ocr' ? (
        <ScanText className={cx(cls, 'animate-pulse text-sky-600')} />
      ) : (
        <Loader2 className={cx(cls, 'animate-spin text-teal-600')} />
      )
    case 'done':
      return <CircleCheck className={cx(cls, 'text-teal-600 dark:text-teal-400')} />
    case 'error':
      return <CircleAlert className={cx(cls, 'text-rose-600')} />
    case 'cancelled':
      return <Ban className={cx(cls, 'text-slate-400')} />
    default:
      return <Clock className={cx(cls, 'text-slate-400')} />
  }
}

function FileRow({ item, selected, onSelect, onRemove }) {
  const { t } = useI18n()
  const errorKey = `errors.${item.error}`
  const errorText = item.error ? (t(errorKey) === errorKey ? t('errors.generic') : t(errorKey)) : ''
  let detail = t(`status.${item.status}`)
  if (item.status === 'processing') {
    detail = t(`stage.${item.stage || 'text'}`)
    if (item.pages && item.stage !== 'anonymize') detail += ` · ${t('pageOf', item.page, item.pages)}`
  } else if (item.status === 'done' && item.pages) {
    detail = t('pages', item.pages)
  } else if (item.status === 'error') {
    detail = errorText
  }
  const percent = item.status === 'processing' && item.pages ? Math.round((item.page / item.pages) * 100) : 0

  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(item.id)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(item.id)}
        className={cx(
          'group relative flex cursor-pointer items-center gap-2 overflow-hidden rounded-lg px-2.5 py-2 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-teal-500/50',
          selected
            ? 'bg-teal-50 ring-1 ring-teal-200 dark:bg-teal-500/10 dark:ring-teal-500/30'
            : 'hover:bg-slate-50 dark:hover:bg-slate-800/60',
        )}
      >
        <StatusIcon item={item} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">{item.name}</div>
          <div
            className={cx(
              'truncate text-[11px]',
              item.status === 'error' ? 'text-rose-600 dark:text-rose-400' : 'text-slate-500 dark:text-slate-400',
            )}
          >
            {detail}
          </div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRemove(item.id)
          }}
          title={t('remove')}
          aria-label={t('remove')}
          disabled={item.status === 'processing'}
          className="rounded p-1 text-slate-400 opacity-0 transition hover:bg-slate-200 hover:text-slate-700 group-hover:opacity-100 focus:opacity-100 disabled:hidden dark:hover:bg-slate-700 dark:hover:text-slate-200"
        >
          <X className="h-3.5 w-3.5" />
        </button>
        {percent > 0 && (
          <span
            className="absolute bottom-0 left-0 h-0.5 bg-teal-500 transition-[width] duration-300"
            style={{ width: `${percent}%` }}
          />
        )}
      </div>
    </li>
  )
}

export default function InputPanel({
  mode,
  onModeChange,
  items,
  selectedId,
  onSelect,
  onRemove,
  onClear,
  busy,
  onPickFiles,
  onDropFiles,
  pasteText,
  onPasteTextChange,
  onSubmitText,
}) {
  const { t } = useI18n()
  const [dragging, setDragging] = useState(false)

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer?.files || []).filter((f) => ACCEPTED.test(f.name))
    if (files.length) onDropFiles(files)
  }

  const dropProps = {
    onDragOver: (e) => {
      e.preventDefault()
      setDragging(true)
    },
    onDragLeave: () => setDragging(false),
    onDrop: handleDrop,
  }

  const hasItems = items.length > 0

  return (
    <Card
      title={t('inputTitle')}
      icon={FileText}
      actions={
        hasItems && (
          <span className="text-xs text-slate-500 dark:text-slate-400">{t('filesCount', items.length)}</span>
        )
      }
    >
      <div className="space-y-3 p-4">
        <Segmented
          value={mode}
          onChange={onModeChange}
          options={[
            { value: 'file', label: t('tabFile') },
            { value: 'paste', label: t('tabPaste') },
          ]}
        />

        {mode === 'file' ? (
          <button
            type="button"
            onClick={onPickFiles}
            {...dropProps}
            className={cx(
              'group flex w-full flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-4 text-center transition',
              hasItems ? 'py-4' : 'py-7',
              dragging
                ? 'border-teal-500 bg-teal-50 dark:bg-teal-500/10'
                : 'border-slate-300 hover:border-teal-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:border-teal-500/60 dark:hover:bg-slate-800/50',
            )}
          >
            {hasItems ? (
              <Plus className="h-6 w-6 text-slate-400 transition group-hover:text-teal-600" />
            ) : (
              <FileUp className="h-8 w-8 text-slate-400 transition group-hover:text-teal-600" />
            )}
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              {dragging ? t('dropActive') : hasItems ? t('addFiles') : t('dropTitleMulti')}
            </span>
            {!dragging && !hasItems && (
              <>
                <span className="text-xs text-slate-500 dark:text-slate-400">{t('dropSubtitle')}</span>
                <span className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">{t('dropHint')}</span>
              </>
            )}
          </button>
        ) : (
          <div className="space-y-2" {...dropProps}>
            <textarea
              value={pasteText}
              onChange={(e) => onPasteTextChange(e.target.value)}
              placeholder={t('pastePlaceholder')}
              spellCheck={false}
              className="h-40 w-full resize-y rounded-xl border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-800 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
            />
            <Button variant="primary" className="w-full" onClick={onSubmitText} disabled={!pasteText.trim()}>
              <Sparkles className="h-4 w-4" />
              {t('anonymizeText')}
            </Button>
          </div>
        )}

        {hasItems && (
          <div>
            <ul className="max-h-64 space-y-1 overflow-y-auto pr-0.5">
              {items.map((item) => (
                <FileRow
                  key={item.id}
                  item={item}
                  selected={item.id === selectedId}
                  onSelect={onSelect}
                  onRemove={onRemove}
                />
              ))}
            </ul>
            <div className="mt-2 flex justify-end">
              <Button variant="ghost" className="px-2 py-1 text-xs" onClick={onClear} disabled={busy}>
                <Trash2 className="h-3.5 w-3.5" /> {t('clearAll')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
