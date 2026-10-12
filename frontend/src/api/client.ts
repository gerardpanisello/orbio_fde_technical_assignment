/**
 * The only module that talks to the backend (spec 004). Types come from the FastAPI
 * OpenAPI schema (`npm run gen:api` -> schema.d.ts), so they mirror the Pydantic models
 * and can't drift silently.
 */
import type { components, operations } from './schema'

type Schemas = components['schemas']

export type Status = Schemas['Status']
export type Bucket = Schemas['Bucket']
export type Country = Schemas['Country']
export type Language = Schemas['Language']
export type RecruiterStatus = Schemas['CandidateRow']['recruiter_status']
export type ActionName = Schemas['ActionIn']['action']
export type Conversation = Schemas['ConversationOut']
export type ChatMessage = Schemas['MessageOut']
export type QuickReply = Schemas['QuickReplyOut']
export type Turn = Schemas['TurnOut']
export type CandidateRow = Schemas['CandidateRow']
export type CandidateDetail = Schemas['CandidateDetail']
export type CandidateRecord = Schemas['CandidateRecord']
export type Summary = Schemas['SummaryOut']
export type Trace = Schemas['TraceOut']
export type RecruiterAction = Schemas['ActionOut']
export type Analytics = Schemas['Analytics']
export type AreaLabels = Schemas['AreaLabels']
export type ScoreFactor = Schemas['ScoreFactor']
export type ScoreResult = Schemas['ScoreResult']
export type Zone = Schemas['ZoneOut']
export type AdvanceResult = Schemas['AdvanceOut']
export type ZonePatch = Schemas['ZonePatchIn']
export type VoiceStatus = Schemas['VoiceStatus']

type ListQuery = NonNullable<operations['list_candidates_api_candidates_get']['parameters']['query']>
/** GET /api/candidates query: status, country, city, bucket, recruiter_status, q, sort. */
export type CandidateFilters = { [K in keyof ListQuery]?: NonNullable<ListQuery[K]> }
export type SortKey = NonNullable<ListQuery['sort']>

/** A non-2xx answer. `detail` is FastAPI's message (e.g. the reason for a 409). */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(`HTTP ${status}: ${detail}`)
    this.status = status
    this.detail = detail
  }
}

/** FastAPI 422 bodies are a list of Pydantic errors: keep their messages, not the JSON. */
function validationText(detail: unknown): string {
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d: unknown) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg) : null))
      .filter(Boolean)
    if (messages.length) return messages.join('; ')
  }
  return JSON.stringify(detail)
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body: unknown = await response.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        detail = typeof body.detail === 'string' ? body.detail : validationText(body.detail)
      }
    } catch {
      // not JSON (e.g. the dev proxy's 502 when the API is down): keep statusText
    }
    throw new ApiError(response.status, detail)
  }
  return response
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

/** Filters -> query string. Empty values are dropped so URLs stay short. */
export function toQueryString(filters: CandidateFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      params.set(key, String(value).trim())
    }
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export const api = {
  // candidate chat
  startConversation: (language: Language, countryHint: Country) =>
    post<Conversation>('/api/conversations', { language, country_hint: countryHint }),
  getConversation: (id: string) => request<Conversation>(`/api/conversations/${id}`),
  sendMessage: (id: string, text: string) =>
    post<Turn>(`/api/conversations/${id}/messages`, { text }),

  // recruiter dashboard
  listCandidates: (filters: CandidateFilters) =>
    request<CandidateRow[]>(`/api/candidates${toQueryString(filters)}`),
  exportUrl: (filters: CandidateFilters) =>
    `/api/candidates/export.csv${toQueryString(filters)}`,
  getCandidate: (id: string) => request<CandidateDetail>(`/api/candidates/${id}`),
  getSummary: (id: string, lang: Language) =>
    request<Summary>(`/api/candidates/${id}/summary?lang=${lang}`),
  addAction: (id: string, action: ActionName, note?: string) =>
    post<RecruiterAction>(`/api/candidates/${id}/actions`, { action, note }),
  analytics: () => request<Analytics>('/api/analytics'),
  areaLabels: () => request<AreaLabels>('/api/meta/areas?lang=es'),
  listZones: () => request<Zone[]>('/api/zones?lang=es'),
  updateZone: (id: string, body: ZonePatch) =>
    patch<Zone>(`/api/zones/${encodeURIComponent(id)}?lang=es`, body),

  // voice (spec 013): Sofi's voice via the backend's ElevenLabs proxy (503 -> browser voice)
  voiceStatus: () => request<VoiceStatus>('/api/voice/status'),
  tts: async (text: string, language: Language, country: Country | null, signal?: AbortSignal) =>
    (
      await send('/api/voice/tts', {
        method: 'POST',
        body: JSON.stringify({ text, language, country }),
        signal,
      })
    ).blob(),

  health: () => request<{ status: string; llm_mode: string; env: string }>('/api/health'),

  // dev helpers (APP_ENV=dev only)
  seed: (n = 40) => post<{ created: number; ids: string[] }>(`/api/dev/seed?n=${n}`),
  silence: (id: string) => post<Turn>(`/api/dev/conversations/${id}/silence`),
  /** Spec 008 FR-8: run the next re-engagement step now (reminder, or abandon after the last). */
  advance: (id: string) => post<AdvanceResult>(`/api/dev/conversations/${id}/advance`),
}
