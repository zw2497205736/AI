import { useState } from 'react'

export function InputBar({ disabled, onSend }: { disabled?: boolean; onSend: (value: string) => void }) {
  const [value, setValue] = useState('')

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  return (
    <div className="border-t border-border bg-white px-6 py-5">
      <div className="mx-auto flex max-w-4xl gap-3">
        <textarea
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          className="min-h-24 flex-1 rounded-[28px] border border-border bg-white px-5 py-4 text-sm text-text shadow-[0_6px_24px_rgba(15,23,42,0.05)] outline-none placeholder:text-text"
          placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
        />
        <button
          type="button"
          disabled={disabled}
          onClick={submit}
          className="rounded-[24px] bg-accent px-6 py-4 text-sm font-medium text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
        >
          发送
        </button>
      </div>
    </div>
  )
}
