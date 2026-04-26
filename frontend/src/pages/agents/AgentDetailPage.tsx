import * as React from "react"

import { ArrowLeftIcon, CopyIcon, HistoryIcon, PencilIcon, RotateCwIcon } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useAgentAnalytics,
  useAgentSkills,
  useAgentUsage,
  useAgents,
  useRotateAgentToken,
  useUpdateAgent,
} from "@/api/client"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { PageHeader } from "@/components/shared/PageHeader"
import { buildWorkspacePath, formatRelativeDate } from "@/lib/format"
import type { Agent, CreatedAgent } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function isDeployedToAgent(
  skill: { deploy_to_all: boolean; agent_ids: string[] },
  agentId: string,
) {
  return skill.deploy_to_all || skill.agent_ids.includes(agentId)
}

function TokenReveal({ agent }: { agent: CreatedAgent | null }) {
  if (!agent) return null

  async function copyToken() {
    try {
      await navigator.clipboard.writeText(agent.token)
      toast.success("Agent token copied")
    } catch {
      toast.error("Clipboard access was blocked")
    }
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
      <p className="font-medium">Save this rotated token now. It will not be shown again.</p>
      <div className="mt-2 flex items-center gap-2 rounded-md bg-background p-2 font-mono text-xs text-foreground">
        <code className="min-w-0 flex-1 break-all">{agent.token}</code>
        <Button size="sm" variant="outline" onClick={() => void copyToken()}>
          <CopyIcon aria-hidden />
          Copy
        </Button>
      </div>
    </div>
  )
}

export function AgentDetailPage() {
  const { workspace, agentId } = useParams<{ workspace: string; agentId: string }>()
  const agentsQuery = useAgents()
  const skillsQuery = useAgentSkills()
  const analyticsQuery = useAgentAnalytics(30, agentId)
  const usageQuery = useAgentUsage(30, agentId)
  const updateAgent = useUpdateAgent()
  const rotateToken = useRotateAgentToken()
  const [rotatedAgent, setRotatedAgent] = React.useState<CreatedAgent | null>(null)

  const agent = React.useMemo(
    () => agentsQuery.data?.find((item) => item.id === agentId),
    [agentId, agentsQuery.data],
  )
  const deployedSkills = React.useMemo(
    () =>
      agentId ? (skillsQuery.data ?? []).filter((skill) => isDeployedToAgent(skill, agentId)) : [],
    [agentId, skillsQuery.data],
  )

  async function handleRotate(currentAgent: Agent) {
    try {
      const rotated = await rotateToken.mutateAsync(currentAgent.id)
      setRotatedAgent(rotated)
      toast.success("Agent token rotated")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to rotate token")
    }
  }

  async function toggleAgent(currentAgent: Agent) {
    try {
      await updateAgent.mutateAsync({
        id: currentAgent.id,
        is_active: !currentAgent.is_active,
      })
      toast.success(currentAgent.is_active ? "Agent deactivated" : "Agent activated")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update agent")
    }
  }

  if (agentsQuery.isError) {
    return (
      <ErrorState
        message={
          agentsQuery.error instanceof Error ? agentsQuery.error.message : "Unable to load agent"
        }
        onRetry={() => void agentsQuery.refetch()}
      />
    )
  }

  if (!agentsQuery.data) {
    return (
      <div className="space-y-8">
        <Button asChild size="sm" variant="ghost">
          <Link to={buildWorkspacePath(workspace, "/agents")}>
            <ArrowLeftIcon />
            Agents
          </Link>
        </Button>
        <Card>
          <CardHeader>
            <CardTitle>Loading agent...</CardTitle>
            <CardDescription>Fetching agent details and usage.</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  if (!agent) {
    return (
      <ErrorState
        title="Agent not found"
        message="This agent does not exist in the current workspace."
      />
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="ghost">
          <Link to={buildWorkspacePath(workspace, "/agents")}>
            <ArrowLeftIcon />
            Agents
          </Link>
        </Button>
      </div>

      <PageHeader
        title={agent.name}
        description={agent.description || "Agent credentials, deployed skills, and recent usage."}
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => void handleRotate(agent)}>
              <RotateCwIcon aria-hidden />
              Rotate token
            </Button>
            <Button variant="outline" onClick={() => void toggleAgent(agent)}>
              {agent.is_active ? "Deactivate" : "Activate"}
            </Button>
          </div>
        }
      />

      <TokenReveal agent={rotatedAgent} />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>{analyticsQuery.data?.total_calls ?? 0}</CardTitle>
            <CardDescription>Calls in the last 30 days</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{deployedSkills.length}</CardTitle>
            <CardDescription>Skills deployed to this agent</CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{analyticsQuery.data?.skills_touched ?? 0}</CardTitle>
            <CardDescription>Skills used in the last 30 days</CardDescription>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agent credentials</CardTitle>
          <CardDescription>Token values are only shown on create or rotation.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-muted-foreground">Token prefix</p>
              <p className="font-mono font-medium">{agent.masked_token}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Status</p>
              <Badge variant={agent.is_active ? "default" : "secondary"}>
                {agent.is_active ? "Active" : "Inactive"}
              </Badge>
            </div>
            <div>
              <p className="text-muted-foreground">Last used</p>
              <p className="font-medium">{formatRelativeDate(agent.last_used_at)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Created</p>
              <p className="font-medium">{formatRelativeDate(agent.created_at)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Skills deployed to {agent.name}</CardTitle>
          <CardDescription>
            Open a skill to edit its content, history, and agent deployment.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {skillsQuery.isError ? (
            <ErrorState
              message={
                skillsQuery.error instanceof Error
                  ? skillsQuery.error.message
                  : "Unable to load skills"
              }
              onRetry={() => void skillsQuery.refetch()}
            />
          ) : deployedSkills.length ? (
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
                  {deployedSkills.map((skill) => (
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
                      <TableCell>{skill.deploy_to_all ? "All agents" : "Selected agent"}</TableCell>
                      <TableCell>{formatRelativeDate(skill.updated_at)}</TableCell>
                      <TableCell className="space-x-2 text-right">
                        <Button asChild size="sm" variant="outline">
                          <Link to={buildWorkspacePath(workspace, `/skills/${skill.slug}`)}>
                            <PencilIcon aria-hidden />
                            Open editor
                          </Link>
                        </Button>
                        <Button asChild size="sm" variant="ghost">
                          <Link to={buildWorkspacePath(workspace, `/skills/${skill.slug}/history`)}>
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
              title="No skills deployed"
              description="Deploy skills from the Agents overview or from an agent skill page."
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent usage</CardTitle>
          <CardDescription>Calls made by this agent in the last 30 days.</CardDescription>
        </CardHeader>
        <CardContent>
          {usageQuery.data?.items.length ? (
            <div className="overflow-hidden rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Skill</TableHead>
                    <TableHead>Tool</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Called</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usageQuery.data.items.map((event) => (
                    <TableRow key={event.id}>
                      <TableCell>
                        <Link
                          to={buildWorkspacePath(workspace, `/skills/${event.skill_slug}`)}
                          className="font-medium hover:underline"
                        >
                          {event.skill_title}
                        </Link>
                      </TableCell>
                      <TableCell>{event.tool_name || event.client_type}</TableCell>
                      <TableCell>v{event.version_number}</TableCell>
                      <TableCell>{formatRelativeDate(event.called_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <EmptyState
              title="No usage yet"
              description="This agent has not called any skills recently."
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
