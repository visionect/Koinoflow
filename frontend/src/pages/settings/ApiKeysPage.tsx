import * as React from "react"

import { CopyIcon, PlusIcon } from "lucide-react"
import { toast } from "sonner"

import {
  useApiKeyRoles,
  useApiKeys,
  useCreateApiKey,
  useDepartments,
  useEffectiveSettings,
  useRevokeApiKey,
  useTeams,
} from "@/api/client"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { useAuth } from "@/hooks/useAuth"
import { formatDateOnly } from "@/lib/format"
import type { ApiKeyRole, ApiKeyRoleOption, CreatedApiKey } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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

function roleBadgeVariant(role: ApiKeyRole): "default" | "secondary" | "outline" {
  if (role === "admin") return "default"
  if (role === "team_manager") return "secondary"
  return "outline"
}

const EXPIRY_OPTIONS = [
  { value: "never", label: "Never" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "365", label: "1 year" },
  { value: "custom", label: "Custom date" },
]

function buildExpiryValue(option: string, customDate: string) {
  if (option === "never") {
    return null
  }

  if (option === "custom") {
    return customDate ? new Date(`${customDate}T00:00:00`).toISOString() : null
  }

  const days = Number(option)
  if (Number.isNaN(days)) {
    return null
  }

  return new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString()
}

export function ApiKeysPage() {
  const { isAdmin } = useAuth()
  const settingsQuery = useEffectiveSettings()
  const apiAccessEnabled = settingsQuery.data?.enable_api_access !== false
  const apiKeysQuery = useApiKeys()
  const createApiKey = useCreateApiKey()
  const revokeApiKey = useRevokeApiKey()

  const rolesQuery = useApiKeyRoles()
  const teamsQuery = useTeams()
  const departmentsQuery = useDepartments()

  const [createOpen, setCreateOpen] = React.useState(false)
  const [step, setStep] = React.useState<"form" | "result">("form")
  const [label, setLabel] = React.useState("")
  const [expiryOption, setExpiryOption] = React.useState("never")
  const [customDate, setCustomDate] = React.useState("")
  const [role, setRole] = React.useState<ApiKeyRole>("admin")
  const [teamId, setTeamId] = React.useState<string>("")
  const [departmentIds, setDepartmentIds] = React.useState<string[]>([])
  const [createdKey, setCreatedKey] = React.useState<CreatedApiKey | null>(null)
  const [revokeTarget, setRevokeTarget] = React.useState<{ id: string; label: string } | null>(null)

  const selectedRole: ApiKeyRoleOption | undefined = rolesQuery.data?.find((r) => r.value === role)

  const departmentNamesById = React.useMemo(() => {
    const map = new Map<string, string>()
    for (const dept of departmentsQuery.data ?? []) {
      map.set(dept.id, dept.name)
    }
    return map
  }, [departmentsQuery.data])

  function renderKeyDepartments(ids: string[]) {
    const names = ids.map((id) => departmentNamesById.get(id) ?? id)
    if (names.length === 0) return null
    if (names.length <= 2) return names.join(", ")
    return `${names.slice(0, 2).join(", ")} +${names.length - 2} more`
  }

  if (!isAdmin) {
    return (
      <ErrorState
        title="Permission required"
        message="Only workspace administrators can create, reveal, or revoke API keys."
      />
    )
  }

  async function handleCreateKey() {
    try {
      const result = await createApiKey.mutateAsync({
        label,
        expires_at: buildExpiryValue(expiryOption, customDate),
        role,
        team_id: selectedRole?.requires_team ? teamId || null : null,
        department_ids: selectedRole?.requires_departments ? departmentIds : [],
      })
      setCreatedKey(result)
      setStep("result")
      toast.success("API key created")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to create API key")
    }
  }

  async function handleRevokeKey() {
    if (!revokeTarget) {
      return
    }

    try {
      await revokeApiKey.mutateAsync(revokeTarget.id)
      toast.success("API key revoked")
      setRevokeTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to revoke API key")
    }
  }

  async function handleCopy(value: string) {
    try {
      await navigator.clipboard.writeText(value)
      toast.success("Copied to clipboard")
    } catch {
      toast.error("Clipboard access was blocked")
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="API keys"
        description="Provision workspace-scoped credentials for REST API integrations and automation."
        action={
          <Button onClick={() => setCreateOpen(true)} disabled={!apiAccessEnabled}>
            <PlusIcon />
            Create key
          </Button>
        }
      />

      {!apiAccessEnabled && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          <span className="font-medium">API access is disabled.</span> All keys are temporarily
          suspended and cannot authenticate. Expiry timers continue to run. Enable API access in{" "}
          <a href="../settings" className="underline underline-offset-2">
            Workspace settings
          </a>{" "}
          to restore access.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Credential policy</CardTitle>
          <CardDescription>
            Keys are shown once and should be stored in a secure secret manager immediately.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            Revoke keys as soon as a client is retired, and prefer short-lived credentials for
            non-production environments.
          </p>
          <div>
            <p className="font-medium text-foreground">Rotating a key</p>
            <ol className="ml-5 list-decimal space-y-0.5">
              <li>
                Create a new key with the same scope and a clear label (e.g. <em>prod-mcp-v2</em>).
              </li>
              <li>Deploy the new key to your client and verify calls succeed.</li>
              <li>
                Revoke the old key here; any client still using it will immediately lose access.
              </li>
            </ol>
          </div>
        </CardContent>
      </Card>

      {apiKeysQuery.isError ? (
        <ErrorState
          message={
            apiKeysQuery.error instanceof Error
              ? apiKeysQuery.error.message
              : "Unable to load API keys"
          }
          onRetry={() => void apiKeysQuery.refetch()}
        />
      ) : apiKeysQuery.data?.length ? (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Label</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Expiry</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {apiKeysQuery.data.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.label}</TableCell>
                  <TableCell>{key.key_prefix}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <Badge variant={roleBadgeVariant(key.role)}>
                        {rolesQuery.data?.find((r) => r.value === key.role)?.label ?? key.role}
                      </Badge>
                      {key.team_name ? (
                        <span className="text-xs text-muted-foreground">{key.team_name}</span>
                      ) : null}
                      {key.department_ids.length > 0 ? (
                        <span
                          className="max-w-[280px] truncate text-xs text-muted-foreground"
                          title={key.department_ids
                            .map((id) => departmentNamesById.get(id) ?? id)
                            .join(", ")}
                        >
                          {renderKeyDepartments(key.department_ids)}
                        </span>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell>{formatDateOnly(key.created_at)}</TableCell>
                  <TableCell>{formatDateOnly(key.expires_at, "Never")}</TableCell>
                  <TableCell>
                    {key.is_active && !apiAccessEnabled ? (
                      <Badge variant="outline" className="text-amber-600 border-amber-300">
                        Suspended
                      </Badge>
                    ) : (
                      <Badge
                        variant={key.is_active ? "default" : "secondary"}
                        className={key.is_active ? "bg-emerald-600 text-white" : ""}
                      >
                        {key.is_active ? "Active" : "Revoked"}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {key.is_active && apiAccessEnabled ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setRevokeTarget({ id: key.id, label: key.label })}
                      >
                        Revoke
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState
          title="No API keys yet"
          description="Create a key to connect API consumers to this workspace."
          action={<Button onClick={() => setCreateOpen(true)}>Create first key</Button>}
        />
      )}

      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) {
            setStep("form")
            setCreatedKey(null)
            setLabel("")
            setExpiryOption("never")
            setCustomDate("")
            setRole("admin")
            setTeamId("")
            setDepartmentIds([])
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          {step === "form" ? (
            <>
              <DialogHeader>
                <DialogTitle>Create API key</DialogTitle>
                <DialogDescription>
                  Label the credential clearly so operators understand which client owns it.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="api-key-label">Label</Label>
                  <Input
                    id="api-key-label"
                    placeholder="Production MCP"
                    value={label}
                    onChange={(event) => setLabel(event.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Expiry</Label>
                  <Select value={expiryOption} onValueChange={setExpiryOption}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select an expiry" />
                    </SelectTrigger>
                    <SelectContent>
                      {EXPIRY_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {expiryOption === "custom" ? (
                  <div className="space-y-2">
                    <Label htmlFor="api-key-custom-date">Custom expiry date</Label>
                    <Input
                      id="api-key-custom-date"
                      type="date"
                      value={customDate}
                      onChange={(event) => setCustomDate(event.target.value)}
                    />
                  </div>
                ) : null}

                <div className="space-y-2">
                  <Label>Scope</Label>
                  <Select
                    value={role}
                    onValueChange={(value: ApiKeyRole) => {
                      setRole(value)
                      setTeamId("")
                      setDepartmentIds([])
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {rolesQuery.data?.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          <span>{option.label}</span>
                          <span className="ml-2 text-muted-foreground">— {option.description}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {selectedRole?.requires_team ? (
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

                {selectedRole?.requires_departments ? (
                  <div className="space-y-2">
                    <Label>Departments</Label>
                    <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border p-3">
                      {departmentsQuery.data?.length ? (
                        departmentsQuery.data.map((dept) => (
                          <label
                            key={dept.id}
                            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                          >
                            <Checkbox
                              checked={departmentIds.includes(dept.id)}
                              onCheckedChange={(checked) => {
                                setDepartmentIds((prev) =>
                                  checked
                                    ? [...prev, dept.id]
                                    : prev.filter((id) => id !== dept.id),
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
                        {departmentIds.length} department{departmentIds.length !== 1 ? "s" : ""}{" "}
                        selected
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setCreateOpen(false)}>
                  Cancel
                </Button>
                <Button
                  disabled={
                    !label.trim() ||
                    createApiKey.isPending ||
                    (expiryOption === "custom" && !customDate) ||
                    (selectedRole?.requires_team && !teamId) ||
                    (selectedRole?.requires_departments && departmentIds.length === 0)
                  }
                  onClick={() => void handleCreateKey()}
                >
                  {createApiKey.isPending ? "Creating..." : "Create key"}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>API key created</DialogTitle>
                <DialogDescription>
                  Copy this key now. It will not be shown again after you close this dialog.
                </DialogDescription>
              </DialogHeader>

              <div className="min-w-0 space-y-6">
                <div className="min-w-0 rounded-xl border bg-muted/40 p-4">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <Label className="text-sm font-medium">Raw key</Label>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleCopy(createdKey?.raw_key ?? "")}
                    >
                      <CopyIcon />
                      Copy
                    </Button>
                  </div>
                  <div className="break-all rounded-lg bg-background p-3 font-mono text-sm">
                    {createdKey?.raw_key}
                  </div>
                </div>
              </div>

              <DialogFooter>
                <Button onClick={() => setCreateOpen(false)}>Done</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <DeleteConfirmDialog
        open={Boolean(revokeTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setRevokeTarget(null)
          }
        }}
        entityName={revokeTarget?.label ?? ""}
        title={revokeTarget ? `Revoke "${revokeTarget.label}"?` : "Revoke API key?"}
        description="Any client using this key will immediately lose access."
        confirmLabel="Revoke"
        requireTyping={false}
        pending={revokeApiKey.isPending}
        onConfirm={handleRevokeKey}
      />
    </div>
  )
}
