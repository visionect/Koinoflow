import * as React from "react"

import {
  CopyIcon,
  HistoryIcon,
  KeyRoundIcon,
  PencilIcon,
  PlusIcon,
  RotateCwIcon,
  UploadIcon,
} from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useAgentAnalytics,
  useAgentSkills,
  useAgentUsage,
  useAgents,
  useCreateAgent,
  useImportAgentSkill,
  useRotateAgentToken,
  useUpdateAgent,
} from "@/api/client"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { useAuth } from "@/hooks/useAuth"
import { type SkillImportData, useSkillImport } from "@/hooks/use-skill-import"
import { buildWorkspacePath, formatRelativeDate } from "@/lib/format"
import type { Agent, CreatedAgent } from "@/types"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100)
}

function TokenReveal({ agent }: { agent: CreatedAgent | null }) {
  if (!agent) return null

  const token = agent.token

  async function copyToken() {
    try {
      await navigator.clipboard.writeText(token)
      toast.success("Agent token copied")
    } catch {
      toast.error("Clipboard access was blocked")
    }
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
      <p className="font-medium">Save this token now. It will not be shown again.</p>
      <div className="mt-2 flex items-center gap-2 rounded-md bg-background p-2 font-mono text-xs text-foreground">
        <code className="min-w-0 flex-1 break-all">{token}</code>
        <Button size="sm" variant="outline" onClick={() => void copyToken()}>
          <CopyIcon aria-hidden />
          Copy
        </Button>
      </div>
    </div>
  )
}

function CreateAgentDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (agent: CreatedAgent) => void
}) {
  const createAgent = useCreateAgent()
  const [name, setName] = React.useState("")
  const [description, setDescription] = React.useState("")

  async function handleSubmit() {
    try {
      const agent = await createAgent.mutateAsync({ name, description })
      onCreated(agent)
      setName("")
      setDescription("")
      onOpenChange(false)
      toast.success("Agent created")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to create agent")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create agent</DialogTitle>
          <DialogDescription>
            Generate a one-time token for an AI agent to connect without a human OAuth login.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="agent-name">Name</Label>
            <Input id="agent-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="agent-description">Description</Label>
            <Textarea
              id="agent-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Where this agent runs and what it is allowed to do"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={!name.trim() || createAgent.isPending}>
            Create agent
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ImportAgentSkillDialog({
  open,
  onOpenChange,
  importData,
  agents,
  onConsumed,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  importData: SkillImportData | null
  agents: Agent[]
  onConsumed: () => void
}) {
  const importAgentSkill = useImportAgentSkill()
  const [deployToAll, setDeployToAll] = React.useState(true)
  const [selectedAgentIds, setSelectedAgentIds] = React.useState<Set<string>>(new Set())
  const [title, setTitle] = React.useState("")
  const [slug, setSlug] = React.useState("")

  React.useEffect(() => {
    if (open && importData) {
      setTitle(importData.title)
      setSlug(slugify(importData.title))
      setDeployToAll(true)
      setSelectedAgentIds(new Set())
    }
  }, [importData, open])

  async function handleImport() {
    if (!importData) return
    try {
      await importAgentSkill.mutateAsync({
        title,
        slug,
        description: importData.description,
        content_md: importData.contentMd,
        frontmatter_yaml: importData.frontmatterYaml,
        files: importData.supportFiles,
        deploy_to_all: deployToAll,
        agent_ids: deployToAll ? [] : [...selectedAgentIds],
      })
      toast.success("Agent skill imported")
      onConsumed()
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to import agent skill")
    }
  }

  function toggleAgent(id: string, checked: boolean) {
    setSelectedAgentIds((current) => {
      const next = new Set(current)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const disabled =
    !importData ||
    !title.trim() ||
    !slug.trim() ||
    (!deployToAll && selectedAgentIds.size === 0) ||
    importAgentSkill.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import agent skill</DialogTitle>
          <DialogDescription>
            Agent skills live in hidden backend storage and are deployed only to selected agents.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="agent-skill-title">Title</Label>
              <Input id="agent-skill-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="agent-skill-slug">Slug</Label>
              <Input id="agent-skill-slug" value={slug} onChange={(e) => setSlug(slugify(e.target.value))} />
            </div>
          </div>

          <div className="rounded-lg border p-3">
            <div className="flex items-start gap-3">
              <Checkbox
                id="deploy-all"
                checked={deployToAll}
                onCheckedChange={(checked) => setDeployToAll(Boolean(checked))}
              />
              <div>
                <Label htmlFor="deploy-all">Deploy to all agents</Label>
                <p className="text-sm text-muted-foreground">
                  New and existing agents will be able to retrieve this skill.
                </p>
              </div>
            </div>
          </div>

          {!deployToAll && (
            <div className="space-y-2">
              <Label>Select agents</Label>
              <div className="max-h-56 space-y-2 overflow-y-auto rounded-lg border p-3">
                {agents.map((agent) => (
                  <label key={agent.id} className="flex items-start gap-3 rounded-md p-2 hover:bg-muted/50">
                    <Checkbox
                      checked={selectedAgentIds.has(agent.id)}
                      onCheckedChange={(checked) => toggleAgent(agent.id, Boolean(checked))}
                    />
                    <span>
                      <span className="block text-sm font-medium">{agent.name}</span>
                      <span className="block text-xs text-muted-foreground">{agent.masked_token}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void handleImport()} disabled={disabled}>
            Import skill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function AgentsPage() {
  const { isAdmin } = useAuth()
  const { workspace } = useParams<{ workspace: string }>()
  const agentsQuery = useAgents()
  const skillsQuery = useAgentSkills()
  const analyticsQuery = useAgentAnalytics(30)
  const usageQuery = useAgentUsage(30)
  const updateAgent = useUpdateAgent()
  const rotateToken = useRotateAgentToken()

  const [createOpen, setCreateOpen] = React.useState(false)
  const [createdAgent, setCreatedAgent] = React.useState<CreatedAgent | null>(null)
  const [importOpen, setImportOpen] = React.useState(false)
  const [importData, setImportData] = React.useState<SkillImportData | null>(null)

  const { fileInput, openFilePicker } = useSkillImport((data) => {
    setImportData(data)
    setImportOpen(true)
  })

  if (!isAdmin) {
    return (
      <ErrorState
        title="Permission required"
        message="Only workspace administrators can manage AI agents and their tokens."
      />
    )
  }

  async function handleRotate(agent: Agent) {
    try {
      const rotated = await rotateToken.mutateAsync(agent.id)
      setCreatedAgent(rotated)
      toast.success("Agent token rotated")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to rotate token")
    }
  }

  async function toggleAgent(agent: Agent) {
    try {
      await updateAgent.mutateAsync({ id: agent.id, is_active: !agent.is_active })
      toast.success(agent.is_active ? "Agent deactivated" : "Agent activated")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update agent")
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Agents"
        description="Manage AI agents, their one-time connection tokens, agent-specific skills, and usage."
        action={
          <div className="flex gap-2">
            <Button variant="outline" onClick={openFilePicker}>
              <UploadIcon aria-hidden />
              Import agent skill
            </Button>
            <Button onClick={() => setCreateOpen(true)}>
              <PlusIcon aria-hidden />
              Create agent
            </Button>
          </div>
        }
      />

      {fileInput}
      <TokenReveal agent={createdAgent} />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>{analyticsQuery.data?.total_calls ?? 0}</CardTitle>
            <CardDescription>Agent calls in the last 30 days</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{analyticsQuery.data?.active_agents ?? 0}</CardTitle>
            <CardDescription>Active agents with usage</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{skillsQuery.data?.length ?? 0}</CardTitle>
            <CardDescription>Agent skills in hidden storage</CardDescription>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agent credentials</CardTitle>
          <CardDescription>
            Tokens are shown only on create or rotation. The table stores only the prefix.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {agentsQuery.isError ? (
            <ErrorState
              message={
                agentsQuery.error instanceof Error ? agentsQuery.error.message : "Unable to load agents"
              }
              onRetry={() => void agentsQuery.refetch()}
            />
          ) : agentsQuery.data?.length ? (
            <div className="overflow-hidden rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Token</TableHead>
                    <TableHead>Last used</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agentsQuery.data.map((agent) => (
                    <TableRow key={agent.id}>
                      <TableCell>
                        <div className="font-medium">{agent.name}</div>
                        <div className="text-xs text-muted-foreground">{agent.description}</div>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{agent.masked_token}</TableCell>
                      <TableCell>{formatRelativeDate(agent.last_used_at)}</TableCell>
                      <TableCell>
                        <Badge variant={agent.is_active ? "default" : "secondary"}>
                          {agent.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </TableCell>
                      <TableCell className="space-x-2 text-right">
                        <Button size="sm" variant="outline" onClick={() => void handleRotate(agent)}>
                          <RotateCwIcon aria-hidden />
                          Rotate
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void toggleAgent(agent)}>
                          {agent.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <EmptyState
              title="No agents yet"
              description="Create an agent to generate its one-time connection token."
              action={
                <Button onClick={() => setCreateOpen(true)}>
                  <KeyRoundIcon aria-hidden />
                  Create agent
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Agent skills</CardTitle>
          <CardDescription>Skills imported from this tab are excluded from normal teams and analytics.</CardDescription>
        </CardHeader>
        <CardContent>
          {skillsQuery.data?.length ? (
            <div className="overflow-hidden rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Skill</TableHead>
                    <TableHead>Deployment</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {skillsQuery.data.map((skill) => (
                    <TableRow key={skill.id}>
                      <TableCell>
                        <Link
                          to={buildWorkspacePath(workspace, `/skills/${skill.slug}`)}
                          className="block hover:underline"
                        >
                          <div className="font-medium">{skill.title}</div>
                          <div className="text-xs text-muted-foreground">{skill.slug}</div>
                        </Link>
                      </TableCell>
                      <TableCell>
                        {skill.deploy_to_all ? "All agents" : `${skill.agent_ids.length} selected agents`}
                      </TableCell>
                      <TableCell>{formatRelativeDate(skill.updated_at)}</TableCell>
                      <TableCell className="space-x-2 text-right">
                        <Button asChild size="sm" variant="outline">
                          <Link to={buildWorkspacePath(workspace, `/skills/${skill.slug}`)}>
                            <PencilIcon aria-hidden />
                            Open
                          </Link>
                        </Button>
                        <Button asChild size="sm" variant="ghost">
                          <Link
                            to={buildWorkspacePath(workspace, `/skills/${skill.slug}/history`)}
                          >
                            <HistoryIcon aria-hidden />
                            History
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <EmptyState
              title="No agent skills"
              description="Import a .skill file and choose which agents receive it."
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Usage logs</CardTitle>
          <CardDescription>Agent activity is tracked separately from people-facing analytics.</CardDescription>
        </CardHeader>
        <CardContent>
          {usageQuery.data?.items.length ? (
            <div className="overflow-hidden rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Agent</TableHead>
                    <TableHead>Skill</TableHead>
                    <TableHead>Tool</TableHead>
                    <TableHead>Called</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usageQuery.data.items.map((event) => (
                    <TableRow key={event.id}>
                      <TableCell>{event.agent_name ?? "Unknown agent"}</TableCell>
                      <TableCell>{event.skill_title}</TableCell>
                      <TableCell>{event.tool_name || event.client_type}</TableCell>
                      <TableCell>{formatRelativeDate(event.called_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <EmptyState title="No agent usage yet" description="Agent MCP calls will appear here." />
          )}
        </CardContent>
      </Card>

      <CreateAgentDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={setCreatedAgent} />
      <ImportAgentSkillDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        importData={importData}
        agents={agentsQuery.data ?? []}
        onConsumed={() => setImportData(null)}
      />
    </div>
  )
}
