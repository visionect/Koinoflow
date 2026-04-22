import * as React from "react"

import { Navigate, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import { apiFetch, queryKeys } from "@/api/client"
import { useAuth } from "@/hooks/useAuth"
import { LoadingScreen } from "@/components/shared/LoadingScreen"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useQueryClient } from "@tanstack/react-query"
import { storeInvitationToken } from "@/lib/invitationToken"
import { AlertTriangleIcon } from "lucide-react"

export function AcceptInvitationPage() {
  const { token } = useParams<{ token: string }>()
  const { isLoading, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [accepting, setAccepting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const attemptedRef = React.useRef(false)

  React.useEffect(() => {
    if (isLoading || !token || attemptedRef.current) return

    if (!isAuthenticated) {
      storeInvitationToken(token)
      return
    }

    attemptedRef.current = true
    setAccepting(true)

    apiFetch<{ detail: string }>(`/invitations/${token}/accept`, {
      method: "POST",
    })
      .then(async () => {
        await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me })
        toast.success("Invitation accepted! Welcome to the workspace.")
        navigate("/", { replace: true })
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : "Failed to accept invitation"
        setError(message)
        toast.error(message)
      })
      .finally(() => setAccepting(false))
  }, [isLoading, isAuthenticated, token, navigate, queryClient])

  if (!token) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-muted/20 px-4">
        <Card className="w-full max-w-md border-destructive/20">
          <CardHeader className="items-center text-center">
            <div
              className="flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive"
              aria-hidden
            >
              <AlertTriangleIcon className="size-5" />
            </div>
            <CardTitle>Invitation link is invalid</CardTitle>
            <CardDescription className="max-w-sm text-sm leading-6">
              This link is missing its invitation token. Ask the person who invited you to resend
              the email, or sign in if you already have access.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center gap-2">
            <Button asChild>
              <a href="/login">Sign in</a>
            </Button>
            <Button asChild variant="outline">
              <a href="/">Go to dashboard</a>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (isLoading) {
    return <LoadingScreen label="Checking your session…" />
  }

  if (accepting) {
    return <LoadingScreen label="Joining workspace…" />
  }

  if (!isAuthenticated) {
    storeInvitationToken(token)
    return <Navigate to="/login" replace />
  }

  if (error) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-muted/20 px-4">
        <Card className="w-full max-w-md border-destructive/20">
          <CardHeader className="items-center text-center">
            <div
              className="flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive"
              aria-hidden
            >
              <AlertTriangleIcon className="size-5" />
            </div>
            <CardTitle>Unable to accept invitation</CardTitle>
            <CardDescription className="max-w-sm text-sm leading-6">{error}</CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center gap-2">
            <Button
              variant="outline"
              onClick={() => {
                attemptedRef.current = false
                setError(null)
              }}
            >
              Try again
            </Button>
            <Button asChild>
              <a href="/">Go to dashboard</a>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return <LoadingScreen label="Processing invitation…" />
}
