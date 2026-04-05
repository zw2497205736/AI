import { create } from 'zustand'

interface AuthState {
  token: string
  username: string
  isAuthenticated: boolean
  setAuth: (token: string, username: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('auth_token') || '',
  username: localStorage.getItem('auth_username') || '',
  isAuthenticated: Boolean(localStorage.getItem('auth_token')),
  setAuth: (token, username) => {
    localStorage.setItem('auth_token', token)
    localStorage.setItem('auth_username', username)
    localStorage.setItem('current_user_id', username)
    set({ token, username, isAuthenticated: true })
  },
  logout: () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_username')
    localStorage.removeItem('current_user_id')
    set({ token: '', username: '', isAuthenticated: false })
  },
}))

