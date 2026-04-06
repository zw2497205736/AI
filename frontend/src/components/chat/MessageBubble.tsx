import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { Message } from '../../types'

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const shouldShowSourceSection = !isUser && (typeof message.retrievalHit === 'boolean' || (message.sources?.length ?? 0) > 0)

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-3xl rounded-[28px] px-5 py-4 text-sm leading-7 shadow-[0_10px_30px_rgba(15,23,42,0.05)] ${
          isUser ? 'rounded-br-md bg-[#10a37f] text-white' : 'rounded-bl-md border border-border bg-white text-text'
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          <div>
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
            {shouldShowSourceSection ? (
              <div className="mt-5 border-t border-slate-200 pt-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">回答来源</div>
                  {message.retrievalHit ? (
                    <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-medium text-emerald-700">已命中知识库</span>
                  ) : (
                    <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-700">未命中知识库</span>
                  )}
                </div>
                {message.retrievalHit && message.sources && message.sources.length > 0 ? (
                  <div className="mt-3 space-y-3">
                    {message.sources.map((source, index) => (
                      <div key={`${source.filename}-${index}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-sm font-medium text-slate-800">{source.filename}</div>
                          <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-600">{source.source_type}</span>
                          {typeof source.score === 'number' ? (
                            <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-600">score {source.score}</span>
                          ) : null}
                        </div>
                        <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-slate-600">{source.preview}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-700">
                    当前回答没有命中知识库文档来源，以上内容来自模型的通用理解与补充回答，不属于知识库引用结果。
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}
