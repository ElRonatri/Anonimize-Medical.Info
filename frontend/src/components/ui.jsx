export function cx(...classes) {
  return classes.filter(Boolean).join(' ')
}

export function Card({ title, icon: Icon, actions, children, className }) {
  return (
    <section
      className={cx(
        'rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900',
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <h2 className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
            {Icon && <Icon className="h-4 w-4 text-teal-600 dark:text-teal-400" />}
            {title}
          </h2>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function Toggle({ checked, onChange, label, hint, id }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start justify-between gap-3 py-1.5">
      <span className="min-w-0">
        <span className="block text-sm text-slate-700 dark:text-slate-200">{label}</span>
        {hint && <span className="block text-xs text-slate-500 dark:text-slate-400">{hint}</span>}
      </span>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input
          id={id}
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="h-5 w-9 rounded-full bg-slate-300 transition-colors peer-checked:bg-teal-600 peer-focus-visible:ring-2 peer-focus-visible:ring-teal-600 focus-visible:ring-offset-1 dark:focus-visible:ring-teal-400 dark:focus-visible:ring-offset-slate-900 dark:bg-slate-700 dark:peer-checked:bg-teal-500" />
        <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4" />
      </span>
    </label>
  )
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div>
      {label && <div className="mb-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">{label}</div>}
      <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            data-testid={`option-${opt.value}`}
            aria-pressed={value === opt.value}
            onClick={() => onChange(opt.value)}
            title={opt.title}
            className={cx(
              'rounded-md px-2 py-1.5 text-xs font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600',
              value === opt.value
                ? 'bg-white text-teal-800 shadow-sm dark:bg-slate-950 dark:text-teal-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function Button({ variant = 'secondary', className, children, ...props }) {
  const styles = {
    primary:
      // teal-700 + blanco = 5,5:1 (AA); teal-600 sólo llegaba a 3,7:1.
      'bg-teal-700 text-white hover:bg-teal-800 disabled:bg-teal-700/50 dark:bg-teal-400 dark:text-slate-950 dark:hover:bg-teal-300',
    secondary:
      'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700',
    ghost: 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
  }
  return (
    <button
      type="button"
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-1 dark:focus-visible:ring-teal-400 dark:focus-visible:ring-offset-slate-900 disabled:cursor-not-allowed',
        styles[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}
