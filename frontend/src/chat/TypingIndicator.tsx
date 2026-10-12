export function TypingIndicator() {
  return (
    <div className="mt-2 flex pl-2" aria-hidden="true">
      <div className="relative flex items-center gap-1 rounded-lg rounded-tl-none bg-white px-3.5 py-3 shadow-[0_1px_0.5px_rgba(11,20,26,0.13)]">
        <Tail side="left" />
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="size-1.5 animate-typing rounded-full bg-wa-meta"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </div>
  )
}

/** The little tail on the top corner of the first bubble of a group. */
export function Tail({ side }: { side: 'left' | 'right' }) {
  return side === 'left' ? (
    <svg
      viewBox="0 0 8 13"
      className="absolute top-0 -left-2 h-[13px] w-2 text-white"
      aria-hidden="true"
    >
      <path d="M8 0H1.5C.6 0 .2 1 .8 1.7L8 10.5Z" fill="currentColor" />
    </svg>
  ) : (
    <svg
      viewBox="0 0 8 13"
      className="absolute top-0 -right-2 h-[13px] w-2 text-wa-out"
      aria-hidden="true"
    >
      <path d="M0 0h6.5c.9 0 1.3 1 .7 1.7L0 10.5Z" fill="currentColor" />
    </svg>
  )
}
