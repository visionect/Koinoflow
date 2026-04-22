import { AlertTriangleIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type ErrorStateProps = {
  title?: string
  message: string
  retryLabel?: string
  onRetry?: () => void
}

export function ErrorState({
  title = "Something went wrong",
  message,
  retryLabel = "Try again",
  onRetry,
}: ErrorStateProps) {
  return (
    <Card className="border-destructive/20">
      <CardHeader className="items-center text-center">
        <div className="flex size-11 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangleIcon className="size-5" aria-hidden />
        </div>
        <CardTitle>{title}</CardTitle>
        <CardDescription className="max-w-xl text-sm leading-6">{message}</CardDescription>
      </CardHeader>
      {onRetry ? (
        <CardContent className="flex justify-center">
          <Button variant="outline" onClick={onRetry}>
            {retryLabel}
          </Button>
        </CardContent>
      ) : null}
    </Card>
  )
}
