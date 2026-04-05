import type { PropsWithChildren } from 'react'

export function Badge({ children }: PropsWithChildren) {
  return <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-muted">{children}</span>
}

