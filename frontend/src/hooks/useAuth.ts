import { useMe } from "@/api/client"

export function useAuth() {
  const { data, ...query } = useMe()

  const billingEnabled = data?.billing_enabled ?? false
  const subscriptionStatus = data?.subscription_status ?? null
  const featureFlags = data?.feature_flags ?? []

  const hasActiveSubscription = billingEnabled
    ? subscriptionStatus === "active" || subscriptionStatus === "in_trial"
    : true

  return {
    ...query,
    user: data?.user ?? null,
    workspaceSlug: data?.workspace_slug ?? null,
    role: data?.role ?? null,
    isAuthenticated: Boolean(data?.user),
    hasWorkspace: Boolean(data?.workspace_slug),
    isAdmin: data?.role === "admin",
    isEditor: data?.role === "admin" || data?.role === "team_manager",
    billingEnabled,
    subscriptionStatus,
    hasActiveSubscription,
    trialEnd: data?.trial_end ?? null,
    featureFlags,
    hasFeature: (flag: string) => featureFlags.includes(flag),
  }
}
