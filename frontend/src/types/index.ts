export interface MessageSource {
  filename: string
  source_type: string
  score?: number | null
  preview: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  sources?: MessageSource[]
  retrievalHit?: boolean
}

export interface Document {
  id: number
  filename: string
  doc_type: string
  description?: string | null
  status: 'processing' | 'ready' | 'error'
  chunk_count: number
  created_at: string
  error_message?: string | null
}

export interface LongTermMemory {
  id: number
  key: string
  value: string
  created_at: string
}

export interface ConversationSummary {
  session_id: string
  title: string
  created_at: string
}

export interface GitHubRepository {
  id: number
  repo_owner: string
  repo_name: string
  display_name: string
  is_active: boolean
  webhook_url: string
  webhook_secret_preview: string
  token_preview: string
  created_at: string
}

export interface AgentTaskSummary {
  id: number
  repo_id: number
  repo_display_name: string
  task_type: string
  event_type: string
  pr_number?: number | null
  commit_sha?: string | null
  title: string
  status: string
  error_message?: string | null
  created_at: string
  updated_at: string
}

export interface AgentTaskDetail extends AgentTaskSummary {
  review_content: string
  test_suggestion_content: string
  unit_test_generation_content: string
  source_payload?: Record<string, unknown> | null
}
