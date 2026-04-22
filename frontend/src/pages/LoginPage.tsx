import { Navigate } from "react-router-dom"

import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingScreen } from "@/components/shared/LoadingScreen"

export function LoginPage() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <LoadingScreen label="Checking your session…" />
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(37,99,235,0.12),_transparent_35%),linear-gradient(180deg,_rgba(248,250,252,1)_0%,_rgba(241,245,249,1)_100%)] px-4 dark:bg-[radial-gradient(circle_at_top,_rgba(96,165,250,0.18),_transparent_30%),linear-gradient(180deg,_rgba(2,6,23,1)_0%,_rgba(15,23,42,1)_100%)]">
      <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(37,99,235,0.04),transparent_45%,rgba(15,23,42,0.08))]" />
      <Card className="relative z-10 w-full max-w-md border-white/50 bg-background/90 shadow-2xl backdrop-blur">
        <CardHeader className="space-y-4 text-center">
          <div
            className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg"
            aria-label="Koinoflow"
          >
            KF
          </div>
          <div className="space-y-2">
            <CardTitle className="text-3xl tracking-tight">Welcome to Koinoflow</CardTitle>
            <CardDescription className="text-sm leading-6">
              Turn operational knowledge into production-ready processes your teams and AI clients
              can trust.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-center text-sm text-muted-foreground">
            Choose a provider to create or access your workspace.
          </p>
          <Button asChild className="w-full" size="lg" variant="outline">
            <a href="/accounts/google/login/?process=login">Continue with Google</a>
          </Button>
          <Button asChild className="w-full" size="lg" variant="outline">
            <a href="/accounts/github/login/?process=login">Continue with GitHub</a>
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            We use Google or GitHub to sign you in &mdash; there&rsquo;s no separate Koinoflow
            password.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
