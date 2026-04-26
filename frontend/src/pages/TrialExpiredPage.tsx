import { toast } from "sonner"

import { apiFetch } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const PRICING_URL = import.meta.env.VITE_PRICING_URL ?? ""
const CONTACT_URL = import.meta.env.VITE_SALES_CONTACT_URL ?? ""

async function handleSignOut() {
  try {
    await apiFetch("/auth/logout", { method: "POST" })
    window.location.href = "/login"
  } catch (error) {
    toast.error(error instanceof Error ? error.message : "Unable to sign out right now")
  }
}

export function TrialExpiredPage() {
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
            <CardTitle className="text-3xl tracking-tight">
              Thank you for trying Koinoflow
            </CardTitle>
            <CardDescription className="text-sm leading-6">
              Your free trial has ended. We hope you found value in building and sharing your
              operational skills. To keep using Koinoflow, choose a plan or talk to us about the
              right fit for your team.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {PRICING_URL ? (
            <Button asChild className="w-full" size="lg">
              <a href={PRICING_URL}>View pricing plans</a>
            </Button>
          ) : null}
          {CONTACT_URL ? (
            <Button asChild className="w-full" size="lg" variant="outline">
              <a href={CONTACT_URL}>Talk to sales</a>
            </Button>
          ) : null}
          <Button className="w-full" size="lg" variant="ghost" onClick={() => void handleSignOut()}>
            Sign out
          </Button>
          <p className="pt-2 text-center text-xs text-muted-foreground">
            Signed in with the wrong account? Sign out and return to the login page.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
