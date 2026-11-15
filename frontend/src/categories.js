// Colores por categoría de dato (resaltado en la vista y chips de la lista).
const palette = {
  rose: 'bg-rose-100 text-rose-800 ring-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-500/30',
  orange: 'bg-orange-100 text-orange-800 ring-orange-200 dark:bg-orange-500/15 dark:text-orange-300 dark:ring-orange-500/30',
  violet: 'bg-violet-100 text-violet-800 ring-violet-200 dark:bg-violet-500/15 dark:text-violet-300 dark:ring-violet-500/30',
  amber: 'bg-amber-100 text-amber-800 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/30',
  sky: 'bg-sky-100 text-sky-800 ring-sky-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/30',
  cyan: 'bg-cyan-100 text-cyan-800 ring-cyan-200 dark:bg-cyan-500/15 dark:text-cyan-300 dark:ring-cyan-500/30',
  emerald: 'bg-emerald-100 text-emerald-800 ring-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-500/30',
  slate: 'bg-slate-200 text-slate-800 ring-slate-300 dark:bg-slate-500/20 dark:text-slate-200 dark:ring-slate-500/30',
}

const byCategory = {
  PATIENT: palette.rose,
  PERSON: palette.orange,
  PROFESSIONAL: palette.violet,
  ID: palette.amber,
  RECORD: palette.amber,
  BIRTHDATE: palette.sky,
  DATE: palette.sky,
  PHONE: palette.cyan,
  EMAIL: palette.cyan,
  URL: palette.cyan,
  IP: palette.cyan,
  ADDRESS: palette.emerald,
  CUSTOM: palette.slate,
}

export function categoryClass(category) {
  return byCategory[category] ?? palette.slate
}
