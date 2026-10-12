/** Query keys and the shared TanStack Query hooks (cache, refetch after actions). */
import { useQuery } from '@tanstack/react-query'
import { api, type CandidateFilters, type Language } from './client'

export const keys = {
  candidates: (filters: CandidateFilters) => ['candidates', filters] as const,
  allCandidates: ['candidates'] as const,
  candidate: (id: string) => ['candidate', id] as const,
  summary: (id: string, lang: Language) => ['summary', id, lang] as const,
  analytics: ['analytics'] as const,
  areas: ['areas'] as const,
  zones: ['zones'] as const,
}

/** City/zone display names from config/service_areas.yaml; they never change at runtime. */
export function useAreaLabels() {
  return useQuery({ queryKey: keys.areas, queryFn: api.areaLabels, staleTime: Infinity }).data
}

export function useCandidate(id: string | null) {
  return useQuery({
    queryKey: keys.candidate(id ?? ''),
    queryFn: () => api.getCandidate(id!),
    enabled: !!id,
  })
}

export function useAnalytics() {
  return useQuery({ queryKey: keys.analytics, queryFn: api.analytics })
}

/** Staffing per served area (spec 015); edits on the Zonas page update this cache. */
export function useZones() {
  return useQuery({ queryKey: keys.zones, queryFn: api.listZones })
}
