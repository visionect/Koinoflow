import * as React from "react"

import { ArrowLeftIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useCreateDepartment,
  useDeleteTeam,
  useTeam,
  useUpdateTeam,
  useWorkspaceMembers,
} from "@/api/client"
import { useAuth } from "@/hooks/useAuth"
import { buildWorkspacePath, formatDateOnly, getDisplayName, slugify } from "@/lib/format"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"

export function TeamDetailPage() {
  const navigate = useNavigate()
  const { workspace, teamSlug } = useParams<{ workspace: string; teamSlug: string }>()
  const { isAdmin, isEditor } = useAuth()

  const teamQuery = useTeam(teamSlug ?? "")
  const membersQuery = useWorkspaceMembers()
  const createDepartment = useCreateDepartment()
  const updateTeam = useUpdateTeam(teamSlug ?? "")
  const deleteTeam = useDeleteTeam()

  const [createOpen, setCreateOpen] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)
  const [deleteOpen, setDeleteOpen] = React.useState(false)

  const [teamName, setTeamName] = React.useState("")
  const [departmentName, setDepartmentName] = React.useState("")
  const [departmentSlug, setDepartmentSlug] = React.useState("")
  const [departmentSlugTouched, setDepartmentSlugTouched] = React.useState(false)
  const [ownerId, setOwnerId] = React.useState<string>("unassigned")

  React.useEffect(() => {
    if (teamQuery.data) {
      setTeamName(teamQuery.data.name)
    }
  }, [teamQuery.data])

  React.useEffect(() => {
    if (!departmentSlugTouched) {
      setDepartmentSlug(slugify(departmentName))
    }
  }, [departmentName, departmentSlugTouched])

  async function handleUpdateTeam() {
    try {
      await updateTeam.mutateAsync({ name: teamName })
      toast.success("Team updated")
      setEditOpen(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update team")
    }
  }

  async function handleCreateDepartment() {
    if (!teamQuery.data) {
      return
    }

    try {
      await createDepartment.mutateAsync({
        team_slug: teamQuery.data.slug,
        name: departmentName,
        slug: departmentSlug,
        owner_id: ownerId === "unassigned" ? null : ownerId,
      })
      toast.success("Department created")
      setCreateOpen(false)
      setDepartmentName("")
      setDepartmentSlug("")
      setDepartmentSlugTouched(false)
      setOwnerId("unassigned")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to create department")
    }
  }

  async function handleDeleteTeam() {
    if (!teamQuery.data) {
      return
    }

    try {
      await deleteTeam.mutateAsync(teamQuery.data.slug)
      toast.success("Team deleted")
      navigate(buildWorkspacePath(workspace, "/teams"), { replace: true })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to delete team")
    }
  }

  if (teamQuery.isError) {
    return (
      <ErrorState
        message={teamQuery.error instanceof Error ? teamQuery.error.message : "Unable to load team"}
        onRetry={() => void teamQuery.refetch()}
      />
    )
  }

  if (!teamQuery.data) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-8 w-24" />
        <div className="space-y-3">
          <Skeleton className="h-9 w-64" />
          <Skeleton className="h-4 w-96" />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={index}>
              <CardHeader>
                <Skeleton className="h-5 w-40" />
                <Skeleton className="mt-2 h-3 w-32" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-3 w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="ghost">
          <Link to={buildWorkspacePath(workspace, "/teams")}>
            <ArrowLeftIcon />
            Teams
          </Link>
        </Button>
      </div>

      <PageHeader
        title={teamQuery.data.name}
        description={`Created ${formatDateOnly(teamQuery.data.created_at)} • ${teamQuery.data.departments.length} departments`}
        action={
          <div className="flex flex-wrap gap-2">
            {isEditor ? (
              <Button onClick={() => setCreateOpen(true)}>
                <PlusIcon />
                New department
              </Button>
            ) : null}
            {isAdmin ? (
              <>
                <Button variant="outline" onClick={() => setEditOpen(true)}>
                  <PencilIcon />
                  Edit
                </Button>
                <Button variant="outline" onClick={() => setDeleteOpen(true)}>
                  <Trash2Icon />
                  Delete
                </Button>
              </>
            ) : null}
          </div>
        }
      />

      {teamQuery.data.departments.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {teamQuery.data.departments.map((department) => (
            <Link key={department.id} to={buildWorkspacePath(workspace, `/depts/${department.id}`)}>
              <Card className="h-full transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <CardTitle>{department.name}</CardTitle>
                      <CardDescription>Owner: {getDisplayName(department.owner)}</CardDescription>
                    </div>
                    <Badge variant="secondary">{department.skill_count} skills</Badge>
                  </div>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  Department slug:{" "}
                  <span className="font-medium text-foreground">{department.slug}</span>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No departments in this team"
          description="Add a department to start organizing ownership and create skill spaces."
          action={
            isEditor ? (
              <Button onClick={() => setCreateOpen(true)}>Add department</Button>
            ) : undefined
          }
        />
      )}

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit team</DialogTitle>
            <DialogDescription>Update the team name shown across the workspace.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="team-edit-name">Team name</Label>
            <Input
              id="team-edit-name"
              value={teamName}
              onChange={(event) => setTeamName(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!teamName.trim() || updateTeam.isPending}
              onClick={() => void handleUpdateTeam()}
            >
              {updateTeam.isPending ? "Saving..." : "Save changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create department</DialogTitle>
            <DialogDescription>
              Departments define skill ownership and keep operational documentation tidy.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="department-name">Name</Label>
              <Input
                id="department-name"
                placeholder="Platform"
                value={departmentName}
                onChange={(event) => setDepartmentName(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="department-slug">Slug</Label>
              <Input
                id="department-slug"
                placeholder="platform"
                value={departmentSlug}
                onChange={(event) => {
                  setDepartmentSlugTouched(true)
                  setDepartmentSlug(slugify(event.target.value))
                }}
              />
              <p className="text-xs text-muted-foreground">
                Used in URLs and API scope. Lowercase letters, numbers, hyphens.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Owner</Label>
              <Select value={ownerId} onValueChange={setOwnerId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select an owner" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unassigned">Unassigned</SelectItem>
                  {membersQuery.data?.map((member) => (
                    <SelectItem key={member.id} value={member.id}>
                      {getDisplayName(member)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={
                !departmentName.trim() || !departmentSlug.trim() || createDepartment.isPending
              }
              onClick={() => void handleCreateDepartment()}
            >
              {createDepartment.isPending ? "Creating..." : "Create department"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DeleteConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        entityName={teamQuery.data.name}
        description="This permanently removes the team, every department inside it, and every skill attached to those departments."
        pending={deleteTeam.isPending}
        onConfirm={handleDeleteTeam}
      />
    </div>
  )
}
