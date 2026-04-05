import { useEffect, useState } from 'react'

import { deleteDocument, listDocuments, uploadDocument } from '../api/documentApi'
import { DocumentList } from '../components/documents/DocumentList'
import { UploadDialog } from '../components/documents/UploadDialog'
import type { Document } from '../types'

export function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([])

  const loadDocuments = async () => {
    const data = await listDocuments()
    setDocuments(data)
  }

  useEffect(() => {
    void loadDocuments()
  }, [])

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-6">
      <div className="rounded-[32px] border border-border bg-white p-8 shadow-[0_18px_60px_rgba(15,23,42,0.05)]">
        <div className="text-xs uppercase tracking-[0.2em] text-text">知识库</div>
        <h1 className="mt-3 text-3xl font-semibold text-text">管理团队资料</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-text">
          上传 Markdown、PDF、Word 等文档作为统一知识来源。文档入库后，智能问答会优先基于这些资料进行检索和回答。
        </p>
      </div>
      <UploadDialog
        onUpload={async (file, description) => {
          await uploadDocument(file, description)
          await loadDocuments()
        }}
      />
      <DocumentList
        documents={documents}
        onDelete={async (id) => {
          await deleteDocument(id)
          await loadDocuments()
        }}
      />
    </div>
  )
}
