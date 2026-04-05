import type { Message } from '../../types'
import { MessageBubble } from './MessageBubble'

export function ChatWindow({ messages, isStreaming }: { messages: Message[]; isStreaming: boolean }) {
  return (
    <div className="gpt-scrollbar flex-1 overflow-y-auto px-6 py-8">
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        {messages.length === 0 ? (
          <div className="rounded-[32px] border border-border bg-white p-12 shadow-[0_16px_50px_rgba(15,23,42,0.05)]">
            <div className="text-xs uppercase tracking-[0.2em] text-text">智能问答</div>
            <div className="mt-4 text-2xl font-semibold text-text">从团队知识库开始提问</div>
            <div className="mt-4 max-w-2xl text-sm leading-7 text-text">
              上传团队文档后开始提问，系统会优先结合知识库进行回答。你可以把不同研发主题拆成多个对话，分别保存和持续追问。
            </div>
            <div className="mt-8 grid gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-border bg-[#fafafa] p-4 text-sm text-text">知识库问答：基于已上传资料生成回答</div>
              <div className="rounded-2xl border border-border bg-[#fafafa] p-4 text-sm text-text">多对话管理：每个主题单独保存、重命名、切换</div>
              <div className="rounded-2xl border border-border bg-[#fafafa] p-4 text-sm text-text">长期记忆：沉淀用户偏好和重要上下文</div>
            </div>
          </div>
        ) : (
          messages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}
        {isStreaming ? <div className="animate-pulse text-sm text-text">AI 正在生成回答...</div> : null}
      </div>
    </div>
  )
}
