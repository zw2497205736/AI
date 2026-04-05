import { apiClient } from './axios'

export async function login(username: string, password: string) {
  const { data } = await apiClient.post('/api/auth/login', { username, password })
  return data
}

export async function register(username: string, password: string) {
  const { data } = await apiClient.post('/api/auth/register', { username, password })
  return data
}

