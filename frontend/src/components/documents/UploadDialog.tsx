import { useState } from 'react'

export function UploadDialog({ onUpload }: { onUpload: (file: File, description: string) => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null)
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)

  return (
    <div className="rounded-[32px] border border-border bg-white p-6 shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
      <div className="mb-1 text-base font-semibold text-text">上传文档</div>
      <div className="mb-5 text-sm text-text">建议上传结构化资料、需求文档、规范文档或沉淀材料，便于后续问答引用。</div>
      <div className="flex flex-col gap-3">
        <input
          type="file"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="rounded-2xl border border-dashed border-border bg-[#fafafa] px-4 py-4 text-sm text-text"
        />
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="描述（可选）"
          className="rounded-2xl border border-border bg-[#fbfbfc] px-4 py-3.5 text-sm text-text outline-none"
        />
        <button
          type="button"
          disabled={!file || loading}
          onClick={async () => {
            if (!file) return
            setLoading(true)
            try {
              await onUpload(file, description)
              setFile(null)
              setDescription('')
            } finally {
              setLoading(false)
            }
          }}
          className="rounded-2xl bg-accent px-4 py-3.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? '上传中...' : '上传'}
        </button>
      </div>
    </div>
  )
}
