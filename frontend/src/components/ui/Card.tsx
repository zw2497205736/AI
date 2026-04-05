import type { PropsWithChildren } from 'react'

export function Card({ children }: PropsWithChildren) {
  return <div className="rounded-3xl border border-border bg-panel p-5">{children}</div>
}

