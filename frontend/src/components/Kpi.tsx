/**
 * Stat tile: label, value, optional context line. A status-linked tile carries a coloured
 * dot beside its label (identity from the mark, never from coloured text). Clickable
 * tiles act as shortcuts to the matching filter.
 */
export function Kpi({
  label,
  value,
  hint,
  dot,
  onClick,
  active,
  loading,
}: {
  label: string
  value: string
  hint?: string
  dot?: string
  onClick?: () => void
  active?: boolean
  loading?: boolean
}) {
  const body = (
    <>
      <div className="flex items-center gap-1.5 text-xs font-medium text-stone-500">
        {dot && <span className="size-2 rounded-full" style={{ backgroundColor: dot }} />}
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold tracking-tight text-stone-900 ${loading ? 'opacity-40' : ''}`}>
        {value}
      </div>
      {hint && <div className="mt-0.5 truncate text-xs text-stone-500">{hint}</div>}
    </>
  )
  const base = 'card px-4 py-3 text-left'
  if (!onClick) return <div className={base}>{body}</div>
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`${base} transition hover:border-stone-300 ${active ? 'border-brand-300 ring-2 ring-brand-100' : ''}`}
    >
      {body}
    </button>
  )
}
