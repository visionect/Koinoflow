import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type EmptyStateProps = {
  title: string
  description: string
  actionLabel?: string
  actionHref?: string
  action?: ReactNode
}

export function EmptyState({
  title,
  description,
  actionLabel,
  actionHref,
  action,
}: EmptyStateProps) {
  return (
    <Card className="border-dashed">
      <CardHeader className="text-center">
        <CardTitle role="heading" aria-level={2}>
          {title}
        </CardTitle>
        <CardDescription className="mx-auto max-w-xl">{description}</CardDescription>
      </CardHeader>
      {(action || (actionLabel && actionHref)) && (
        <CardContent className="flex justify-center">
          {action ?? (
            <Button asChild>
              <Link to={actionHref!}>{actionLabel}</Link>
            </Button>
          )}
        </CardContent>
      )}
    </Card>
  )
}
