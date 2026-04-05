import { useEffect, useState } from 'react'

import { getSettings, saveSettings, testSettings } from '../api/settingsApi'

export function SettingsPage() {
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1')
  const [chatModel, setChatModel] = useState('gpt-4o-mini')
  const [embeddingModel, setEmbeddingModel] = useState('text-embedding-3-small')
  const [message, setMessage] = useState('')
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false)

  useEffect(() => {
    void getSettings().then((data) => {
      setApiKeyConfigured(Boolean(data.openai_api_key_configured))
      setBaseUrl(data.openai_base_url)
      setChatModel(data.chat_model)
      setEmbeddingModel(data.embedding_model)
    })
  }, [])

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="rounded-[32px] border border-border bg-white p-8 shadow-[0_18px_60px_rgba(15,23,42,0.05)]">
        <div className="text-xs uppercase tracking-[0.2em] text-text">设置</div>
        <h1 className="mt-3 text-3xl font-semibold text-text">模型与接口配置</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-text">
          配置聊天模型、Embedding 模型和兼容 OpenAI 协议的接口地址。这里的配置影响整个团队知识库问答和代码审查能力。
        </p>
        <div className="mt-8 grid gap-4">
          <div className="rounded-2xl border border-border bg-[#fafafa] px-4 py-3 text-sm text-text">
            API Key 状态：{apiKeyConfigured ? '已配置' : '未配置'}
          </div>
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="OpenAI API Key"
            className="rounded-2xl border border-border bg-white px-4 py-3.5 text-sm text-text outline-none"
          />
          <input
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="API Base URL"
            className="rounded-2xl border border-border bg-white px-4 py-3.5 text-sm text-text outline-none"
          />
          <input
            value={chatModel}
            onChange={(event) => setChatModel(event.target.value)}
            placeholder="Chat Model"
            className="rounded-2xl border border-border bg-white px-4 py-3.5 text-sm text-text outline-none"
          />
          <input
            value={embeddingModel}
            onChange={(event) => setEmbeddingModel(event.target.value)}
            placeholder="Embedding Model"
            className="rounded-2xl border border-border bg-white px-4 py-3.5 text-sm text-text outline-none"
          />
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={async () => {
                try {
                  await saveSettings({
                    openai_api_key: apiKey || undefined,
                    openai_base_url: baseUrl,
                    chat_model: chatModel,
                    embedding_model: embeddingModel,
                  })
                  setApiKeyConfigured(apiKeyConfigured || Boolean(apiKey))
                  setMessage('已保存设置')
                } catch (error) {
                  setMessage(error instanceof Error ? error.message : '保存失败')
                }
              }}
              className="rounded-2xl bg-accent px-5 py-3 text-sm font-medium text-white"
            >
              保存
            </button>
            <button
              type="button"
              onClick={async () => {
                try {
                  const result = await testSettings()
                  setMessage(result.message)
                } catch (error) {
                  setMessage(error instanceof Error ? error.message : '测试连接失败')
                }
              }}
              className="rounded-2xl border border-border bg-white px-5 py-3 text-sm text-text"
            >
              测试连接
            </button>
          </div>
          {message ? <div className="rounded-2xl border border-accent/15 bg-accentSoft px-4 py-3 text-sm text-text">{message}</div> : null}
        </div>
      </div>
    </div>
  )
}
