import { useState } from 'react'

export function ReviewForm({
  disabled,
  onSubmit,
}: {
  disabled?: boolean
  onSubmit: (payload: { code: string; language: string; file: File | null }) => Promise<void>
}) {
  const [code, setCode] = useState('')
  const [language, setLanguage] = useState('diff')
  const [file, setFile] = useState<File | null>(null)

  return (
    <div className="flex h-full flex-col gap-4 rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-text">输入代码或 Diff</h2>
        <select
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
          className="rounded-xl border border-border bg-white px-3 py-2 text-sm text-text outline-none"
        >
          <option value="diff">diff</option>
          <option value="python">python</option>
          <option value="typescript">typescript</option>
          <option value="java">java</option>
        </select>
      </div>
      <textarea
        value={code}
        onChange={(event) => setCode(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
            event.preventDefault()
            void onSubmit({ code, language, file })
          }
        }}
        className="min-h-[420px] flex-1 rounded-[24px] border border-border bg-white p-4 font-mono text-sm text-text outline-none"
        placeholder="粘贴代码变更，或上传 .diff 文件"
      />
      <input
        type="file"
        accept=".diff,.patch,.txt"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        className="rounded-2xl border border-dashed border-border bg-[#fafafa] px-4 py-4 text-sm text-text"
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSubmit({ code, language, file })}
        className="rounded-2xl bg-accent px-4 py-3.5 text-sm font-medium text-white disabled:opacity-50"
      >
        开始审查
      </button>
    </div>
  )
}
