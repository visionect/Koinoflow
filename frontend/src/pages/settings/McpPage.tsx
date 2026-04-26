import * as React from "react"

import { CopyIcon, ExternalLinkIcon, PencilIcon } from "lucide-react"
import { toast } from "sonner"

import {
  useDepartments,
  useMcpConnections,
  useRevokeMcpConnection,
  useTeams,
  useUpdateMcpConnectionScope,
} from "@/api/client"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { useAuth } from "@/hooks/useAuth"
import { formatDateOnly, formatRelativeDate } from "@/lib/format"
import type { McpConnection, McpScopeType } from "@/types"
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
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const MCP_SERVER_URL = import.meta.env.VITE_MCP_SERVER_URL ?? "http://localhost:8001"
const MCP_DOCS_URL = "https://modelcontextprotocol.io/docs/clients"

const SCOPE_LABELS: Record<string, { label: string; description: string }> = {
  "skills:read": {
    label: "Read skills",
    description: "Discover and fetch approved skills in the workspace.",
  },
  "skills:write": {
    label: "Edit skills",
    description: "Create new skills and push new versions.",
  },
  "usage:write": {
    label: "Log usage",
    description: "Record which skills this client invoked (for analytics).",
  },
}

type ClientId = "cursor" | "claude" | "claude-code" | "windsurf" | "generic"

type ClientTab = {
  id: ClientId
  label: string
  snippet: (url: string) => string
  language: "json" | "shell"
}

const CLIENT_TABS: ClientTab[] = [
  {
    id: "cursor",
    label: "Cursor",
    snippet: (url) => JSON.stringify({ mcpServers: { koinoflow: { url: `${url}/mcp` } } }, null, 2),
    language: "json",
  },
  {
    id: "claude",
    label: "Claude Desktop",
    snippet: (url) =>
      JSON.stringify(
        {
          mcpServers: {
            koinoflow: {
              command: "npx",
              args: ["-y", "@koinoflow/mcp", "--url", `${url}/mcp`],
            },
          },
        },
        null,
        2,
      ),
    language: "json",
  },
  {
    id: "claude-code",
    label: "Claude Code",
    snippet: (url) => `claude mcp add --transport http koinoflow ${url}/mcp`,
    language: "shell",
  },
  {
    id: "windsurf",
    label: "Windsurf",
    snippet: (url) =>
      JSON.stringify({ mcpServers: { koinoflow: { serverUrl: `${url}/mcp` } } }, null, 2),
    language: "json",
  },
  {
    id: "generic",
    label: "Other",
    snippet: (url) => JSON.stringify({ mcpServers: { koinoflow: { url: `${url}/mcp` } } }, null, 2),
    language: "json",
  },
]

function buildTeammateInstructions(
  workspaceName: string | undefined,
  snippet: string,
  language: "json" | "shell",
) {
  const name = workspaceName ?? "our workspace"
  const fence = language === "shell" ? "bash" : "json"
  const heading =
    language === "shell"
      ? "## 1. Run this command in your MCP client"
      : "## 1. Add this config to your MCP client"
  return `# Connecting to Koinoflow MCP

Koinoflow exposes ${name}'s skills as an MCP server so your AI client (Cursor, Claude Desktop, Claude Code, Windsurf, etc.) can read and search them.

${heading}

\`\`\`${fence}
${snippet}
\`\`\`

## 2. Sign in when prompted

On first use the client will open a browser window. Sign in with your usual Koinoflow account — your access mirrors your workspace permissions.

## 3. Docs

MCP client setup guides: ${MCP_DOCS_URL}
`
}

function ScopeBadge({ connection }: { connection: McpConnection }) {
  const scope = connection.connection_scope
  if (!scope || scope.scope_type === "workspace") {
    return (
      <Badge variant="outline" className="text-xs">
        All skills
      </Badge>
    )
  }
  if (scope.scope_type === "team") {
    return (
      <Badge variant="outline" className="text-xs">
        Team: {scope.team_name}
      </Badge>
    )
  }
  if (scope.departments.length === 1) {
    const dept = scope.departments[0]
    if (!dept) return null
    return (
      <Badge variant="outline" className="text-xs">
        Dept: {dept.name}
      </Badge>
    )
  }
  const names = scope.departments.map((d) => d.name).join(", ")
  return (
    <Badge variant="outline" className="max-w-[220px] truncate text-xs" title={names}>
      {scope.departments.length} departments: {names}
    </Badge>
  )
}

function ScopeTokenBadge({ token }: { token: string }) {
  const info = SCOPE_LABELS[token]
  return (
    <Badge
      variant="outline"
      className="text-xs"
      title={info ? `${token} — ${info.description}` : token}
    >
      {info?.label ?? token}
    </Badge>
  )
}

function ScopeEditorDialog({
  connection,
  open,
  onOpenChange,
}: {
  connection: McpConnection
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const teamsQuery = useTeams()
  const departmentsQuery = useDepartments()
  const updateScope = useUpdateMcpConnectionScope()

  const currentScope = connection.connection_scope

  const [scopeType, setScopeType] = React.useState<McpScopeType>(
    currentScope?.scope_type ?? "workspace",
  )
  const [teamId, setTeamId] = React.useState<string>(currentScope?.team_id ?? "")
  const [departmentIds, setDepartmentIds] = React.useState<string[]>(
    currentScope?.department_ids ?? [],
  )

  React.useEffect(() => {
    if (open) {
      setScopeType(currentScope?.scope_type ?? "workspace")
      setTeamId(currentScope?.team_id ?? "")
      setDepartmentIds(currentScope?.department_ids ?? [])
    }
  }, [open, currentScope])

  const teams = teamsQuery.data ?? []
  const allDepartments = React.useMemo(() => departmentsQuery.data ?? [], [departmentsQuery.data])

  function toggleDepartment(id: string) {
    setDepartmentIds((prev) => (prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id]))
  }

  async function handleSave() {
    try {
      await updateScope.mutateAsync({
        id: connection.id,
        scope_type: scopeType,
        team_id: scopeType === "team" ? teamId : null,
        department_ids: scopeType === "department" ? departmentIds : [],
      })
      toast.success("Skill scope updated")
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update scope")
    }
  }

  const isSaveDisabled =
    (scopeType === "team" && !teamId) ||
    (scopeType === "department" && departmentIds.length === 0) ||
    updateScope.isPending

  const departmentsByTeam = React.useMemo(() => {
    const grouped = new Map<string, { teamName: string; departments: typeof allDepartments }>()
    for (const dept of allDepartments) {
      const existing = grouped.get(dept.team_slug)
      if (existing) {
        existing.departments.push(dept)
      } else {
        grouped.set(dept.team_slug, {
          teamName: dept.team_name,
          departments: [dept],
        })
      }
    }
    return grouped
  }, [allDepartments])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Skill scope — {connection.client_name}</DialogTitle>
          <DialogDescription>
            Choose which skills this MCP connection can access. This narrows visibility below
            your role-level permissions.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <RadioGroup value={scopeType} onValueChange={(v) => setScopeType(v as McpScopeType)}>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="workspace" id="scope-workspace" />
              <Label htmlFor="scope-workspace" className="font-normal">
                All skills (workspace-wide)
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="team" id="scope-team" />
              <Label htmlFor="scope-team" className="font-normal">
                Specific team
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="department" id="scope-department" />
              <Label htmlFor="scope-department" className="font-normal">
                Specific department(s)
              </Label>
            </div>
          </RadioGroup>

          {scopeType === "team" && (
            <Select value={teamId} onValueChange={setTeamId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a team" />
              </SelectTrigger>
              <SelectContent>
                {teams.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {scopeType === "department" && (
            <div className="max-h-56 space-y-3 overflow-y-auto rounded-lg border p-3">
              {[...departmentsByTeam.entries()].map(([slug, group]) => (
                <div key={slug}>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">{group.teamName}</p>
                  <div className="space-y-1.5">
                    {group.departments.map((dept) => (
                      <label key={dept.id} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={departmentIds.includes(dept.id)}
                          onCheckedChange={() => toggleDepartment(dept.id)}
                        />
                        {dept.name}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              {allDepartments.length === 0 && (
                <p className="text-sm text-muted-foreground">No departments found.</p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaveDisabled}>
            {updateScope.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function McpPage() {
  const { isAdmin, workspaceSlug } = useAuth()
  const connectionsQuery = useMcpConnections()
  const revokeConnection = useRevokeMcpConnection()

  const [revokeTarget, setRevokeTarget] = React.useState<{
    id: string
    name: string
  } | null>(null)

  const [scopeTarget, setScopeTarget] = React.useState<McpConnection | null>(null)
  const [activeClient, setActiveClient] = React.useState<ClientId>("cursor")

  const activeTab = CLIENT_TABS.find((tab) => tab.id === activeClient) ?? CLIENT_TABS[0]!
  const snippet = activeTab.snippet(MCP_SERVER_URL)
  const teammateInstructions = React.useMemo(
    () => buildTeammateInstructions(workspaceSlug ?? undefined, snippet, activeTab.language),
    [workspaceSlug, snippet, activeTab.language],
  )

  if (!isAdmin) {
    return (
      <ErrorState
        title="Permission required"
        message="Only workspace administrators can manage MCP connections."
      />
    )
  }

  async function handleCopy(value: string) {
    try {
      await navigator.clipboard.writeText(value)
      toast.success("Copied to clipboard")
    } catch {
      toast.error("Clipboard access was blocked")
    }
  }

  async function handleRevoke() {
    if (!revokeTarget) return

    try {
      await revokeConnection.mutateAsync(revokeTarget.id)
      toast.success("MCP connection revoked")
      setRevokeTarget(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to revoke connection")
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="MCP"
        description="Connect AI clients to your workspace skills via the Model Context Protocol."
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Client configuration</CardTitle>
              <CardDescription>
                Choose your AI client and copy the snippet. Everyone signs in with their usual
                Koinoflow account on first use — access mirrors their workspace permissions.
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" asChild>
              <a href={MCP_DOCS_URL} target="_blank" rel="noreferrer">
                MCP client docs
                <ExternalLinkIcon aria-hidden />
              </a>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Tabs value={activeClient} onValueChange={(v) => setActiveClient(v as ClientId)}>
            <TabsList>
              {CLIENT_TABS.map((tab) => (
                <TabsTrigger key={tab.id} value={tab.id}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
            {CLIENT_TABS.map((tab) => {
              const tabSnippet = tab.snippet(MCP_SERVER_URL)
              const isShell = tab.language === "shell"
              return (
                <TabsContent key={tab.id} value={tab.id} className="mt-4">
                  <div className="min-w-0 rounded-xl border bg-muted/40 p-4">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <Label className="text-sm font-medium">
                        {tab.label} {isShell ? "command" : "config"}
                      </Label>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleCopy(tabSnippet)}
                      >
                        <CopyIcon aria-hidden />
                        {isShell ? "Copy command" : "Copy JSON"}
                      </Button>
                    </div>
                    <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg bg-background p-3 text-sm">
                      {tabSnippet}
                    </pre>
                  </div>
                </TabsContent>
              )
            })}
          </Tabs>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-background p-3">
            <div className="min-w-0">
              <p className="text-sm font-medium">Share with teammates</p>
              <p className="text-xs text-muted-foreground">
                Copies a ready-to-paste Markdown doc with the {activeTab.label} snippet and sign-in
                steps.
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void handleCopy(teammateInstructions)}
            >
              <CopyIcon aria-hidden />
              Copy teammate instructions
            </Button>
          </div>
        </CardContent>
      </Card>

      {connectionsQuery.isError ? (
        <ErrorState
          message={
            connectionsQuery.error instanceof Error
              ? connectionsQuery.error.message
              : "Unable to load MCP connections"
          }
          onRetry={() => void connectionsQuery.refetch()}
        />
      ) : connectionsQuery.data?.length ? (
        <>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">Connected clients</h2>
            <p className="text-sm text-muted-foreground">
              Users who have completed OAuth and connected an MCP client.
            </p>
          </div>
          <div className="overflow-hidden rounded-2xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Client</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Scopes</TableHead>
                  <TableHead>Skill scope</TableHead>
                  <TableHead>Connected</TableHead>
                  <TableHead>Last active</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connectionsQuery.data.map((conn) => (
                  <TableRow key={conn.id}>
                    <TableCell className="font-medium">{conn.client_name}</TableCell>
                    <TableCell>{conn.user?.email ?? "—"}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {conn.scopes
                          ? conn.scopes
                              .split(" ")
                              .map((scope) => <ScopeTokenBadge key={scope} token={scope} />)
                          : "—"}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <ScopeBadge connection={conn} />
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-xs"
                          onClick={() => setScopeTarget(conn)}
                        >
                          <PencilIcon aria-hidden />
                          Edit
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell>{formatDateOnly(conn.created_at)}</TableCell>
                    <TableCell>{formatRelativeDate(conn.last_used_at)}</TableCell>
                    <TableCell>
                      <Badge
                        variant={conn.is_active ? "default" : "secondary"}
                        className={conn.is_active ? "bg-emerald-600 text-white" : ""}
                      >
                        {conn.is_active ? "Active" : "Expired"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setRevokeTarget({ id: conn.id, name: conn.client_name })}
                      >
                        Revoke
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      ) : (
        <EmptyState
          title="No MCP clients connected"
          description="Share the config snippet above with your team. Connections appear here once a user completes the OAuth sign-in from their MCP client."
        />
      )}

      {scopeTarget && (
        <ScopeEditorDialog
          connection={scopeTarget}
          open={Boolean(scopeTarget)}
          onOpenChange={(open) => {
            if (!open) setScopeTarget(null)
          }}
        />
      )}

      <DeleteConfirmDialog
        open={Boolean(revokeTarget)}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null)
        }}
        entityName={revokeTarget?.name ?? ""}
        title={revokeTarget ? `Revoke "${revokeTarget.name}"?` : "Revoke connection?"}
        description="This will invalidate all tokens for this MCP client. The user will need to re-authorize to reconnect."
        confirmLabel="Revoke"
        requireTyping={false}
        pending={revokeConnection.isPending}
        onConfirm={handleRevoke}
      />
    </div>
  )
}
