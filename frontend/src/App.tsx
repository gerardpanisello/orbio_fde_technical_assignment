import { Navigate, Route, Routes } from 'react-router'
import { ChatPage } from './chat/ChatPage'
import { Home } from './pages/Home'
import { AnalyticsPage } from './recruiter/AnalyticsPage'
import { CandidatesPage } from './recruiter/CandidatesPage'
import { InterviewsPage } from './recruiter/InterviewsPage'
import { RecruiterLayout } from './recruiter/RecruiterLayout'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/recruiter" element={<RecruiterLayout />}>
        <Route index element={<CandidatesPage />} />
        <Route path="entrevistas" element={<InterviewsPage />} />
        <Route path="analitica" element={<AnalyticsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
