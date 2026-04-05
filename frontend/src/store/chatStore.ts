import { create } from 'zustand'
import { v4 as uuidv4 } from 'uuid'

import type { ConversationSummary, LongTermMemory, Message } from '../types'

interface ChatStore {
  sessionId: string
  currentTitle: string
  userId: string
  messages: Message[]
  isStreaming: boolean
  longTermMemories: LongTermMemory[]
  conversations: ConversationSummary[]
  setSessionId: (id: string) => void
  setCurrentTitle: (title: string) => void
  setUserId: (userId: string) => void
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void
  setMessages: (messages: Message[]) => void
  appendToLastAssistant: (content: string) => void
  setStreaming: (value: boolean) => void
  clearSession: () => void
  setMemories: (memories: LongTermMemory[]) => void
  setConversations: (conversations: ConversationSummary[]) => void
}

export const useChatStore = create<ChatStore>((set) => ({
  sessionId: uuidv4(),
  currentTitle: '新对话',
  userId: localStorage.getItem('current_user_id') || 'guest',
  messages: [],
  isStreaming: false,
  longTermMemories: [],
  conversations: [],
  setSessionId: (id) => set({ sessionId: id }),
  setCurrentTitle: (title) => set({ currentTitle: title }),
  setUserId: (userId) => {
    localStorage.setItem('current_user_id', userId)
    set({ userId })
  },
  addMessage: (msg) =>
    set((state) => ({
      messages: [...state.messages, { ...msg, id: uuidv4(), timestamp: Date.now() }],
    })),
  setMessages: (messages) => set({ messages }),
  appendToLastAssistant: (content) =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last?.role === 'assistant') {
        messages[messages.length - 1] = { ...last, content: last.content + content }
      }
      return { messages }
    }),
  setStreaming: (value) => set({ isStreaming: value }),
  clearSession: () => set({ messages: [], sessionId: uuidv4(), currentTitle: '新对话' }),
  setMemories: (memories) => set({ longTermMemories: memories }),
  setConversations: (conversations) => set({ conversations }),
}))
