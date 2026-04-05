import type { LongTermMemory } from '../../types'

function formatMemoryKey(key: string) {
  return key.replace(/_/g, ' ')
}

export function MemoryPanel({
  memories,
  onDelete,
}: {
  memories: LongTermMemory[]
  onDelete: (memoryId: number) => void
}) {
  return (
    <aside className="gpt-scrollbar hidden w-80 overflow-y-auto border-l border-border bg-[#f8f8f7] xl:block">
      <div className="border-b border-border px-5 py-5">
        <div className="text-sm font-semibold text-text">长期记忆</div>
        <div className="mt-1 text-xs leading-5 text-text">保存当前账号在长期对话中沉淀的偏好、背景和稳定事实。</div>
      </div>
      <div className="flex flex-col gap-3 p-4">
        {memories.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border bg-white p-4 text-sm text-text">暂无长期记忆</div>
        ) : (
          memories.map((memory) => (
            <div key={memory.id} className="rounded-2xl border border-border bg-white p-4 shadow-[0_8px_26px_rgba(15,23,42,0.04)]">
              <div className="mb-2 flex items-start justify-between gap-3">
                <div className="text-xs uppercase tracking-wide text-text">{formatMemoryKey(memory.key)}</div>
                <button type="button" onClick={() => onDelete(memory.id)} className="text-xs text-red-500">
                  删除
                </button>
              </div>
              <div className="text-sm text-text">{memory.value}</div>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
