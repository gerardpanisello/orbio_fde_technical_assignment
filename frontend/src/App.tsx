import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { ChatPage } from './chat/ChatPage'
import { Home } from './pages/Home'
import { CandidatesPage } from './recruiter/CandidatesPage'
import { InterviewsPage } from './recruiter/InterviewsPage'
import { Loading } from './components/States'
import { RecruiterLayout } from './recruiter/RecruiterLayout'

// Charts (Recharts) are the heaviest dependency: load them only when Analytics opens.
const AnalyticsPage = lazy(() =>
  import('./recruiter/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
)

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/recruiter" element={<RecruiterLayout />}>
        <Route index element={<CandidatesPage />} />
        <Route path="entrevistas" element={<InterviewsPage />} />
        <Route
          path="analitica"
          element={
            <Suspense fallback={<Loading />}>
              <AnalyticsPage />
            </Suspense>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
