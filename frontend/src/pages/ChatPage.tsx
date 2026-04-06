import { useEffect, useRef, useState } from 'react'

import {
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
    messagesBySession,
    streamingBySession,
    longTermMemories,
    conversations,
    setSessionId,
    setCurrentTitle,
    addMessage,
    setSessionMessages,
    appendToLastAssistant,
    setLastAssistantSources,
    setLastAssistantRetrievalHit,
    clearSession: clearLocalSession,
    removeSession,
    setMemories,
    setConversations,
  } = useChatStore()
  const [editingTitle, setEditingTitle] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const previousUserIdRef = useRef(userId)
  const userLoadVersionRef = useRef(0)
  const messageLoadVersionRef = useRef(0)
  const streamControllersRef = useRef<Record<string, AbortController>>({})
  const messages = messagesBySession[sessionId] || []
  const isStreaming = Boolean(streamingBySession[sessionId])

  const abortStreamForSession = (targetSessionId: string) => {
    const controller = streamControllersRef.current[targetSessionId]
    if (controller) {
      controller.abort()
      delete streamControllersRef.current[targetSessionId]
    }
    useChatStore.getState().setSessionStreaming(targetSessionId, false)
  }

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
    Object.keys(streamControllersRef.current).forEach((item) => abortStreamForSession(item))
    setSessionMessages(useChatStore.getState().sessionId, [])
    setCurrentTitle('新对话')
    setEditingTitle(false)
  }, [clearLocalSession, setConversations, setCurrentTitle, setMemories, setSessionMessages, userId])

  useEffect(
    () => () => {
      Object.keys(streamControllersRef.current).forEach((item) => abortStreamForSession(item))
    },
    [],
  )

  useEffect(() => {
    if (!sessionId) return
    const version = ++messageLoadVersionRef.current
    void getConversationMessages(sessionId)
      .then((data) => {
        if (messageLoadVersionRef.current !== version) return
        if (useChatStore.getState().sessionId !== sessionId) return
        setSessionMessages(sessionId, data.messages)
        setCurrentTitle(data.title)
      })
      .catch(() => undefined)
  }, [sessionId, setCurrentTitle, setSessionMessages])

  const handleSend = async (query: string) => {
    const activeSessionId = sessionId
    let targetSessionId = activeSessionId
    abortStreamForSession(activeSessionId)
    const controller = new AbortController()
    streamControllersRef.current[activeSessionId] = controller
    addMessage(activeSessionId, { role: 'user', content: query })
    addMessage(activeSessionId, { role: 'assistant', content: '', sources: [], retrievalHit: false })
    useChatStore.getState().setSessionStreaming(activeSessionId, true)
    try {
      await streamChat(
        query,
        activeSessionId,
        (content) => {
          appendToLastAssistant(targetSessionId, content)
        },
        (nextSessionId) => {
          targetSessionId = nextSessionId
          const state = useChatStore.getState()
          if (state.sessionId === activeSessionId) {
            state.setSessionId(nextSessionId)
          }
          if (nextSessionId !== activeSessionId) {
            state.setSessionMessages(nextSessionId, state.messagesBySession[activeSessionId] || [])
            state.removeSession(activeSessionId)
            if (streamControllersRef.current[activeSessionId]) {
              streamControllersRef.current[nextSessionId] = streamControllersRef.current[activeSessionId]
              delete streamControllersRef.current[activeSessionId]
            }
            useChatStore.getState().setSessionStreaming(nextSessionId, true)
            useChatStore.getState().setSessionStreaming(activeSessionId, false)
          }
        },
        (sources) => {
          setLastAssistantSources(targetSessionId, sources)
        },
        (retrievalHit) => {
          setLastAssistantRetrievalHit(targetSessionId, retrievalHit)
        },
        controller.signal,
      )
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      throw error
    } finally {
      const finalSessionId = targetSessionId
      if (streamControllersRef.current[finalSessionId] === controller) {
        delete streamControllersRef.current[finalSessionId]
      }
      useChatStore.getState().setSessionStreaming(finalSessionId, false)
      const memories = await listMemories()
      const nextConversations = await listConversations()
      setMemories(memories)
      setConversations(nextConversations)
      const current = nextConversations.find((item) => item.session_id === useChatStore.getState().sessionId)
      setCurrentTitle(current?.title ?? '新对话')
    }
  }

  const handleNewSession = async () => {
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
                    abortStreamForSession(sessionId)
                    removeSession(sessionId)
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
