import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function ReviewReport({ content }: { content: string }) {
  return (
    <div className="gpt-scrollbar h-full overflow-y-auto rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-text">审查报告</h2>
        <button
          type="button"
          onClick={() => {
            const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
            const url = URL.createObjectURL(blob)
            const anchor = document.createElement('a')
            anchor.href = url
            anchor.download = 'code-review-report.md'
            anchor.click()
            URL.revokeObjectURL(url)
          }}
          className="rounded-xl border border-border bg-white px-3 py-2 text-sm text-text"
        >
          下载 Markdown
        </button>
      </div>
      <div className="markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || '等待审查结果...'}</ReactMarkdown>
      </div>
    </div>
  )
}
