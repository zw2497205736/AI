import { apiClient } from './axios'
import type { ConversationSummary, LongTermMemory, Message, MessageSource } from '../types'

export async function streamChat(
  query: string,
  sessionId: string,
  onChunk: (content: string) => void,
  onSession: (sessionId: string) => void,
  onSources?: (sources: MessageSource[]) => void,
  onRetrievalHit?: (retrievalHit: boolean) => void,
  onError?: (message: string) => void,
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

  const processEventBlock = (block: string) => {
    const dataLines = block
      .split('\n')
      .filter((line) => line.startsWith('data: '))
      .map((line) => line.slice(6))

    if (dataLines.length === 0) return false

    const data = dataLines.join('\n')
    if (data === '[DONE]') return true

    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(data) as Record<string, unknown>
    } catch {
      return false
    }

    const eventType = typeof parsed.type === 'string' ? parsed.type : ''

    if (typeof parsed.session_id === 'string') onSession(parsed.session_id)

    if (eventType === 'meta') {
      return false
    }

    if (eventType === 'delta' && typeof parsed.delta === 'string') {
      onChunk(parsed.delta)
      return false
    }

    if (eventType === 'sources') {
      if (Array.isArray(parsed.sources) && onSources) onSources(parsed.sources as MessageSource[])
      if (typeof parsed.retrieval_hit === 'boolean' && onRetrievalHit) onRetrievalHit(parsed.retrieval_hit)
      return false
    }

    if (eventType === 'error' && typeof parsed.message === 'string') {
      onError?.(parsed.message)
      return false
    }

    if (eventType === 'done') {
      return false
    }

    if (typeof parsed.content === 'string') onChunk(parsed.content)
    if (Array.isArray(parsed.sources) && onSources) onSources(parsed.sources as MessageSource[])
    if (typeof parsed.retrieval_hit === 'boolean' && onRetrievalHit) onRetrievalHit(parsed.retrieval_hit)
    return false
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })

    const eventBlocks = buffer.split('\n\n')
    buffer = eventBlocks.pop() || ''
    for (const block of eventBlocks) {
      if (processEventBlock(block)) return
    }

    if (done) break
  }

  if (buffer.trim()) {
    processEventBlock(buffer)
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
