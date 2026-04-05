import { create } from 'zustand'

interface SettingsState {
  currentUserId: string
  openaiBaseUrl: string
  chatModel: string
  embeddingModel: string
  setSettings: (payload: Partial<Omit<SettingsState, 'setSettings'>>) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  currentUserId: localStorage.getItem('current_user_id') || 'guest',
  openaiBaseUrl: 'https://api.openai.com/v1',
  chatModel: 'gpt-4o-mini',
  embeddingModel: 'text-embedding-3-small',
  setSettings: (payload) =>
    set((state) => {
      const next = { ...state, ...payload }
      if (payload.currentUserId) {
        localStorage.setItem('current_user_id', payload.currentUserId)
      }
      return next
    }),
}))
