import { create } from 'zustand'
import { v4 as uuidv4 } from 'uuid'

import type { ConversationSummary, LongTermMemory, Message, MessageSource } from '../types'

interface ChatStore {
  sessionId: string
  currentTitle: string
  userId: string
  messagesBySession: Record<string, Message[]>
  streamingBySession: Record<string, boolean>
  longTermMemories: LongTermMemory[]
  conversations: ConversationSummary[]
  setSessionId: (id: string) => void
  setCurrentTitle: (title: string) => void
  setUserId: (userId: string) => void
  addMessage: (sessionId: string, msg: Omit<Message, 'id' | 'timestamp'>) => void
  setSessionMessages: (sessionId: string, messages: Message[]) => void
  appendToLastAssistant: (sessionId: string, content: string) => void
  setLastAssistantSources: (sessionId: string, sources: MessageSource[]) => void
  setLastAssistantRetrievalHit: (sessionId: string, retrievalHit: boolean) => void
  setSessionStreaming: (sessionId: string, value: boolean) => void
  clearSession: () => void
  removeSession: (sessionId: string) => void
  setMemories: (memories: LongTermMemory[]) => void
  setConversations: (conversations: ConversationSummary[]) => void
}

const createSessionId = () => uuidv4()

export const useChatStore = create<ChatStore>((set) => ({
  sessionId: createSessionId(),
  currentTitle: '新对话',
  userId: localStorage.getItem('current_user_id') || 'guest',
  messagesBySession: {},
  streamingBySession: {},
  longTermMemories: [],
  conversations: [],
  setSessionId: (id) => set({ sessionId: id }),
  setCurrentTitle: (title) => set({ currentTitle: title }),
  setUserId: (userId) => {
    localStorage.setItem('current_user_id', userId)
    set({ userId })
  },
  addMessage: (sessionId, msg) =>
    set((state) => ({
      messagesBySession: {
        ...state.messagesBySession,
        [sessionId]: [...(state.messagesBySession[sessionId] || []), { ...msg, id: uuidv4(), timestamp: Date.now() }],
      },
    })),
  setSessionMessages: (sessionId, messages) =>
    set((state) => ({
      messagesBySession: {
        ...state.messagesBySession,
        [sessionId]: messages,
      },
    })),
  appendToLastAssistant: (sessionId, content) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] || [])]
      const last = messages[messages.length - 1]
      if (last?.role === 'assistant') {
        messages[messages.length - 1] = { ...last, content: last.content + content }
      }
      return {
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId]: messages,
        },
      }
    }),
  setLastAssistantSources: (sessionId, sources) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] || [])]
      const last = messages[messages.length - 1]
      if (last?.role === 'assistant') {
        messages[messages.length - 1] = { ...last, sources }
      }
      return {
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId]: messages,
        },
      }
    }),
  setLastAssistantRetrievalHit: (sessionId, retrievalHit) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] || [])]
      const last = messages[messages.length - 1]
      if (last?.role === 'assistant') {
        messages[messages.length - 1] = { ...last, retrievalHit }
      }
      return {
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId]: messages,
        },
      }
    }),
  setSessionStreaming: (sessionId, value) =>
    set((state) => ({
      streamingBySession: {
        ...state.streamingBySession,
        [sessionId]: value,
      },
    })),
  clearSession: () => {
    const nextSessionId = createSessionId()
    set((state) => ({
      sessionId: nextSessionId,
      currentTitle: '新对话',
      messagesBySession: {
        ...state.messagesBySession,
        [nextSessionId]: [],
      },
      streamingBySession: {
        ...state.streamingBySession,
        [nextSessionId]: false,
      },
    }))
  },
  removeSession: (sessionId) =>
    set((state) => {
      const { [sessionId]: _removedMessages, ...nextMessagesBySession } = state.messagesBySession
      const { [sessionId]: _removedStreaming, ...nextStreamingBySession } = state.streamingBySession
      return {
        messagesBySession: nextMessagesBySession,
        streamingBySession: nextStreamingBySession,
      }
    }),
  setMemories: (memories) => set({ longTermMemories: memories }),
  setConversations: (conversations) => set({ conversations }),
}))
