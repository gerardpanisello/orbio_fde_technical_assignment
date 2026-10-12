import type { CandidateFilters, SortKey } from '../api/client'

/** The filter bar lives in the URL (?status=…&q=…), so a filtered view survives reloads and can be shared. */
export const FILTER_KEYS = ['status', 'country', 'city', 'bucket', 'recruiter_status', 'channel', 'q'] as const
export const DEFAULT_SORT: SortKey = '-score' // FR-8: highest priority first

export function filtersFromParams(params: URLSearchParams): CandidateFilters {
  const filters: Record<string, string> = {}
  for (const key of FILTER_KEYS) {
    const value = params.get(key)?.trim()
    if (value) filters[key] = value
  }
  filters.sort = params.get('sort') || DEFAULT_SORT
  return filters as CandidateFilters
}

/** Returns new params with `key` set (or removed when empty); other params, like ?id, are kept. */
export function withParam(params: URLSearchParams, key: string, value: string | null): URLSearchParams {
  const next = new URLSearchParams(params)
  if (value && value.trim()) next.set(key, value)
  else next.delete(key)
  return next
}

export function hasActiveFilters(filters: CandidateFilters): boolean {
  return FILTER_KEYS.some((key) => !!filters[key])
}

export function clearFilters(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const key of FILTER_KEYS) next.delete(key)
  return next
}
