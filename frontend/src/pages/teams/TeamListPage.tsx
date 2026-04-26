import * as React from "react"

import { PlusIcon } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { useCreateTeam, useTeams } from "@/api/client"
import { useAuth } from "@/hooks/useAuth"
import { buildWorkspacePath, formatDateOnly, slugify } from "@/lib/format"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"

export function TeamListPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const { isEditor } = useAuth()
  const teamsQuery = useTeams()
  const createTeam = useCreateTeam()

  const [open, setOpen] = React.useState(false)
  const [name, setName] = React.useState("")
  const [slug, setSlug] = React.useState("")
  const [slugTouched, setSlugTouched] = React.useState(false)

  React.useEffect(() => {
    if (!slugTouched) {
      setSlug(slugify(name))
    }
  }, [name, slugTouched])

  async function handleCreateTeam() {
    try {
      await createTeam.mutateAsync({ name, slug })
      toast.success("Team created")
      setOpen(false)
      setName("")
      setSlug("")
      setSlugTouched(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to create team")
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Teams"
        description="Create the high-level organizational structure your departments and skills live under."
        action={
          isEditor ? (
            <Button onClick={() => setOpen(true)}>
              <PlusIcon />
              New team
            </Button>
          ) : null
        }
      />

      {teamsQuery.isError ? (
        <ErrorState
          message={
            teamsQuery.error instanceof Error ? teamsQuery.error.message : "Unable to load teams"
          }
          onRetry={() => void teamsQuery.refetch()}
        />
      ) : teamsQuery.isLoading || !teamsQuery.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={index} className="h-full">
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-2">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-3 w-24" />
                  </div>
                  <Skeleton className="h-6 w-24 rounded-full" />
                </div>
              </CardHeader>
              <CardContent>
                <Skeleton className="h-3 w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : teamsQuery.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {teamsQuery.data.map((team) => (
            <Link key={team.id} to={buildWorkspacePath(workspace, `/teams/${team.slug}`)}>
              <Card className="h-full transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle>{team.name}</CardTitle>
                      <CardDescription>Created {formatDateOnly(team.created_at)}</CardDescription>
                    </div>
                    <Badge variant="secondary">{team.department_count} departments</Badge>
                  </div>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  Organize skill ownership, reporting lines, and review accountability.
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No teams yet"
          description="Create your first team to organize departments and skills in a way that matches the business."
          action={
            isEditor ? (
              <Button onClick={() => setOpen(true)}>Create your first team</Button>
            ) : undefined
          }
        />
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create team</DialogTitle>
            <DialogDescription>
              Create a workspace-level team grouping for departments and skill ownership.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="team-name">Name</Label>
              <Input
                id="team-name"
                placeholder="Engineering"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="team-slug">Slug</Label>
              <Input
                id="team-slug"
                placeholder="engineering"
                value={slug}
                onChange={(event) => {
                  setSlugTouched(true)
                  setSlug(slugify(event.target.value))
                }}
              />
              <p className="text-xs text-muted-foreground">
                Short ID used in URLs and in the API. Lowercase letters, numbers, hyphens.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!name.trim() || !slug.trim() || createTeam.isPending}
              onClick={() => void handleCreateTeam()}
            >
              {createTeam.isPending ? "Creating..." : "Create team"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
