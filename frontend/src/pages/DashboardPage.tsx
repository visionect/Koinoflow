import { BarChart3Icon, BotIcon, Building2Icon, FileTextIcon, KeyRoundIcon } from "lucide-react"
import { Link, useParams } from "react-router-dom"

import { useSkills, useTeams, useUsageSummary } from "@/api/client"
import { PageHeader } from "@/components/shared/PageHeader"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { buildWorkspacePath } from "@/lib/format"

function DashboardMetric({
  icon: Icon,
  label,
  value,
  description,
  isLoading,
}: {
  icon: typeof Building2Icon
  label: string
  value: string | number
  description: string
  isLoading?: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardDescription>{label}</CardDescription>
          {isLoading ? (
            <Skeleton className="mt-2 h-9 w-20" />
          ) : (
            <CardTitle className="mt-2 text-3xl">{value}</CardTitle>
          )}
        </div>
        <div className="rounded-xl bg-primary/10 p-2 text-primary">
          <Icon className="size-5" aria-hidden />
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}

export function DashboardPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const teamsQuery = useTeams()
  const skillsQuery = useSkills({ limit: 100 })
  const usageSummaryQuery = useUsageSummary(30)

  const departmentCount =
    teamsQuery.data?.reduce((total, team) => total + team.department_count, 0) ?? 0
  const totalUsageCalls =
    usageSummaryQuery.data?.reduce((total, item) => total + item.total_calls, 0) ?? 0

  const topSkill = usageSummaryQuery.data?.[0]?.skill_title

  return (
    <div className="space-y-8">
      <PageHeader
        title="Workspace dashboard"
        description="Keep a pulse on your operational knowledge, ownership structure, and AI usage."
        action={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link to={buildWorkspacePath(workspace, "/settings/mcp")}>
                <BotIcon />
                MCP connections
              </Link>
            </Button>
            <Button asChild>
              <Link to={buildWorkspacePath(workspace, "/skills")}>
                <FileTextIcon />
                View skills
              </Link>
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <DashboardMetric
          icon={Building2Icon}
          label="Teams"
          value={teamsQuery.data?.length ?? "—"}
          description={
            teamsQuery.data
              ? `${departmentCount} departments currently organized across the workspace.`
              : "Loading team data…"
          }
          isLoading={teamsQuery.isLoading}
        />
        <DashboardMetric
          icon={FileTextIcon}
          label="Skills"
          value={skillsQuery.data?.count ?? "—"}
          description="Operational skills documented and ready for internal teams or AI clients."
          isLoading={skillsQuery.isLoading}
        />
        <DashboardMetric
          icon={BarChart3Icon}
          label="Usage calls"
          value={usageSummaryQuery.data ? totalUsageCalls : "—"}
          description="Skill retrieval calls in the last 30 days."
          isLoading={usageSummaryQuery.isLoading}
        />
        <DashboardMetric
          icon={KeyRoundIcon}
          label="Top skill"
          value={usageSummaryQuery.data ? (topSkill ?? "None yet") : "—"}
          description="The most frequently consumed skill over the current reporting period."
          isLoading={usageSummaryQuery.isLoading}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Adoption snapshot</CardTitle>
            <CardDescription>
              The product becomes more valuable as teams document more skills and clients consume
              them consistently.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              Start by organizing teams and departments, then create operational runbooks under each
              area. Published skills become immediately available to connected MCP clients.
            </p>
            <p>
              API keys and the usage dashboard provide the visibility needed to run Koinoflow in a
              production environment with confidence.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Next actions</CardTitle>
            <CardDescription>Suggested steps to keep onboarding moving.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button asChild className="w-full justify-start" variant="outline">
              <Link to={buildWorkspacePath(workspace, "/teams")}>Create or refine teams</Link>
            </Button>
            <Button asChild className="w-full justify-start" variant="outline">
              <Link to={buildWorkspacePath(workspace, "/skills")}>Review all skills</Link>
            </Button>
            <Button asChild className="w-full justify-start" variant="outline">
              <Link to={buildWorkspacePath(workspace, "/usage")}>Open analytics</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
