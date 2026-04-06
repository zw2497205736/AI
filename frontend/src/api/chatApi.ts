import { apiClient } from './axios'
import type { ConversationSummary, LongTermMemory, Message, MessageSource } from '../types'

export async function streamChat(
  query: string,
  sessionId: string,
  onChunk: (content: string) => void,
  onSession: (sessionId: string) => void,
  onSources?: (sources: MessageSource[]) => void,
  onRetrievalHit?: (retrievalHit: boolean) => void,
  signal?: AbortSignal,
) {
  const url = `/api/chat/stream?query=${encodeURIComponent(query)}&session_id=${sessionId}`
  const token = localStorage.getItem('auth_token')
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error('Chat stream failed')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') return
      const parsed = JSON.parse(data)
      if (parsed.session_id) onSession(parsed.session_id)
      if (parsed.content) onChunk(parsed.content)
      if (Array.isArray(parsed.sources) && onSources) onSources(parsed.sources as MessageSource[])
      if (typeof parsed.retrieval_hit === 'boolean' && onRetrievalHit) onRetrievalHit(parsed.retrieval_hit)
    }
  }
}

export async function listMemories() {
  const { data } = await apiClient.get<LongTermMemory[]>('/api/chat/memories')
  return data
}

export async function clearSession(sessionId: string) {
  await apiClient.delete(`/api/chat/session/${sessionId}`)
}

export async function deleteMemory(memoryId: number) {
  await apiClient.delete(`/api/chat/memories/${memoryId}`)
}

export async function listConversations() {
  const { data } = await apiClient.get<ConversationSummary[]>('/api/chat/conversations')
  return data
}

export async function getConversationMessages(sessionId: string) {
  const { data } = await apiClient.get<{ session_id: string; title: string; messages: Message[] }>(
    `/api/chat/conversations/${sessionId}/messages`,
  )
  return data
}

export async function updateConversationTitle(sessionId: string, title: string) {
  const { data } = await apiClient.patch(`/api/chat/conversations/${sessionId}`, { title })
  return data
}

export async function deleteConversation(sessionId: string) {
  await apiClient.delete(`/api/chat/conversations/${sessionId}`)
}
