import { Link, useLocation, useNavigate } from 'react-router-dom'

import { deleteConversation } from '../../api/chatApi'
import { useAuthStore } from '../../store/authStore'
import { useChatStore } from '../../store/chatStore'

const items = [
  { to: '/', label: '智能问答' },
  { to: '/documents', label: '知识库' },
  { to: '/code-review', label: 'Code Review' },
  { to: '/github-agent', label: 'GitHub Agent' },
  { to: '/settings', label: '设置' },
]

export function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { username, logout } = useAuthStore()
  const { conversations, sessionId, streamingBySession, setSessionId, setCurrentTitle, clearSession, removeSession, setConversations } =
    useChatStore()

  return (
    <aside className="gpt-scrollbar flex w-72 flex-col border-r border-border bg-sidebar/92 px-4 py-6 backdrop-blur">
      <div className="mb-8 px-2">
        <div className="mb-2 text-lg font-semibold leading-snug text-text">武大计算机学院校企合作实验室</div>
        <div className="text-2xl font-semibold leading-tight text-text">AI 研发协作平台</div>
      </div>
      <div className="mb-4 rounded-2xl border border-border bg-white px-4 py-3 text-xs text-text shadow-sm">当前账号：{username}</div>
      <nav className="flex flex-col gap-2">
        {items.map((item) => {
          const active = location.pathname === item.to
          return (
            <Link
              key={item.to}
              to={item.to}
              className={`rounded-2xl px-4 py-3 text-sm transition-all ${
                active ? 'bg-accentSoft text-text shadow-sm' : 'text-text hover:bg-white'
              }`}
            >
              {item.label}
            </Link>
          )
        })}
      </nav>
      {location.pathname === '/' ? (
        <div className="gpt-scrollbar mt-8 min-h-0 flex-1 overflow-y-auto">
          <div className="mb-3 px-2 text-xs uppercase tracking-wide text-text">对话</div>
          <div className="flex flex-col gap-2">
            {conversations.map((conversation) => {
              const active = conversation.session_id === sessionId
              return (
                <div
                  key={conversation.session_id}
                  className={`rounded-2xl border px-3 py-3 ${
                    active ? 'border-accent/30 bg-accentSoft shadow-sm' : 'border-border bg-white'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setSessionId(conversation.session_id)
                      setCurrentTitle(conversation.title)
                      navigate('/')
                    }}
                    className="w-full text-left"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="line-clamp-2 text-sm font-medium text-text">{conversation.title}</div>
                      {streamingBySession[conversation.session_id] ? (
                        <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700">生成中</span>
                      ) : null}
                    </div>
                    <div className="mt-1 text-xs text-text">{conversation.created_at}</div>
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      await deleteConversation(conversation.session_id)
                      const next = conversations.filter((item) => item.session_id !== conversation.session_id)
                      setConversations(next)
                      removeSession(conversation.session_id)
                      if (conversation.session_id === sessionId) {
                        clearSession()
                      }
                    }}
                    className="mt-2 text-xs text-red-500"
                  >
                    删除
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}
      <button
        type="button"
        onClick={() => {
          logout()
          clearSession()
          setConversations([])
          navigate('/login')
        }}
        className="mt-4 rounded-2xl border border-border bg-white px-4 py-3 text-sm text-text"
      >
        退出登录
      </button>
    </aside>
  )
}
