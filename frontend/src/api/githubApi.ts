import { apiClient } from './axios'


export async function listGitHubRepositories() {
  const { data } = await apiClient.get('/api/github/repositories')
  return data
}


export async function createGitHubRepository(payload: {
  repo_owner: string
  repo_name: string
  display_name: string
  github_token: string
  webhook_secret: string
}) {
  const { data } = await apiClient.post('/api/github/repositories', payload)
  return data
}


export async function deleteGitHubRepository(repoId: number) {
  const { data } = await apiClient.delete(`/api/github/repositories/${repoId}`)
  return data
}


export async function listAgentTasks() {
  const { data } = await apiClient.get('/api/github/tasks')
  return data
}


export async function getAgentTaskDetail(taskId: number) {
  const { data } = await apiClient.get(`/api/github/tasks/${taskId}`)
  return data
}


export async function rerunAgentTask(taskId: number) {
  const { data } = await apiClient.post(`/api/github/tasks/${taskId}/rerun`)
  return data
}
