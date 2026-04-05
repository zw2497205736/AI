import { Navigate, Outlet } from 'react-router-dom'
import type { PropsWithChildren } from 'react'

import { useAuthStore } from '../../store/authStore'
import { Layout } from './Layout'

export function ProtectedLayout({ children }: PropsWithChildren) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <Layout>{children ?? <Outlet />}</Layout>
}
