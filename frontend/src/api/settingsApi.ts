import { apiClient } from './axios'

export async function getSettings() {
  const { data } = await apiClient.get('/api/settings')
  return data
}

export async function saveSettings(payload: {
  openai_api_key?: string
  openai_base_url: string
  chat_model: string
  embedding_model: string
}) {
  const { data } = await apiClient.post('/api/settings', payload)
  return data
}

export async function testSettings() {
  const { data } = await apiClient.get('/api/settings/test')
  return data
}
