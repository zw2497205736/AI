import { apiClient } from './axios'
import type { Document } from '../types'

export async function listDocuments() {
  const { data } = await apiClient.get<Document[]>('/api/documents/')
  return data
}

export async function uploadDocument(file: File, description: string) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('description', description)
  const { data } = await apiClient.post('/api/documents/upload', formData)
  return data
}

export async function deleteDocument(id: number) {
  const { data } = await apiClient.delete(`/api/documents/${id}`)
  return data
}

