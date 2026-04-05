import type { Document } from '../../types'

export function DocumentList({ documents, onDelete }: { documents: Document[]; onDelete: (id: number) => void }) {
  return (
    <div className="overflow-hidden rounded-[32px] border border-border bg-white shadow-[0_16px_48px_rgba(15,23,42,0.05)]">
      <div className="border-b border-border px-6 py-5">
        <div className="text-base font-semibold text-text">已入库文档</div>
        <div className="mt-1 text-sm text-text">这里显示当前团队知识库中的全部资料及处理状态。</div>
      </div>
      <table className="min-w-full text-left text-sm text-text">
        <thead className="bg-[#fafafa] text-text">
          <tr>
            <th className="px-6 py-4">文件名</th>
            <th className="px-6 py-4">类型</th>
            <th className="px-6 py-4">状态</th>
            <th className="px-6 py-4">分块数</th>
            <th className="px-6 py-4">时间</th>
            <th className="px-6 py-4">操作</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-t border-border">
              <td className="px-6 py-4 font-medium text-text">{doc.filename}</td>
              <td className="px-6 py-4 text-text">{doc.doc_type}</td>
              <td className="px-6 py-4">
                <span
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    doc.status === 'ready'
                      ? 'bg-accentSoft text-accent'
                      : doc.status === 'error'
                        ? 'bg-red-50 text-red-500'
                        : 'bg-[#f3f4f6] text-text'
                  }`}
                >
                  {doc.status}
                </span>
              </td>
              <td className="px-6 py-4">{doc.chunk_count}</td>
              <td className="px-6 py-4 text-text">{doc.created_at}</td>
              <td className="px-6 py-4">
                <button className="text-red-500" onClick={() => onDelete(doc.id)}>
                  删除
                </button>
              </td>
            </tr>
          ))}
          {documents.length === 0 ? (
            <tr>
              <td className="px-6 py-10 text-center text-text" colSpan={6}>
                暂无文档
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}
