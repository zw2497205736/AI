import { useState } from 'react'

import { streamCodeReview } from '../api/codeReviewApi'
import { ReviewForm } from '../components/code-review/ReviewForm'
import { ReviewReport } from '../components/code-review/ReviewReport'

export function CodeReviewPage() {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)

  return (
    <div className="flex h-screen flex-col gap-6 p-6">
      <div className="rounded-[32px] border border-border bg-white p-8 shadow-[0_18px_60px_rgba(15,23,42,0.05)]">
        <div className="text-xs uppercase tracking-[0.2em] text-text">Code Review</div>
        <h1 className="mt-3 text-3xl font-semibold text-text">AI 代码审查</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-text">
          粘贴代码、Diff 或上传补丁文件，系统会从可读性、风险点、潜在缺陷和改进建议几个角度生成结构化审查结果。
        </p>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 xl:grid-cols-2">
        <ReviewForm
          disabled={loading}
          onSubmit={async ({ code, language, file }) => {
            setContent('')
            setLoading(true)
            try {
              await streamCodeReview(code, language, file, (chunk) => setContent((current) => current + chunk))
            } finally {
              setLoading(false)
            }
          }}
        />
        <ReviewReport content={content || (loading ? '正在生成审查报告...' : '')} />
      </div>
    </div>
  )
}
