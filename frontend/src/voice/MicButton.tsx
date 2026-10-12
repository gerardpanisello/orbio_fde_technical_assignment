import { useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { Icon } from '../components/Icon'
import { Spinner } from '../components/States'
import { pressKind, type VoicePhase } from './voiceLogic'

/**
 * The big round mic (FR-1, FR-6). Tap: listen until a pause (tap again to finish early).
 * Hold: push-to-talk, releasing ends the turn. Enter/Space toggle it from the keyboard.
 * Disabled while Sofi speaks or while we wait for her answer.
 */
export function MicButton({
  phase,
  enabled,
  label,
  onStart,
  onStop,
}: {
  phase: VoicePhase
  enabled: boolean // may a new turn start now
  label: string
  onStart: () => void
  onStop: () => void
}) {
  const press = useRef<{ at: number; started: boolean } | null>(null)
  const listening = phase === 'listening'

  function down(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return
    event.preventDefault()
    if (listening) {
      press.current = null
      onStop()
      return
    }
    if (!enabled) return
    event.currentTarget.setPointerCapture?.(event.pointerId)
    press.current = { at: performance.now(), started: true }
    onStart()
  }

  function up() {
    const current = press.current
    press.current = null
    if (current?.started && pressKind(current.at, performance.now()) === 'hold') onStop()
  }

  function key(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    if (event.repeat) return
    if (listening) onStop()
    else if (enabled) onStart()
  }

  const tone =
    phase === 'listening'
      ? 'bg-red-500 text-white shadow-red-500/30'
      : enabled
        ? 'bg-brand-600 text-white shadow-brand-600/30 hover:bg-brand-700'
        : 'bg-stone-200 text-stone-500 shadow-transparent'

  return (
    <div className="relative grid size-28 place-items-center">
      {listening && (
        <>
          <span className="absolute inset-2 animate-ping rounded-full bg-red-400/30" aria-hidden="true" />
          <span className="absolute inset-0 rounded-full border-2 border-red-300/60" aria-hidden="true" />
        </>
      )}
      {phase === 'speaking' && (
        <span className="absolute inset-1 animate-pulse rounded-full bg-brand-200/60" aria-hidden="true" />
      )}
      <button
        type="button"
        onPointerDown={down}
        onPointerUp={up}
        onPointerCancel={up}
        onKeyDown={key}
        onContextMenu={(e) => e.preventDefault()} // long-press on mobile must not open a menu
        disabled={!enabled && !listening}
        aria-pressed={listening}
        aria-label={label}
        title={label}
        data-phase={phase}
        className={`relative grid size-20 touch-none place-items-center rounded-full shadow-lg transition select-none active:scale-95 disabled:cursor-not-allowed ${tone}`}
      >
        {phase === 'thinking' ? (
          <Spinner className="size-7" />
        ) : phase === 'speaking' ? (
          <SoundBars />
        ) : listening ? (
          <span className="size-6 rounded-md bg-white" aria-hidden="true" />
        ) : (
          <Icon name="mic" className="size-9" />
        )}
      </button>
    </div>
  )
}

function SoundBars() {
  return (
    <span className="flex h-7 items-center gap-1" aria-hidden="true">
      {[0, 150, 300, 450].map((delay) => (
        <span
          key={delay}
          className="h-full w-1.5 origin-center animate-[sound_900ms_ease-in-out_infinite] rounded-full bg-brand-600"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  )
}
