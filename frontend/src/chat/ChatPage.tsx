import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { keys, useCandidate } from '../api/queries'
import { Icon } from '../components/Icon'
import { Logo } from '../components/Logo'
import { ChatWindow } from './ChatWindow'
import { LiveRecordPanel } from './LiveRecordPanel'
import { StartScreen } from './StartScreen'
import { useChat } from './useChat'
import { followUpTotal } from '../lib/reengagement'

const PANEL_KEY = 'sazon.chat.demoPanel'

function readPanelPref(): boolean {
  try {
    return localStorage.getItem(PANEL_KEY) !== 'off'
  } catch {
    return true
  }
}

/**
 * /chat. Mobile: full-screen chat. Desktop: the chat inside a phone frame, plus the
 * optional demo panel with the live record (FR-7).
 */
export function ChatPage() {
  const queryClient = useQueryClient()
  const onTurn = useCallback(
    (id: string) => {
      void queryClient.invalidateQueries({ queryKey: keys.candidate(id) })
      void queryClient.invalidateQueries({ queryKey: keys.allCandidates })
    },
    [queryClient],
  )
  const chat = useChat(onTurn)
  const detail = useCandidate(chat.conversationId)
  const [showPanel, setShowPanel] = useState(readPanelPref)

  function togglePanel() {
    setShowPanel((current) => {
      try {
        localStorage.setItem(PANEL_KEY, current ? 'off' : 'on')
      } catch {
        // preference only
      }
      return !current
    })
  }

  const screen =
    chat.phase === 'start' || chat.phase === 'starting' ? (
      <StartScreen
        onStart={chat.start}
        starting={chat.phase === 'starting'}
        failed={chat.error === 'start'}
      />
    ) : (
      <ChatWindow
        chat={chat}
        slot={detail.data?.candidate.interview_slot ?? null}
        followUpTotal={followUpTotal(detail.data)}
        booking={detail.data?.booking ?? null}
      />
    )

  return (
    <div className="h-dvh md:flex md:flex-col md:bg-stone-100">
      {/* Desktop chrome: brand, back link and the demo-panel toggle. */}
      <header className="hidden items-center justify-between px-6 py-3 md:flex">
        <Link to="/" className="rounded-lg">
          <Logo subtitle="Chat de candidatos" />
        </Link>
        <div className="flex items-center gap-2">
          <Link to="/recruiter" className="btn-ghost">
            <Icon name="users" /> Panel recruiter
          </Link>
          <button type="button" onClick={togglePanel} className="btn-secondary" aria-pressed={showPanel}>
            <Icon name="panel" /> {showPanel ? 'Ocultar panel demo' : 'Mostrar panel demo'}
          </button>
        </div>
      </header>

      <main className="h-full md:flex md:min-h-0 md:flex-1 md:items-center md:justify-center md:gap-8 md:px-6 md:pb-6">
        <PhoneFrame>{screen}</PhoneFrame>
        {showPanel && (
          <div className="hidden h-[min(780px,100%)] w-[380px] animate-slide-in lg:block">
            <LiveRecordPanel
              conversationId={chat.conversationId}
              detail={detail.data}
              loading={detail.isFetching}
              onAdvanced={chat.sync}
            />
          </div>
        )}
      </main>
    </div>
  )
}

/** Phone bezel on desktop; on a real phone the chat simply fills the screen. */
function PhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div className="h-full md:h-[min(780px,100%)] md:w-[380px] md:shrink-0 md:rounded-[44px] md:bg-stone-900 md:p-[10px] md:shadow-2xl md:shadow-stone-900/20">
      <div className="relative h-full overflow-hidden md:rounded-[34px]">
        <div className="hidden h-6 items-center justify-between bg-wa-header px-6 text-[11px] font-semibold text-white md:flex">
          <span>9:41</span>
          <span className="h-4 w-20 rounded-full bg-stone-900" aria-hidden="true" />
          <span aria-hidden="true">5G ▮▮▮</span>
        </div>
        <div className="h-full md:h-[calc(100%-1.5rem)]">{children}</div>
      </div>
    </div>
  )
}
