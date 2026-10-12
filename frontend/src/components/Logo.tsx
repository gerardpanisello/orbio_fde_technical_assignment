export function LogoMark({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#c2531f" />
      <path
        d="M16 6c1 3.5 5.5 5.2 5.5 10.5A5.5 5.5 0 0 1 16 22a5.5 5.5 0 0 1-5.5-5.5c0-2.4 1.2-3.9 2.3-5 .2 1.7 1 2.8 2.2 3.2C14.6 11.6 15 8.6 16 6Z"
        fill="#fff"
      />
      <rect x="9" y="24" width="14" height="2" rx="1" fill="#fff" opacity=".85" />
    </svg>
  )
}

export function Logo({ subtitle }: { subtitle?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark />
      <div className="leading-tight">
        <div className="font-semibold tracking-tight text-stone-900">Grupo Sazón</div>
        {subtitle && <div className="text-xs text-stone-500">{subtitle}</div>}
      </div>
    </div>
  )
}
