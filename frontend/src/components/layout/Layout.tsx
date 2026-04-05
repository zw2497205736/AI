import type { PropsWithChildren } from 'react'

import { Sidebar } from './Sidebar'

export function Layout({ children }: PropsWithChildren) {
  return (
    <div className="relative flex min-h-screen overflow-hidden bg-[#f7f7f5] text-text">
      <div
        className="pointer-events-none absolute left-[52%] top-[19%] h-[255px] w-[255px] -translate-x-1/2 bg-center bg-no-repeat opacity-[0.2]"
        style={{ backgroundImage: "url('/校徽.png')", backgroundSize: 'contain' }}
      />
      <Sidebar />
      <main className="relative z-10 flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
