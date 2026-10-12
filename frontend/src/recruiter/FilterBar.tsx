import { useEffect, useRef, useState } from 'react'
import type { AreaLabels, CandidateFilters } from '../api/client'
import { Icon } from '../components/Icon'
import { COUNTRY, RECRUITER_STATUS } from '../lib/labels'
import { hasActiveFilters } from '../lib/filters'
import { BUCKET_META, STATUS_META, STATUS_ORDER } from '../lib/status'

const SORTS = [
  { value: '-score', label: 'Prioridad' },
  { value: '-updated', label: 'Última actividad' },
  { value: '-created', label: 'Más recientes' },
  { value: 'created', label: 'Más antiguas' },
]

/** Sort control, shown in the table's header bar. */
export function SortSelect({ value, onChange }: { value: string | undefined; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-stone-500">
      Ordenar por
      <select
        className="h-7 rounded-md border border-stone-200 bg-white px-1.5 text-xs text-stone-700 focus:border-brand-400 focus:outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {SORTS.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
    </label>
  )
}

/** FR-8 filter bar: one row above the table; every control writes to the URL. */
export function FilterBar({
  filters,
  areas,
  onChange,
  onClear,
}: {
  filters: CandidateFilters
  areas: AreaLabels | undefined
  onChange: (key: string, value: string | null) => void
  onClear: () => void
}) {
  const [query, setQuery] = useState(filters.q ?? '')
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  })

  // Search as you type, without a request per keystroke.
  useEffect(() => {
    const current = filters.q ?? ''
    if (query.trim() === current) return
    const timer = setTimeout(() => onChangeRef.current('q', query.trim() || null), 250)
    return () => clearTimeout(timer)
  }, [query, filters.q])

  // Keep the box in sync when filters are cleared elsewhere (state adjusted during render).
  const [seenQ, setSeenQ] = useState(filters.q)
  if (filters.q !== seenQ) {
    setSeenQ(filters.q)
    if (!filters.q) setQuery('')
  }

  const cities = Object.entries(areas?.cities ?? {}).sort((a, b) => a[1].localeCompare(b[1], 'es'))

  return (
    <div className="flex flex-wrap items-center gap-2" role="search">
      <div className="relative w-full sm:w-56">
        <Icon name="search" className="pointer-events-none absolute top-2 left-2.5 size-4 text-stone-400" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar por nombre"
          aria-label="Buscar por nombre"
          className="field w-full pl-8"
        />
      </div>
      <Select label="Estado" value={filters.status} onChange={(v) => onChange('status', v)}
        options={STATUS_ORDER.map((s) => [s, STATUS_META[s].label])} />
      <Select label="País" value={filters.country} onChange={(v) => onChange('country', v)}
        options={Object.entries(COUNTRY)} />
      <Select label="Ciudad" value={filters.city} onChange={(v) => onChange('city', v)} options={cities} />
      <Select label="Prioridad" value={filters.bucket} onChange={(v) => onChange('bucket', v)}
        options={Object.entries(BUCKET_META).map(([k, m]) => [k, m.label])} />
      <Select label="Gestión" value={filters.recruiter_status} onChange={(v) => onChange('recruiter_status', v)}
        options={Object.entries(RECRUITER_STATUS)} />
      {hasActiveFilters(filters) && (
        <button type="button" className="btn-ghost" onClick={onClear}>
          <Icon name="x" /> Limpiar
        </button>
      )}
    </div>
  )
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string | undefined
  options: [string, string][]
  onChange: (value: string | null) => void
}) {
  return (
    <select
      aria-label={label}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
      className={`field max-w-44 text-[13px] ${value ? 'border-brand-300 bg-brand-50 text-brand-900' : 'text-stone-600'}`}
    >
      <option value="">{label}: todos</option>
      {options.map(([key, text]) => (
        <option key={key} value={key}>
          {text}
        </option>
      ))}
    </select>
  )
}
