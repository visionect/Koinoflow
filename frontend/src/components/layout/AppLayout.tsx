import { Navigate, Outlet, useParams } from "react-router-dom"

import { useAuth } from "@/hooks/useAuth"
import { LoadingScreen } from "@/components/shared/LoadingScreen"
import { AppSidebar } from "@/components/layout/AppSidebar"
import { TopNav } from "@/components/layout/TopNav"
import { TrialBanner } from "@/components/layout/TrialBanner"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

export function AppLayout() {
  const { workspace } = useParams<{ workspace: string }>()
  const { isLoading, isAuthenticated, hasWorkspace, hasActiveSubscription, workspaceSlug } =
    useAuth()

  if (isLoading) {
    return <LoadingScreen />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (!hasWorkspace) {
    return <Navigate to="/onboarding" replace />
  }

  if (!hasActiveSubscription) {
    return <Navigate to="/trial-expired" replace />
  }

  if (workspaceSlug && workspaceSlug !== workspace) {
    return <Navigate to={`/${workspaceSlug}`} replace />
  }

  return (
    <SidebarProvider defaultOpen>
      <AppSidebar />
      <SidebarInset className="min-w-0 overflow-hidden">
        <TrialBanner />
        <TopNav />
        <main className="min-w-0 flex-1 overflow-hidden px-4 py-6 md:px-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
