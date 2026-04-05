import { useEffect, useRef, useState } from 'react'

import {
  clearSession,
  deleteConversation,
  deleteMemory,
  getConversationMessages,
  listConversations,
  listMemories,
  streamChat,
  updateConversationTitle,
} from '../api/chatApi'
import { ChatWindow } from '../components/chat/ChatWindow'
import { InputBar } from '../components/chat/InputBar'
import { MemoryPanel } from '../components/chat/MemoryPanel'
import { useChatStore } from '../store/chatStore'

export function ChatPage() {
  const {
    sessionId,
    currentTitle,
    userId,
    messages,
    isStreaming,
    longTermMemories,
    conversations,
    setSessionId,
    setCurrentTitle,
    addMessage,
    setMessages,
    appendToLastAssistant,
    setStreaming,
    clearSession: clearLocalSession,
    setMemories,
    setConversations,
  } = useChatStore()
  const [editingTitle, setEditingTitle] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const previousUserIdRef = useRef(userId)
  const userLoadVersionRef = useRef(0)
  const messageLoadVersionRef = useRef(0)

  useEffect(() => {
    const version = ++userLoadVersionRef.current
    void listMemories()
      .then((items) => {
        if (userLoadVersionRef.current !== version) return
        setMemories(items)
      })
      .catch(() => undefined)
    void listConversations()
      .then((items) => {
        if (userLoadVersionRef.current !== version) return
        setConversations(items)
        const currentExists = items.some((item) => item.session_id === useChatStore.getState().sessionId)
        if (!currentExists) {
          clearLocalSession()
        }
      })
      .catch(() => undefined)
  }, [clearLocalSession, setConversations, setMemories, userId])

  useEffect(() => {
    if (previousUserIdRef.current === userId) {
      return
    }
    previousUserIdRef.current = userId
    userLoadVersionRef.current += 1
    messageLoadVersionRef.current += 1
    clearLocalSession()
    setMemories([])
    setConversations([])
    setMessages([])
    setCurrentTitle('新对话')
    setEditingTitle(false)
  }, [clearLocalSession, setConversations, setCurrentTitle, setMemories, setMessages, userId])

  useEffect(() => {
    if (!sessionId) return
    const existing = conversations.find((item) => item.session_id === sessionId)
    if (!existing) return
    const version = ++messageLoadVersionRef.current
    void getConversationMessages(sessionId)
      .then((data) => {
        if (messageLoadVersionRef.current !== version) return
        if (useChatStore.getState().sessionId !== sessionId) return
        setMessages(data.messages)
        setCurrentTitle(data.title)
      })
      .catch(() => undefined)
  }, [conversations, sessionId, setCurrentTitle, setMessages])

  const handleSend = async (query: string) => {
    addMessage({ role: 'user', content: query })
    addMessage({ role: 'assistant', content: '' })
    setStreaming(true)
    try {
      await streamChat(query, sessionId, appendToLastAssistant, setSessionId)
      const memories = await listMemories()
      const nextConversations = await listConversations()
      setMemories(memories)
      setConversations(nextConversations)
      const current = nextConversations.find((item) => item.session_id === useChatStore.getState().sessionId)
      setCurrentTitle(current?.title ?? '新对话')
    } finally {
      setStreaming(false)
    }
  }

  const handleNewSession = async () => {
    if (sessionId) {
      await clearSession(sessionId).catch(() => undefined)
    }
    clearLocalSession()
  }

  const handleDeleteMemory = async (memoryId: number) => {
    await deleteMemory(memoryId)
    const memories = await listMemories()
    setMemories(memories)
  }

  const handleSaveTitle = async () => {
    const title = draftTitle.trim()
    if (!sessionId || !title) {
      setEditingTitle(false)
      return
    }
    await updateConversationTitle(sessionId, title)
    const nextConversations = await listConversations()
    setConversations(nextConversations)
    setCurrentTitle(title)
    setEditingTitle(false)
  }

  return (
    <div className="flex h-screen bg-transparent">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-border bg-white px-6 py-5">
          <div className="mx-auto flex max-w-4xl items-center justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-text">当前对话</div>
              {editingTitle ? (
                <div className="mt-1 flex items-center gap-2">
                  <input
                    value={draftTitle}
                    onChange={(event) => setDraftTitle(event.target.value)}
                    className="rounded-2xl border border-border bg-white px-4 py-2.5 text-sm text-text outline-none"
                  />
                  <button type="button" onClick={handleSaveTitle} className="rounded-xl px-3 py-2 text-sm text-text hover:bg-accentSoft">
                    保存
                  </button>
                </div>
              ) : (
                <div className="mt-1 flex items-center gap-3">
                  <div className="text-lg font-semibold text-text">{currentTitle}</div>
                  {sessionId ? (
                    <button
                      type="button"
                      onClick={() => {
                        setDraftTitle(currentTitle)
                        setEditingTitle(true)
                      }}
                      className="rounded-xl px-3 py-2 text-sm text-text hover:bg-[#f5f6f7]"
                    >
                      重命名
                    </button>
                  ) : null}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              {sessionId ? (
                <button
                  type="button"
                  onClick={async () => {
                    await deleteConversation(sessionId).catch(() => undefined)
                    const nextConversations = await listConversations()
                    setConversations(nextConversations)
                    clearLocalSession()
                  }}
                  className="rounded-2xl border border-red-200 bg-white px-4 py-2.5 text-sm text-red-500"
                >
                  删除对话
                </button>
              ) : null}
              <button type="button" onClick={handleNewSession} className="rounded-2xl border border-border bg-white px-4 py-2.5 text-sm shadow-sm">
                新建对话
              </button>
            </div>
          </div>
        </div>
        <ChatWindow messages={messages} isStreaming={isStreaming} />
        <InputBar disabled={isStreaming} onSend={handleSend} />
      </div>
      <MemoryPanel memories={longTermMemories} onDelete={handleDeleteMemory} />
    </div>
  )
}
