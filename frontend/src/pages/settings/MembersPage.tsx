import * as React from "react"

import { AlertTriangleIcon, MailPlusIcon, Trash2Icon, XIcon } from "lucide-react"
import { toast } from "sonner"

import {
  useCancelInvitation,
  useDepartments,
  useInviteMember,
  usePendingInvitations,
  useRemoveMember,
  useTeams,
  useWorkspaceMembers,
} from "@/api/client"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { useAuth } from "@/hooks/useAuth"
import { formatRelativeDate, startCase } from "@/lib/format"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

type MemberRole = "admin" | "team_manager" | "member"

function roleBadgeVariant(role: string): "default" | "secondary" | "outline" {
  if (role === "admin") return "default"
  if (role === "team_manager") return "secondary"
  return "outline"
}

const ROLE_OPTIONS: { value: MemberRole; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "team_manager", label: "Team Manager" },
  { value: "member", label: "Member" },
]

export function MembersPage() {
  const { role: myRole, user: currentUser } = useAuth()
  const canManage = myRole === "admin" || myRole === "team_manager"

  const membersQuery = useWorkspaceMembers()
  const invitationsQuery = usePendingInvitations()
  const teamsQuery = useTeams()
  const departmentsQuery = useDepartments()

  const inviteMember = useInviteMember()
  const removeMember = useRemoveMember()
  const cancelInvitation = useCancelInvitation()

  const [inviteOpen, setInviteOpen] = React.useState(false)
  const [email, setEmail] = React.useState("")
  const [role, setRole] = React.useState<MemberRole>("member")
  const [teamId, setTeamId] = React.useState("")
  const [departmentIds, setDepartmentIds] = React.useState<string[]>([])
  const [removeTarget, setRemoveTarget] = React.useState<{
    id: string
    name: string
  } | null>(null)
  const [cancelTarget, setCancelTarget] = React.useState<{
    id: string
    email: string
  } | null>(null)

  const filteredDepartments = React.useMemo(() => {
    if (!departmentsQuery.data) return []
    if (role === "team_manager" && teamId) {
      const selectedTeam = teamsQuery.data?.find((t) => t.id === teamId)
      if (selectedTeam) {
        return departmentsQuery.data.filter((d) => d.team_slug === selectedTeam.slug)
      }
    }
    return departmentsQuery.data
  }, [departmentsQuery.data, teamsQuery.data, role, teamId])

  const requiresTeam = role === "team_manager"
  const showDepartments = role === "member" || role === "team_manager"

  function resetInviteForm() {
    setEmail("")
    setRole("member")
    setTeamId("")
    setDepartmentIds([])
  }

  async function handleInvite() {
    try {
      await inviteMember.mutateAsync({
        email,
        role,
        team_id: requiresTeam ? teamId || null : null,
        department_ids: departmentIds,
      })
      toast.success("Invitation sent")
      setInviteOpen(false)
      resetInviteForm()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to send invitation")
    }
  }

  async function handleRemoveMember() {
    if (!removeTarget) return
    try {
      await removeMember.mutateAsync(removeTarget.id)
      toast.success("Member removed")
      setRemoveTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to remove member")
    }
  }

  async function handleCancelInvitation() {
    if (!cancelTarget) return
    try {
      await cancelInvitation.mutateAsync(cancelTarget.id)
      toast.success("Invitation cancelled")
      setCancelTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to cancel invitation")
    }
  }

  const departmentNamesById = React.useMemo(() => {
    const map = new Map<string, string>()
    for (const dept of departmentsQuery.data ?? []) {
      map.set(dept.id, dept.name)
    }
    return map
  }, [departmentsQuery.data])

  function renderMemberDepartments(ids: string[]) {
    const names = ids.map((id) => departmentNamesById.get(id) ?? id)
    if (names.length === 0) return null
    if (names.length <= 2) return names.join(", ")
    return `${names.slice(0, 2).join(", ")} +${names.length - 2} more`
  }

  const allowedRoles = React.useMemo(() => {
    if (myRole === "team_manager") {
      return ROLE_OPTIONS.filter((r) => r.value === "member")
    }
    return ROLE_OPTIONS
  }, [myRole])

  return (
    <div className="space-y-8">
      <PageHeader
        title="Members"
        description="Manage who has access to this workspace and what they can do."
        action={
          canManage ? (
            <Button onClick={() => setInviteOpen(true)}>
              <MailPlusIcon />
              Invite member
            </Button>
          ) : undefined
        }
      />

      {membersQuery.isError ? (
        <ErrorState
          message={
            membersQuery.error instanceof Error
              ? membersQuery.error.message
              : "Unable to load members"
          }
          onRetry={() => void membersQuery.refetch()}
        />
      ) : membersQuery.data?.length ? (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Team</TableHead>
                <TableHead>Departments</TableHead>
                {canManage ? <TableHead className="text-right">Actions</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {membersQuery.data.map((member) => {
                const displayName =
                  `${member.first_name} ${member.last_name}`.trim() || member.email
                const isSelf = member.id === currentUser?.id

                return (
                  <TableRow key={member.id}>
                    <TableCell className="font-medium">
                      {displayName}
                      {isSelf ? (
                        <span className="ml-1.5 text-xs text-muted-foreground">(you)</span>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{member.email}</TableCell>
                    <TableCell>
                      <Badge variant={roleBadgeVariant(member.role)}>
                        {startCase(member.role)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {member.team_name ?? <span className="text-muted-foreground">--</span>}
                    </TableCell>
                    <TableCell>
                      {member.department_ids.length > 0 ? (
                        <span
                          className="block max-w-[260px] truncate text-sm"
                          title={member.department_ids
                            .map((id) => departmentNamesById.get(id) ?? id)
                            .join(", ")}
                        >
                          {renderMemberDepartments(member.department_ids)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">--</span>
                      )}
                    </TableCell>
                    {canManage ? (
                      <TableCell className="text-right">
                        {!isSelf ? (
                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-8 text-muted-foreground hover:text-destructive"
                            onClick={() =>
                              setRemoveTarget({
                                id: member.id,
                                name: displayName,
                              })
                            }
                          >
                            <Trash2Icon className="size-4" />
                          </Button>
                        ) : null}
                      </TableCell>
                    ) : null}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState
          title="No members"
          description="You are the only member. Invite others to start collaborating."
          action={
            canManage ? (
              <Button onClick={() => setInviteOpen(true)}>Invite first member</Button>
            ) : undefined
          }
        />
      )}

      {canManage && !invitationsQuery.isError ? (
        invitationsQuery.data?.length ? (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold tracking-tight">Pending invitations</h2>
            <div className="overflow-hidden rounded-2xl border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Team</TableHead>
                    <TableHead>Invited by</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invitationsQuery.data.map((inv) => (
                    <TableRow key={inv.id}>
                      <TableCell className="font-medium">{inv.email}</TableCell>
                      <TableCell>
                        <Badge variant={roleBadgeVariant(inv.role)}>{startCase(inv.role)}</Badge>
                      </TableCell>
                      <TableCell>
                        {inv.team_name ?? <span className="text-muted-foreground">--</span>}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {inv.invited_by_email ?? "--"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatRelativeDate(inv.expires_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-8 text-muted-foreground hover:text-destructive"
                          onClick={() =>
                            setCancelTarget({
                              id: inv.id,
                              email: inv.email,
                            })
                          }
                        >
                          <XIcon className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : null
      ) : null}

      <Dialog
        open={inviteOpen}
        onOpenChange={(open) => {
          setInviteOpen(open)
          if (!open) resetInviteForm()
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Invite member</DialogTitle>
            <DialogDescription>
              Send an invitation to join this workspace. The user will receive an email with a link
              to accept.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="invite-email">Email address</Label>
              <Input
                id="invite-email"
                type="email"
                placeholder="colleague@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label>Role</Label>
              <Select
                value={role}
                onValueChange={(value: MemberRole) => {
                  setRole(value)
                  setTeamId("")
                  setDepartmentIds([])
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {allowedRoles.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {requiresTeam ? (
              <div className="space-y-2">
                <Label>Team</Label>
                <Select value={teamId} onValueChange={setTeamId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a team" />
                  </SelectTrigger>
                  <SelectContent>
                    {teamsQuery.data?.map((team) => (
                      <SelectItem key={team.id} value={team.id}>
                        {team.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            {showDepartments ? (
              <div className="space-y-2">
                <Label>
                  Departments
                  {role === "member" ? (
                    <span className="ml-1 font-normal text-muted-foreground">(scope access)</span>
                  ) : null}
                </Label>
                <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border p-3">
                  {filteredDepartments.length > 0 ? (
                    filteredDepartments.map((dept) => (
                      <label
                        key={dept.id}
                        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                      >
                        <Checkbox
                          checked={departmentIds.includes(dept.id)}
                          onCheckedChange={(checked) => {
                            setDepartmentIds((prev) =>
                              checked ? [...prev, dept.id] : prev.filter((id) => id !== dept.id),
                            )
                          }}
                        />
                        <span>{dept.name}</span>
                        <span className="text-muted-foreground">({dept.team_name})</span>
                      </label>
                    ))
                  ) : (
                    <p className="text-sm text-muted-foreground">No departments found</p>
                  )}
                </div>
                {departmentIds.length > 0 ? (
                  <p className="text-xs text-muted-foreground">
                    {departmentIds.length} department
                    {departmentIds.length !== 1 ? "s" : ""} selected
                  </p>
                ) : role === "member" ? (
                  <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-900 dark:text-amber-200">
                    <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                    <p>
                      Members without a department only see workspace-wide processes. Most invitees
                      should be scoped to at least one department.
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInviteOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!email.trim() || inviteMember.isPending || (requiresTeam && !teamId)}
              onClick={() => void handleInvite()}
            >
              {inviteMember.isPending ? "Sending..." : "Send invitation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DeleteConfirmDialog
        open={Boolean(removeTarget)}
        onOpenChange={(open) => {
          if (!open) setRemoveTarget(null)
        }}
        entityName={removeTarget?.name ?? ""}
        title={removeTarget ? `Remove "${removeTarget.name}"?` : "Remove member?"}
        description="This will revoke their access to the workspace immediately."
        confirmLabel="Remove"
        requireTyping={false}
        pending={removeMember.isPending}
        onConfirm={handleRemoveMember}
      />

      <DeleteConfirmDialog
        open={Boolean(cancelTarget)}
        onOpenChange={(open) => {
          if (!open) setCancelTarget(null)
        }}
        entityName={cancelTarget?.email ?? ""}
        title={
          cancelTarget ? `Cancel invitation for "${cancelTarget.email}"?` : "Cancel invitation?"
        }
        description="The invitation link will no longer work."
        confirmLabel="Cancel invitation"
        requireTyping={false}
        pending={cancelInvitation.isPending}
        onConfirm={handleCancelInvitation}
      />
    </div>
  )
}
