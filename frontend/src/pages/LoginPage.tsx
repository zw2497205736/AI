import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import axios from 'axios'

import { login, register } from '../api/authApi'
import { useAuthStore } from '../store/authStore'
import { useChatStore } from '../store/chatStore'

export function LoginPage() {
  const { isAuthenticated, setAuth } = useAuthStore()
  const { setUserId, clearSession, setCurrentTitle, setConversations, setMemories } = useChatStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isRegister, setIsRegister] = useState(false)
  const [message, setMessage] = useState('')

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#f7f7f5] px-6 py-12 text-text">
      <div
        className="pointer-events-none absolute right-[-60px] top-[-10px] h-[420px] w-[420px] bg-center bg-no-repeat opacity-[0.28]"
        style={{ backgroundImage: "url('/校徽.png')", backgroundSize: 'contain' }}
      />
      <div
        className="pointer-events-none absolute bottom-[-140px] left-[-40px] h-[500px] w-[500px] bg-center bg-no-repeat opacity-[0.16]"
        style={{ backgroundImage: "url('/校徽.png')", backgroundSize: 'contain' }}
      />
      <div className="relative z-10 grid w-full max-w-5xl gap-10 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="hidden flex-col justify-center lg:flex">
          <div className="max-w-xl">
            <div className="mb-4 inline-flex rounded-full border border-accent/15 bg-accentSoft px-4 py-2 text-xs font-medium text-text">
              AI 研发协作平台
            </div>
            <h1 className="text-4xl font-semibold leading-tight text-text">武大计算机学院校企合作实验室</h1>
            <p className="mt-5 text-base leading-8 text-text">
              面向校企联合研发、知识沉淀、智能问答与代码审查的统一工作台。登录后可集中管理知识库、跟踪 GitHub Agent
              自动审查结果、保存多轮对话，并基于团队资料进行检索增强问答，支撑实验室日常研发协同与项目演示。
            </p>
          </div>
        </div>
        <div className="w-full rounded-[32px] border border-border bg-white p-8 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
          <h2 className="text-2xl font-semibold">{isRegister ? '注册账号' : '账号登录'}</h2>
          <p className="mt-2 text-sm leading-6 text-text">使用最简单的账号密码方式进入平台。每个账号拥有自己的对话记录与长期记忆。</p>
          <div className="mt-8 grid gap-4">
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="用户名"
              className="rounded-2xl border border-border bg-white px-4 py-3.5 text-sm text-text outline-none transition focus:border-accent/40"
            />
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="密码"
              className="rounded-2xl border border-border bg-white px-4 py-3.5 text-sm text-text outline-none transition focus:border-accent/40"
            />
            <button
              type="button"
              onClick={async () => {
                try {
                  const data = isRegister ? await register(username, password) : await login(username, password)
                  setAuth(data.token, data.username)
                  setUserId(data.username)
                  clearSession()
                  setCurrentTitle('新对话')
                  setConversations([])
                  setMemories([])
                } catch (error) {
                  if (axios.isAxiosError(error)) {
                    setMessage(String(error.response?.data?.detail || error.message))
                  } else {
                    setMessage(error instanceof Error ? error.message : '登录失败')
                  }
                }
              }}
              className="rounded-2xl bg-accent px-4 py-3.5 text-sm font-medium text-white shadow-sm transition hover:opacity-95"
            >
              {isRegister ? '注册并登录' : '登录'}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsRegister((value) => !value)
                setMessage('')
              }}
              className="rounded-2xl border border-border bg-white px-4 py-3 text-sm text-text transition hover:bg-[#f8fafc]"
            >
              {isRegister ? '已有账号，去登录' : '没有账号，先注册'}
            </button>
            {message ? <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-500">{message}</div> : null}
          </div>
        </div>
      </div>
    </div>
  )
}
