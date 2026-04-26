import React from "react"
import { Navigate, Route, Routes } from "react-router-dom"

import { useAuth } from "@/hooks/useAuth"
import { AppLayout } from "@/components/layout/AppLayout"
import { LoadingScreen } from "@/components/shared/LoadingScreen"
import { AcceptInvitationPage } from "@/pages/AcceptInvitationPage"
import { consumeInvitationToken } from "@/lib/invitationToken"
import { DashboardPage } from "@/pages/DashboardPage"
import { DepartmentDetailPage } from "@/pages/departments/DepartmentDetailPage"
import { LoginPage } from "@/pages/LoginPage"
import { OnboardingPage } from "@/pages/OnboardingPage"
import { SkillEditPage } from "@/pages/skills/SkillEditPage"
import { SkillHistoryPage } from "@/pages/skills/SkillHistoryPage"
import { SkillListPage } from "@/pages/skills/SkillListPage"
import { SkillViewPage } from "@/pages/skills/SkillViewPage"
import { ApiKeysPage } from "@/pages/settings/ApiKeysPage"
import { McpPage } from "@/pages/settings/McpPage"
import { CandidatesPage } from "@/pages/capture/CandidatesPage"
import { ConnectorsPage } from "@/pages/settings/ConnectorsPage"
import { MembersPage } from "@/pages/settings/MembersPage"
import { SettingsPage } from "@/pages/settings/SettingsPage"
import { TeamDetailPage } from "@/pages/teams/TeamDetailPage"
import { TeamListPage } from "@/pages/teams/TeamListPage"
import { UsageDashboardPage } from "@/pages/usage/UsageDashboardPage"
import { TrialExpiredPage } from "@/pages/TrialExpiredPage"

function RootRedirect() {
  const { isLoading, isAuthenticated, hasWorkspace, hasActiveSubscription, workspaceSlug } =
    useAuth()

  if (isLoading) {
    return <LoadingScreen label="Checking session..." />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  const pendingToken = consumeInvitationToken()
  if (pendingToken) {
    return <Navigate to={`/invitations/${pendingToken}/accept`} replace />
  }

  if (!hasWorkspace) {
    return <Navigate to="/onboarding" replace />
  }

  if (!hasActiveSubscription) {
    return <Navigate to="/trial-expired" replace />
  }

  return <Navigate to={`/${workspaceSlug}`} replace />
}

function RequireFeature({ flag, children }: { flag: string; children: React.ReactNode }) {
  const { isLoading, hasFeature } = useAuth()
  if (isLoading) return <LoadingScreen label="Loading..." />
  if (!hasFeature(flag)) return <Navigate to="." replace />
  return <>{children}</>
}

function TrialExpiredRoute() {
  const { isLoading, billingEnabled } = useAuth()
  if (isLoading) return <LoadingScreen label="Loading..." />
  if (!billingEnabled) return <Navigate to="/" replace />
  return <TrialExpiredPage />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/onboarding" element={<OnboardingPage />} />
      <Route path="/invitations/:token/accept" element={<AcceptInvitationPage />} />
      <Route path="/trial-expired" element={<TrialExpiredRoute />} />

      <Route path="/:workspace" element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="teams" element={<TeamListPage />} />
        <Route path="teams/:teamSlug" element={<TeamDetailPage />} />
        <Route path="depts/:departmentId" element={<DepartmentDetailPage />} />
        <Route path="skills" element={<SkillListPage />} />
        <Route path="skills/:skillSlug" element={<SkillViewPage />} />
        <Route path="skills/:skillSlug/edit" element={<SkillEditPage />} />
        <Route path="skills/:skillSlug/history" element={<SkillHistoryPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="settings/members" element={<MembersPage />} />
        <Route path="settings/mcp" element={<McpPage />} />
        <Route path="settings/keys" element={<ApiKeysPage />} />
        <Route
          path="capture/connectors"
          element={
            <RequireFeature flag="capture">
              <ConnectorsPage />
            </RequireFeature>
          }
        />
        <Route
          path="capture/candidates"
          element={
            <RequireFeature flag="capture">
              <CandidatesPage />
            </RequireFeature>
          }
        />
        <Route path="usage" element={<UsageDashboardPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
