import type { ScoreResult } from '../api/client'
import { FACTOR } from '../lib/labels'
import { factorSentence, factorValue } from '../lib/record'
import { BUCKET_META } from '../lib/status'
import { PriorityPill } from './Badges'

/**
 * Explainability: the score is a plain sum of config-weighted factors (spec 002 FR-30),
 * so we show every factor, the value it came from and the points it earned.
 *
 * Spec 015: the zone-demand factor depends on the zone's *current* staffing, so the
 * dashboard shows the live score; `atClose` is the score stored when the conversation
 * ended (kept for audit) and is noted when it differs.
 */
export function ScoreBreakdown({
  score,
  atClose,
}: {
  score: ScoreResult | null | undefined
  atClose?: ScoreResult | null
}) {
  if (!score) {
    return (
      <p className="text-sm text-stone-500">
        Sin puntuación: solo se puntúa a candidatos aptos o pendientes de revisión.
      </p>
    )
  }
  const factors = [...score.factors].sort((a, b) => b.points - a.points)
  const changed = !!atClose && (atClose.score !== score.score || atClose.bucket !== score.bucket)
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold text-stone-900">{score.score}</span>
        <span className="text-sm text-stone-500">/ {score.max_score}</span>
        <span className="ml-auto">
          <PriorityPill bucket={score.bucket} score={null} />
        </span>
      </div>
      {changed && atClose && (
        <p
          className="mt-0.5 text-right text-xs text-stone-500"
          title="Puntuación guardada al cerrar la conversación; la actual usa la ocupación de hoy"
        >
          Al cerrar: {atClose.score} ({BUCKET_META[atClose.bucket].label})
        </p>
      )}
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-brand-100"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={score.max_score}
        aria-valuenow={score.score}
        aria-label="Puntuación"
      >
        <div
          className="h-full rounded-full bg-brand-600"
          style={{ width: `${(score.score / score.max_score) * 100}%` }}
        />
      </div>
      <ul className="mt-3 divide-y divide-stone-100">
        {factors.map((factor) => (
          <li
            key={factor.reason_code + factor.field}
            className="flex items-center gap-3 py-1.5 text-sm"
            title={factorSentence(factor)}
          >
            <span className="w-40 shrink-0 text-stone-700">{FACTOR[factor.reason_code]}</span>
            <span className="min-w-0 flex-1 truncate text-stone-500">{factorValue(factor)}</span>
            <span
              className={`w-10 text-right font-medium tabular-nums ${factor.points ? 'text-stone-900' : 'text-stone-400'}`}
            >
              +{factor.points}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
