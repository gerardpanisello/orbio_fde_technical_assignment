import type { QuickReply } from '../api/client'

/** FR-2: tappable chips under the last agent message; a tap sends the chip's label. */
export function QuickReplies({
  replies,
  onPick,
  disabled,
  label,
}: {
  replies: QuickReply[]
  onPick: (text: string) => void
  disabled?: boolean
  label: string
}) {
  if (!replies.length) return null
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1.5 pt-1.5 pl-2">
      {replies.map((reply) => (
        <button
          key={reply.id}
          type="button"
          disabled={disabled}
          onClick={() => onPick(reply.label)}
          className="animate-pop rounded-full border border-wa-green/30 bg-white px-3.5 py-1.5 text-[13px] font-medium text-wa-header shadow-[0_1px_0.5px_rgba(11,20,26,0.13)] transition hover:bg-[#f0faf7] active:scale-95 disabled:opacity-50"
        >
          {reply.label}
        </button>
      ))}
    </div>
  )
}
