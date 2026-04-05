export async function streamCodeReview(
  code: string,
  language: string,
  file: File | null,
  onChunk: (content: string) => void,
) {
  const token = localStorage.getItem('auth_token')
  const formData = new FormData()
  formData.append('code', code)
  formData.append('language', language)
  if (file) {
    formData.append('file', file)
  }

  const response = await fetch('/api/code-review/stream', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  })
  if (!response.ok || !response.body) {
    throw new Error('Code review stream failed')
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
      if (parsed.content) onChunk(parsed.content)
    }
  }
}
