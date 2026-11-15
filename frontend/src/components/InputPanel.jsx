import { useState } from 'react'
import { FileText, FileUp, Loader2, Sparkles } from 'lucide-react'
import { useI18n } from '../i18n.jsx'
import { Button, Card, Segmented, cx } from './ui.jsx'

export default function InputPanel({
  mode,
  onModeChange,
  source,
  loading,
  onPickFile,
  onDropFile,
  pasteText,
  onPasteTextChange,
  onSubmitText,
}) {
  const { t } = useI18n()
  const [dragging, setDragging] = useState(false)

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer?.files?.[0]
    if (file) onDropFile(file)
  }

  return (
    <Card title={t('inputTitle')} icon={FileText}>
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
            onClick={onPickFile}
            disabled={loading}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={cx(
              'group flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-7 text-center transition',
              dragging
                ? 'border-teal-500 bg-teal-50 dark:bg-teal-500/10'
                : 'border-slate-300 hover:border-teal-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:border-teal-500/60 dark:hover:bg-slate-800/50',
            )}
          >
            {loading ? (
              <Loader2 className="h-8 w-8 animate-spin text-teal-600" />
            ) : (
              <FileUp className="h-8 w-8 text-slate-400 transition group-hover:text-teal-600" />
            )}
            {source?.type === 'file' && !dragging ? (
              <>
                <span className="max-w-full truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {source.name}
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {source.pages ? t('pages', source.pages) + ' · ' : ''}
                  {t('changeFile')}
                </span>
              </>
            ) : (
              <>
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {dragging ? t('dropActive') : t('dropTitle')}
                </span>
                {!dragging && (
                  <span className="text-xs text-slate-500 dark:text-slate-400">{t('dropSubtitle')}</span>
                )}
                <span className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">{t('dropHint')}</span>
              </>
            )}
          </button>
        ) : (
          <div className="space-y-2">
            <textarea
              value={pasteText}
              onChange={(e) => onPasteTextChange(e.target.value)}
              placeholder={t('pastePlaceholder')}
              spellCheck={false}
              className="h-44 w-full resize-y rounded-xl border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-800 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
            />
            <Button
              variant="primary"
              className="w-full"
              onClick={onSubmitText}
              disabled={loading || !pasteText.trim()}
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {t('anonymizeText')}
            </Button>
          </div>
        )}
      </div>
    </Card>
  )
}
