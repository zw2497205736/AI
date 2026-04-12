import { useEffect, useState } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import {
  createGitHubRepository,
  deleteGitHubRepository,
  getAgentTaskDetail,
  listAgentTasks,
  listGitHubRepositories,
  rerunAgentTask,
} from '../api/githubApi'
import type { AgentTaskDetail, AgentTaskSummary, AgentTrace, GitHubRepository } from '../types'


const statusClassName: Record<string, string> = {
  queued: 'border-amber-200 bg-amber-50 text-amber-700',
  running: 'border-sky-200 bg-sky-50 text-sky-700',
  running_review: 'border-sky-200 bg-sky-50 text-sky-700',
  running_test_suggestion: 'border-sky-200 bg-sky-50 text-sky-700',
  running_unit_test_generation: 'border-sky-200 bg-sky-50 text-sky-700',
  completed: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  partial_completed: 'border-orange-200 bg-orange-50 text-orange-700',
  failed: 'border-rose-200 bg-rose-50 text-rose-700',
}

const statusLabel: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  running_review: '生成评审中',
  running_test_suggestion: '生成测试建议中',
  running_unit_test_generation: '生成单测建议中',
  completed: '已完成',
  partial_completed: '部分完成',
  failed: '失败',
}

const statusStepLabel: Record<string, string> = {
  queued: '等待触发',
  running: '准备执行',
  running_review: '阶段 1 / Code Review',
  running_test_suggestion: '阶段 2 / 测试建议',
  running_unit_test_generation: '阶段 3 / 单测建议',
  completed: '全部阶段完成',
  partial_completed: '部分阶段完成',
  failed: '执行失败',
}

const stageMeta = [
  { key: 'review', title: 'Code Review', description: '识别逻辑、边界、可维护性与风险问题' },
  { key: 'test', title: '测试建议', description: '补齐测试重点、回归点和验证思路' },
  { key: 'unit', title: '单元测试建议 / 示例代码', description: '给出可直接参考的测试样例' },
] as const

const taskFilters = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '异常' },
] as const

function formatDateTime(value?: string) {
  if (!value) return '未知时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getAgentTrace(task: AgentTaskDetail | null): AgentTrace | null {
  if (!task?.source_payload || typeof task.source_payload !== 'object') {
    return null
  }
  const payload = task.source_payload as Record<string, unknown>
  const trace = payload.agent_trace
  if (!trace || typeof trace !== 'object') {
    return null
  }
  return trace as AgentTrace
}


export function GithubAgentPage() {
  const [repositories, setRepositories] = useState<GitHubRepository[]>([])
  const [tasks, setTasks] = useState<AgentTaskSummary[]>([])
  const [selectedTask, setSelectedTask] = useState<AgentTaskDetail | null>(null)
  const [activePanel, setActivePanel] = useState<'review' | 'test' | 'unit'>('review')
  const [taskFilter, setTaskFilter] = useState<'all' | 'running' | 'completed' | 'failed'>('all')
  const [submitting, setSubmitting] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [submitMessage, setSubmitMessage] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [form, setForm] = useState({
    repo_owner: '',
    repo_name: '',
    display_name: '',
    github_token: '',
    webhook_secret: '',
  })

  const loadRepositories = async () => {
    const data = await listGitHubRepositories()
    setRepositories(data)
  }

  const loadTasks = async () => {
    const data = await listAgentTasks()
    setTasks(data)
  }

  const loadTaskDetail = async (taskId: number) => {
    setLoadingDetail(true)
    try {
      const data = await getAgentTaskDetail(taskId)
      setSelectedTask(data)
      setActivePanel('review')
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    void loadRepositories()
    void loadTasks()
  }, [])

  useEffect(() => {
    if (!selectedTask) return
    const shouldPoll =
      selectedTask.status === 'queued' ||
      selectedTask.status.startsWith('running')
    if (!shouldPoll) return

    const timer = window.setInterval(() => {
      void loadTasks()
      void loadTaskDetail(selectedTask.id)
    }, 4000)

    return () => window.clearInterval(timer)
  }, [selectedTask])

  const completedCount = tasks.filter((task) => task.status === 'completed').length
  const runningCount = tasks.filter((task) => task.status.startsWith('running') || task.status === 'queued').length
  const failedCount = tasks.filter((task) => task.status === 'failed' || task.status === 'partial_completed').length

  const filteredTasks = tasks.filter((task) => {
    if (taskFilter === 'all') return true
    if (taskFilter === 'running') return task.status.startsWith('running') || task.status === 'queued'
    if (taskFilter === 'completed') return task.status === 'completed'
    return task.status === 'failed' || task.status === 'partial_completed'
  })

  const selectedTaskStatusLabel = selectedTask ? statusStepLabel[selectedTask.status] ?? selectedTask.status : '尚未选择任务'

  const activePanelContent = selectedTask
    ? activePanel === 'review'
      ? selectedTask.review_content
      : activePanel === 'test'
        ? selectedTask.test_suggestion_content
        : selectedTask.unit_test_generation_content
    : ''

  const activePanelTitle =
    activePanel === 'review' ? 'Code Review' : activePanel === 'test' ? '测试建议' : '单元测试建议 / 示例代码'
  const agentTrace = getAgentTrace(selectedTask)

  const renderAgentSection = (title: string, content: string) => {
    const failed = content.startsWith('生成失败：')
    return (
      <div className="rounded-[28px] border border-border bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.04)]">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="text-base font-semibold text-text">{title}</div>
          <div className="rounded-full bg-[#f3f4f6] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-text">
            {failed ? 'error' : 'output'}
          </div>
        </div>
        {failed ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-7 text-rose-700">{content}</div>
        ) : (
          <div className="markdown-body min-h-[84px] text-sm leading-7 text-text">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || '暂无结果'}</ReactMarkdown>
          </div>
        )}
      </div>
    )
  }

  const renderAgentTrace = () => {
    if (!agentTrace) {
      return (
        <div className="rounded-[28px] border border-dashed border-border bg-[#fafafa] p-5 text-sm leading-7 text-text">
          当前任务暂无 Agent 执行轨迹。
        </div>
      )
    }

    const plan = agentTrace.plan
    const toolCalls = agentTrace.tool_calls ?? []
    const replans = agentTrace.replans ?? []
    const fallbackEvents = agentTrace.fallback_events ?? []
    const knowledgeSources = agentTrace.knowledge_sources ?? []
    const executedSteps = agentTrace.executed_steps ?? []

    return (
      <div className="rounded-[28px] border border-border bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.04)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-text">Agent 执行轨迹</div>
            <div className="mt-1 text-sm text-text">展示本次 PR 审查的计划、工具调用、重规划与兜底记录。</div>
          </div>
          <div className="rounded-full bg-[#f3f4f6] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-text">
            {agentTrace.mode || 'agent'}
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-[24px] border border-border bg-[#fbfbfa] p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-text">Plan</div>
            <div className="mt-3 space-y-2 text-sm leading-7 text-text">
              <div>PR 类型：{plan?.pr_type || '未知'}</div>
              <div>关注点：{plan?.focus?.length ? plan.focus.join('、') : '无'}</div>
              <div>计划步骤：{plan?.steps?.length ? plan.steps.join(' → ') : '无'}</div>
              <div>知识查询：{plan?.knowledge_queries?.length ? plan.knowledge_queries.join('；') : '无'}</div>
              <div>备注：{plan?.planning_note || '无'}</div>
            </div>
          </div>

          <div className="rounded-[24px] border border-border bg-[#fbfbfa] p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-text">Execution</div>
            <div className="mt-3 space-y-2 text-sm leading-7 text-text">
              <div>执行步骤数：{executedSteps.length}</div>
              <div>工具调用数：{toolCalls.length}</div>
              <div>重规划次数：{replans.length}</div>
              <div>兜底事件数：{fallbackEvents.length}</div>
              <div>命中知识来源：{knowledgeSources.length}</div>
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr,0.9fr]">
          <div className="rounded-[24px] border border-border bg-[#fbfbfa] p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-text">Tool Calls</div>
            <div className="mt-3 space-y-3 text-sm text-text">
              {toolCalls.length === 0 ? <div>暂无工具调用</div> : null}
              {toolCalls.map((toolCall, index) => (
                <div key={`${toolCall.name}-${index}`} className="rounded-2xl border border-border bg-white p-3">
                  <div className="font-medium text-text">{toolCall.name}</div>
                  <div className="mt-1 text-xs leading-6 text-text">
                    参数：{toolCall.arguments && Object.keys(toolCall.arguments).length ? JSON.stringify(toolCall.arguments, null, 0) : '{}'}
                  </div>
                  <div className="mt-2 text-xs leading-6 text-text">{toolCall.output_preview || '无输出预览'}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-[24px] border border-border bg-[#fbfbfa] p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-text">Replans</div>
              <div className="mt-3 space-y-3 text-sm text-text">
                {replans.length === 0 ? <div>本次执行未触发重规划</div> : null}
                {replans.map((replan, index) => (
                  <div key={`${replan.reason || 'replan'}-${index}`} className="rounded-2xl border border-border bg-white p-3">
                    <div>原因：{replan.reason || '未知'}</div>
                    <div>重规划说明：{replan.replan_reason || '无'}</div>
                    <div>新关注点：{replan.new_focus?.length ? replan.new_focus.join('、') : '无'}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[24px] border border-border bg-[#fbfbfa] p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-text">Fallback</div>
              <div className="mt-3 space-y-2 text-sm text-text">
                {fallbackEvents.length === 0 ? <div>本次执行未触发兜底</div> : null}
                {fallbackEvents.map((event, index) => (
                  <div key={`${event}-${index}`} className="rounded-2xl border border-border bg-white px-3 py-2">
                    {event}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {agentTrace.execution_summary ? (
          <div className="mt-4 rounded-[24px] border border-border bg-[#fbfbfa] p-4">
            <div className="mb-3 text-xs uppercase tracking-[0.18em] text-text">Summary</div>
            <div className="markdown-body text-sm leading-7 text-text">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{agentTrace.execution_summary}</ReactMarkdown>
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-6 p-6">
      <section className="overflow-hidden rounded-[36px] border border-border bg-white shadow-[0_24px_80px_rgba(15,23,42,0.06)]">
        <div className="grid gap-6 bg-[linear-gradient(135deg,#f7faf8_0%,#eef8f5_42%,#ffffff_100%)] p-8 xl:grid-cols-[1.35fr,0.65fr]">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-text">GitHub Agent Workspace</div>
            <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.03em] text-text">PR 自动审查工作台</h1>
            <p className="mt-4 max-w-3xl text-sm leading-8 text-text">
              这里集中处理 GitHub Webhook、任务状态流转和 AI 输出结果。左侧看任务队列，右侧专注查看单个 PR 的完整审查内容。
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
            <div className="rounded-[28px] border border-white/70 bg-white/80 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.18em] text-text">仓库</div>
              <div className="mt-3 text-3xl font-semibold text-text">{repositories.length}</div>
              <div className="mt-2 text-sm text-text">当前已接入的 GitHub 仓库</div>
            </div>
            <div className="rounded-[28px] border border-white/70 bg-white/80 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.18em] text-text">运行中</div>
              <div className="mt-3 text-3xl font-semibold text-text">{runningCount}</div>
              <div className="mt-2 text-sm text-text">排队或仍在生成中的任务</div>
            </div>
            <div className="rounded-[28px] border border-white/70 bg-white/80 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.18em] text-text">已完成</div>
              <div className="mt-3 text-3xl font-semibold text-text">{completedCount}</div>
              <div className="mt-2 text-sm text-text">{failedCount > 0 ? `另有 ${failedCount} 个异常任务` : '当前没有异常任务'}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <section className="rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
          <div className="text-lg font-semibold text-text">接入仓库</div>
          <p className="mt-2 text-sm leading-7 text-text">
            建议使用 GitHub Personal Access Token，权限至少包含目标私有仓库读取权限。Webhook Secret 由你自己设置，稍后填到 GitHub Webhook。
          </p>
          <form
            className="mt-6 grid gap-4 md:grid-cols-2"
            onSubmit={async (event) => {
              event.preventDefault()
              setSubmitting(true)
              setSubmitMessage('')
              setSubmitError('')
              try {
                const result = await createGitHubRepository(form)
                setForm({
                  repo_owner: '',
                  repo_name: '',
                  display_name: '',
                  github_token: '',
                  webhook_secret: '',
                })
                await loadRepositories()
                setSubmitMessage(`连接成功。Webhook URL：${result.webhook_url}`)
              } catch (error) {
                if (axios.isAxiosError(error)) {
                  setSubmitError(error.response?.data?.detail || error.message || '连接失败')
                } else {
                  setSubmitError('连接失败，请稍后重试')
                }
              } finally {
                setSubmitting(false)
              }
            }}
          >
            <input
              value={form.repo_owner}
              onChange={(event) => setForm((current) => ({ ...current, repo_owner: event.target.value }))}
              placeholder="仓库 owner，例如 zhaowei"
              className="rounded-2xl border border-border bg-[#fbfbfa] px-4 py-3 text-sm outline-none"
              required
            />
            <input
              value={form.repo_name}
              onChange={(event) => setForm((current) => ({ ...current, repo_name: event.target.value }))}
              placeholder="仓库名，例如 AI"
              className="rounded-2xl border border-border bg-[#fbfbfa] px-4 py-3 text-sm outline-none"
              required
            />
            <input
              value={form.display_name}
              onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))}
              placeholder="显示名称，例如 AI 项目主仓库"
              className="rounded-2xl border border-border bg-[#fbfbfa] px-4 py-3 text-sm outline-none md:col-span-2"
              required
            />
            <input
              value={form.github_token}
              onChange={(event) => setForm((current) => ({ ...current, github_token: event.target.value }))}
              placeholder="GitHub Token"
              className="rounded-2xl border border-border bg-[#fbfbfa] px-4 py-3 text-sm outline-none md:col-span-2"
              required
            />
            <input
              value={form.webhook_secret}
              onChange={(event) => setForm((current) => ({ ...current, webhook_secret: event.target.value }))}
              placeholder="Webhook Secret"
              className="rounded-2xl border border-border bg-[#fbfbfa] px-4 py-3 text-sm outline-none md:col-span-2"
              required
            />
            <button
              type="submit"
              disabled={submitting}
              className="rounded-2xl bg-text px-5 py-3 text-sm font-medium text-white disabled:opacity-60 md:col-span-2"
            >
              {submitting ? '连接中...' : '连接仓库'}
            </button>
          </form>
          {submitMessage ? (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-7 text-emerald-700">
              {submitMessage}
            </div>
          ) : null}
          {submitError ? (
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-7 text-rose-700">
              {submitError}
            </div>
          ) : null}
        </section>

        <section className="rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
          <div className="text-lg font-semibold text-text">使用说明</div>
          <div className="mt-5 space-y-4 text-sm leading-7 text-text">
            <div className="rounded-2xl border border-border bg-[#fbfbfa] p-4">1. 添加仓库后，页面会生成对应的 Webhook URL。</div>
            <div className="rounded-2xl border border-border bg-[#fbfbfa] p-4">2. 到 GitHub 仓库设置页新增 Webhook，事件选择 `Pull requests`。</div>
            <div className="rounded-2xl border border-border bg-[#fbfbfa] p-4">3. Secret 填你在当前页面输入的 `webhook_secret`。</div>
            <div className="rounded-2xl border border-border bg-[#fbfbfa] p-4">4. PR 的 `opened / reopened / synchronize` 会自动触发 AI 审查。</div>
          </div>
        </section>
      </section>

      <section className="rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold text-text">已接入仓库</div>
            <div className="mt-1 text-sm text-text">连接状态和 webhook 地址集中放在这里。</div>
          </div>
          <button
            type="button"
            onClick={() => void loadRepositories()}
            className="rounded-2xl border border-border bg-white px-4 py-2.5 text-sm text-text shadow-sm"
          >
            刷新仓库
          </button>
        </div>
        <div className="mt-5 flex flex-col gap-4">
          {repositories.length === 0 ? <div className="rounded-2xl border border-dashed border-border bg-[#fafafa] p-5 text-sm text-text">暂无仓库配置</div> : null}
          {repositories.map((repo) => (
            <div key={repo.id} className="rounded-[26px] border border-border bg-[#fbfbfa] p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-base font-semibold text-text">{repo.display_name}</div>
                  <div className="mt-1 text-sm text-text">
                    {repo.repo_owner}/{repo.repo_name}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    await deleteGitHubRepository(repo.id)
                    if (selectedTask?.repo_id === repo.id) {
                      setSelectedTask(null)
                    }
                    await loadRepositories()
                    await loadTasks()
                  }}
                  className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
                >
                  删除
                </button>
              </div>
              <div className="mt-4 rounded-2xl border border-border bg-white p-4 text-xs leading-6 text-text">
                <div>Webhook URL：{repo.webhook_url}</div>
                <div>Secret 预览：{repo.webhook_secret_preview}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold text-text">任务队列</div>
            <div className="mt-1 text-sm text-text">按最新时间排序。任务区支持纵向滚动，优先点开最新完成或正在运行的任务。</div>
          </div>
          <button
            type="button"
            onClick={() => void loadTasks()}
            className="rounded-2xl border border-border bg-white px-4 py-2.5 text-sm text-text shadow-sm"
          >
            刷新任务
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {taskFilters.map((filter) => {
            const active = taskFilter === filter.key
            return (
              <button
                key={filter.key}
                type="button"
                onClick={() => setTaskFilter(filter.key)}
                className={`rounded-full px-4 py-2 text-sm transition ${
                  active ? 'bg-text text-white shadow-sm' : 'border border-border bg-white text-text'
                }`}
              >
                {filter.label}
              </button>
            )
          })}
        </div>

        <div className="gpt-scrollbar mt-5 grid max-h-[560px] gap-4 overflow-y-auto pr-1 lg:grid-cols-2">
          {filteredTasks.length === 0 ? <div className="rounded-2xl border border-dashed border-border bg-[#fafafa] p-5 text-sm text-text">当前筛选条件下没有任务</div> : null}
          {filteredTasks.map((task) => (
            <button
              key={task.id}
              type="button"
              onClick={() => void loadTaskDetail(task.id)}
              className={`rounded-[26px] border p-5 text-left transition ${
                selectedTask?.id === task.id
                  ? 'border-accent/30 bg-[linear-gradient(135deg,#edf8f4_0%,#ffffff_100%)] shadow-[0_14px_36px_rgba(16,163,127,0.10)]'
                  : 'border-border bg-[#fbfbfa] hover:border-accent/20 hover:bg-white'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="line-clamp-2 text-base font-semibold text-text">{task.title}</div>
                  <div className="mt-2 text-xs uppercase tracking-[0.18em] text-text">{task.repo_display_name}</div>
                </div>
                <span className={`rounded-full border px-3 py-1 text-xs ${statusClassName[task.status] ?? 'border-slate-200 bg-slate-100 text-slate-700'}`}>
                  {statusLabel[task.status] ?? task.status}
                </span>
              </div>
              <div className="mt-4 grid gap-2 text-xs leading-6 text-text sm:grid-cols-3">
                <div>PR：{task.pr_number ? `#${task.pr_number}` : '无'}</div>
                <div>事件：{task.event_type}</div>
                <div>阶段：{statusStepLabel[task.status] ?? task.status}</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text">
                <span>创建：{formatDateTime(task.created_at)}</span>
                <span>更新：{formatDateTime(task.updated_at)}</span>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
        {loadingDetail ? <div className="text-sm text-text">正在加载任务详情...</div> : null}
        {!loadingDetail && !selectedTask ? (
          <div className="rounded-[28px] border border-dashed border-border bg-[#fafafa] p-8">
            <div className="text-xs uppercase tracking-[0.2em] text-text">Task Detail</div>
            <div className="mt-3 text-2xl font-semibold text-text">选择上方任务后查看完整结果</div>
            <div className="mt-4 max-w-2xl text-sm leading-8 text-text">
              这里会显示当前任务的执行阶段、错误信息以及三段 AI 输出。建议优先点开最新一个任务，不要反复查看旧任务。
            </div>
          </div>
        ) : null}

        {!loadingDetail && selectedTask ? (
          <div className="space-y-6">
            <div className="flex flex-col gap-4 rounded-[28px] border border-border bg-[linear-gradient(135deg,#ffffff_0%,#f7faf8_100%)] p-6 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.2em] text-text">Task Detail</div>
                <div className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-text">{selectedTask.title}</div>
                <div className="mt-3 flex flex-wrap gap-2 text-sm text-text">
                  <span className="rounded-full border border-border bg-white px-3 py-1">PR：{selectedTask.pr_number ? `#${selectedTask.pr_number}` : '无'}</span>
                  <span className="rounded-full border border-border bg-white px-3 py-1">事件：{selectedTask.event_type}</span>
                  <span className="rounded-full border border-border bg-white px-3 py-1">阶段：{selectedTaskStatusLabel}</span>
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setSelectedTask(null)}
                  className="rounded-2xl border border-border bg-white px-4 py-2.5 text-sm text-text shadow-sm"
                >
                  收起详情
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    const rerun = await rerunAgentTask(selectedTask.id)
                    await loadTasks()
                    if (rerun?.id) {
                      await loadTaskDetail(rerun.id)
                    }
                  }}
                  className="rounded-2xl bg-text px-4 py-2.5 text-sm font-medium text-white shadow-sm"
                >
                  重新执行
                </button>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              {stageMeta.map((stage, index) => (
                <div key={stage.key} className="rounded-[24px] border border-border bg-[#fbfbfa] p-5">
                  <div className="text-xs uppercase tracking-[0.18em] text-text">Stage 0{index + 1}</div>
                  <div className="mt-3 text-base font-semibold text-text">{stage.title}</div>
                  <div className="mt-2 text-sm leading-7 text-text">{stage.description}</div>
                </div>
              ))}
            </div>

            {selectedTask.error_message ? (
              <div className="rounded-[28px] border border-rose-200 bg-rose-50 p-5 text-sm leading-7 text-rose-700">
                执行失败：{selectedTask.error_message}
              </div>
            ) : null}

            <div className="rounded-[28px] border border-border bg-[#fbfbfa] p-3">
              <div className="grid gap-3 md:grid-cols-3">
                {stageMeta.map((stage) => {
                  const isActive = activePanel === stage.key
                  const content =
                    stage.key === 'review'
                      ? selectedTask.review_content
                      : stage.key === 'test'
                        ? selectedTask.test_suggestion_content
                        : selectedTask.unit_test_generation_content
                  const hasFailure = content.startsWith('生成失败：')
                  return (
                    <button
                      key={stage.key}
                      type="button"
                      onClick={() => setActivePanel(stage.key)}
                      className={`rounded-[22px] border p-4 text-left transition ${
                        isActive
                          ? 'border-accent/30 bg-white shadow-[0_10px_26px_rgba(15,23,42,0.05)]'
                          : 'border-transparent bg-transparent hover:border-border hover:bg-white/70'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-text">{stage.title}</div>
                        <div
                          className={`rounded-full px-2.5 py-1 text-[11px] ${
                            hasFailure ? 'bg-rose-100 text-rose-700' : content ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-700'
                          }`}
                        >
                          {hasFailure ? '异常' : content ? '已生成' : '空'}
                        </div>
                      </div>
                      <div className="mt-2 text-sm leading-6 text-text">{stage.description}</div>
                    </button>
                  )
                })}
              </div>
            </div>

            {renderAgentTrace()}

            {renderAgentSection(activePanelTitle, activePanelContent)}
          </div>
        ) : null}
      </section>
    </div>
  )
}
