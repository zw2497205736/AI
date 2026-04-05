import { Route, Routes } from 'react-router-dom'

import { ProtectedLayout } from './components/layout/ProtectedLayout'
import { ChatPage } from './pages/ChatPage'
import { CodeReviewPage } from './pages/CodeReviewPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { GithubAgentPage } from './pages/GithubAgentPage'
import { LoginPage } from './pages/LoginPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<ChatPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/code-review" element={<CodeReviewPage />} />
        <Route path="/github-agent" element={<GithubAgentPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
