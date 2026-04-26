import * as React from "react"

import { useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useAuditRules,
  useCreateAuditRule,
  useCreateStalenessAlertRule,
  useDepartments,
  useEffectiveSettings,
  useTeams,
  useUpdateStalenessAlertRule,
  useUpsertSettings,
  useWorkspace,
} from "@/api/client"
import { PageHeader } from "@/components/shared/PageHeader"
import { useAuth } from "@/hooks/useAuth"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type TriState = "true" | "false" | "inherit"

function toTriState(value: boolean | null): TriState {
  if (value === true) return "true"
  if (value === false) return "false"
  return "inherit"
}

function fromTriState(value: TriState): boolean | null {
  if (value === "true") return true
  if (value === "false") return false
  return null
}

const BOOLEAN_SETTINGS = [
  {
    key: "enable_api_access" as const,
    label: "Enable API access",
    description: "Allow external clients to read skills via the API.",
  },
  {
    key: "require_change_summary" as const,
    label: "Require change summary",
    description: "Require authors to provide a change summary when publishing a version.",
  },
  {
    key: "allow_agent_skill_updates" as const,
    label: "Allow agent skill updates",
    description:
      "Allow AI agents (via MCP) to propose and publish new skill versions. Disabled by default.",
  },
]

type BooleanSettingKey = (typeof BOOLEAN_SETTINGS)[number]["key"]

export function SettingsPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const { isAdmin } = useAuth()
  const workspaceQuery = useWorkspace(workspace ?? "")
  const teamsQuery = useTeams()
  const [selectedTeamId, setSelectedTeamId] = React.useState<string>("")
  const [selectedDeptId, setSelectedDeptId] = React.useState<string>("")

  const selectedTeam = teamsQuery.data?.find((t) => t.id === selectedTeamId)
  const departmentsQuery = useDepartments(selectedTeam?.slug)

  React.useEffect(() => {
    setSelectedDeptId("")
  }, [selectedTeamId])

  const scopeTeamId = selectedTeamId || undefined
  const scopeDeptId = selectedDeptId || undefined

  const settingsQuery = useEffectiveSettings(scopeTeamId, scopeDeptId)
  const auditRulesQuery = useAuditRules()
  const upsertSettings = useUpsertSettings()
  const createAuditRule = useCreateAuditRule()
  const createStalenessAlertRule = useCreateStalenessAlertRule()
  const updateStalenessAlertRule = useUpdateStalenessAlertRule()

  const currentAuditRule = settingsQuery.data?.skill_audit ?? null
  const [auditPeriod, setAuditPeriod] = React.useState(String(currentAuditRule?.period_days ?? 90))

  React.useEffect(() => {
    if (currentAuditRule) {
      setAuditPeriod(String(currentAuditRule.period_days))
    }
  }, [currentAuditRule])

  const currentStalenessRule = settingsQuery.data?.staleness_alert ?? null
  const [stalenessPeriod, setStalenessPeriod] = React.useState(
    String(currentStalenessRule?.period_days ?? 30),
  )

  React.useEffect(() => {
    if (currentStalenessRule) {
      setStalenessPeriod(String(currentStalenessRule.period_days))
    }
  }, [currentStalenessRule])

  const scopeLabel = selectedDeptId ? "department" : selectedTeamId ? "team" : "workspace"
  const isSubScope = Boolean(scopeTeamId || scopeDeptId)
  const hasTeams = (teamsQuery.data?.length ?? 0) > 0

  async function handleSettingChange(key: BooleanSettingKey, value: TriState) {
    if (!workspaceQuery.data) return
    try {
      await upsertSettings.mutateAsync({
        workspace_id: workspaceQuery.data.id,
        team_id: scopeTeamId ?? null,
        department_id: scopeDeptId ?? null,
        [key]: fromTriState(value),
      })
      toast.success("Setting updated")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update setting")
    }
  }

  async function handleAuditToggle(value: TriState) {
    if (!workspaceQuery.data) return
    try {
      if (value === "true") {
        const days = parseInt(auditPeriod, 10) || 90
        const existing = auditRulesQuery.data?.find((r) => r.period_days === days)
        const ruleId = existing
          ? existing.id
          : (await createAuditRule.mutateAsync({ period_days: days })).id
        await upsertSettings.mutateAsync({
          workspace_id: workspaceQuery.data.id,
          team_id: scopeTeamId ?? null,
          department_id: scopeDeptId ?? null,
          skill_audit_id: ruleId,
        })
        toast.success("Skill audit enabled")
      } else {
        await upsertSettings.mutateAsync({
          workspace_id: workspaceQuery.data.id,
          team_id: scopeTeamId ?? null,
          department_id: scopeDeptId ?? null,
          skill_audit_id: "",
        })
        toast.success(
          value === "inherit" ? "Skill audit set to inherit" : "Skill audit disabled",
        )
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update skill audit")
    }
  }

  async function handleAuditPeriodApply() {
    if (!workspaceQuery.data) return
    const days = parseInt(auditPeriod, 10)
    if (!days || days < 1) {
      toast.error("Enter a valid number of days (minimum 1)")
      return
    }
    try {
      const existing = auditRulesQuery.data?.find((r) => r.period_days === days)
      const ruleId = existing
        ? existing.id
        : (await createAuditRule.mutateAsync({ period_days: days })).id
      await upsertSettings.mutateAsync({
        workspace_id: workspaceQuery.data.id,
        team_id: scopeTeamId ?? null,
        department_id: scopeDeptId ?? null,
        skill_audit_id: ruleId,
      })
      toast.success(`Skill audit updated: every ${days} days`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update audit period")
    }
  }

  async function handleStalenessToggle(value: TriState) {
    if (!workspaceQuery.data) return
    try {
      if (value === "true") {
        const days = parseInt(stalenessPeriod, 10) || 30
        const rule = await createStalenessAlertRule.mutateAsync({
          period_days: days,
          notify_admins: true,
          notify_team_managers: false,
          notify_skill_owner: true,
        })
        await upsertSettings.mutateAsync({
          workspace_id: workspaceQuery.data.id,
          team_id: scopeTeamId ?? null,
          department_id: scopeDeptId ?? null,
          staleness_alert_id: rule.id,
        })
        toast.success("Staleness alerts enabled")
      } else {
        await upsertSettings.mutateAsync({
          workspace_id: workspaceQuery.data.id,
          team_id: scopeTeamId ?? null,
          department_id: scopeDeptId ?? null,
          staleness_alert_id: "",
        })
        toast.success(
          value === "inherit" ? "Staleness alerts set to inherit" : "Staleness alerts disabled",
        )
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update staleness alerts")
    }
  }

  async function handleStalenessPeriodApply() {
    if (!currentStalenessRule) return
    const days = parseInt(stalenessPeriod, 10)
    if (!days || days < 1) {
      toast.error("Enter a valid number of days (minimum 1)")
      return
    }
    try {
      await updateStalenessAlertRule.mutateAsync({ id: currentStalenessRule.id, period_days: days })
      toast.success(`Staleness alert updated: every ${days} days`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update staleness period")
    }
  }

  async function handleStalenessRecipient(
    field: "notify_admins" | "notify_team_managers" | "notify_skill_owner",
    checked: boolean,
  ) {
    if (!currentStalenessRule) return
    try {
      await updateStalenessAlertRule.mutateAsync({ id: currentStalenessRule.id, [field]: checked })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update recipients")
    }
  }

  const auditTriState: TriState = currentAuditRule ? "true" : "false"
  const auditPeriodChanged =
    currentAuditRule && String(currentAuditRule.period_days) !== auditPeriod

  const stalenessTriState: TriState = currentStalenessRule ? "true" : "false"
  const stalenessPeriodChanged =
    currentStalenessRule && String(currentStalenessRule.period_days) !== stalenessPeriod

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workspace settings"
        description="Configure policies that govern how skills are managed across the workspace."
      />

      {isAdmin && hasTeams ? (
        <Card>
          <CardHeader>
            <CardTitle>Scope</CardTitle>
            <CardDescription>
              Choose which level to view and edit policies for. Team and department overrides take
              precedence over workspace defaults.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-1.5">
                <Label>Level</Label>
                <Select
                  value={selectedDeptId ? "department" : selectedTeamId ? "team" : "workspace"}
                  onValueChange={(value) => {
                    if (value === "workspace") {
                      setSelectedTeamId("")
                      setSelectedDeptId("")
                    } else if (value === "team") {
                      setSelectedDeptId("")
                      if (!selectedTeamId && teamsQuery.data?.[0]) {
                        setSelectedTeamId(teamsQuery.data[0].id)
                      }
                    } else if (value === "department") {
                      if (!selectedTeamId && teamsQuery.data?.[0]) {
                        setSelectedTeamId(teamsQuery.data[0].id)
                      }
                    }
                  }}
                >
                  <SelectTrigger className="w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="workspace">Workspace</SelectItem>
                    <SelectItem value="team">Team</SelectItem>
                    <SelectItem value="department">Department</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {selectedTeamId || scopeLabel === "team" || scopeLabel === "department" ? (
                <div className="space-y-1.5">
                  <Label>Team</Label>
                  <Select value={selectedTeamId} onValueChange={setSelectedTeamId}>
                    <SelectTrigger className="w-52">
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

              {scopeLabel === "department" && selectedTeamId ? (
                <div className="space-y-1.5">
                  <Label>Department</Label>
                  <Select value={selectedDeptId} onValueChange={setSelectedDeptId}>
                    <SelectTrigger className="w-52">
                      <SelectValue placeholder="Select a department" />
                    </SelectTrigger>
                    <SelectContent>
                      {departmentsQuery.data?.map((dept) => (
                        <SelectItem key={dept.id} value={dept.id}>
                          {dept.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Policies</CardTitle>
              <CardDescription>
                {isSubScope
                  ? `Overrides for this ${scopeLabel}. Set to "Inherit" to fall back to the parent scope.`
                  : "Configure workspace-wide rules for skill management."}
              </CardDescription>
            </div>
            <Badge variant="secondary" className="capitalize">
              {scopeLabel}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {!isAdmin ? (
            <p className="rounded-md border bg-muted/50 p-3 text-xs text-muted-foreground">
              You&rsquo;re viewing effective settings for your workspace. Contact an admin to make
              changes.
            </p>
          ) : null}

          {BOOLEAN_SETTINGS.map((setting) => {
            const currentValue = settingsQuery.data?.[setting.key] ?? null
            // At workspace scope null means "not set" — treat as Disabled since there's no parent to inherit
            const selectValue = isSubScope
              ? toTriState(currentValue)
              : currentValue === null
                ? "false"
                : toTriState(currentValue)
            return (
              <div
                key={setting.key}
                className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between rounded-lg border p-4"
              >
                <div className="space-y-0.5">
                  <p className="text-sm font-medium">{setting.label}</p>
                  <p className="text-xs text-muted-foreground">{setting.description}</p>
                </div>
                {isAdmin ? (
                  <Select
                    value={selectValue}
                    onValueChange={(value) =>
                      void handleSettingChange(setting.key, value as TriState)
                    }
                    disabled={upsertSettings.isPending}
                  >
                    <SelectTrigger className="w-36 shrink-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="true">Enabled</SelectItem>
                      <SelectItem value="false">Disabled</SelectItem>
                      {isSubScope ? <SelectItem value="inherit">Inherit</SelectItem> : null}
                    </SelectContent>
                  </Select>
                ) : (
                  <Badge variant={currentValue === true ? "default" : "secondary"}>
                    {currentValue === true
                      ? "Enabled"
                      : currentValue === false
                        ? "Disabled"
                        : "Default"}
                  </Badge>
                )}
              </div>
            )
          })}

          {/* Skill audit row */}
          <div className="rounded-lg border p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">Skill audit</p>
                <p className="text-xs text-muted-foreground">
                  Require skill owners to periodically confirm their skills are still accurate.
                </p>
                {currentAuditRule ? (
                  <div className="flex items-center gap-2 pt-2">
                    <span className="text-xs text-muted-foreground">Review every</span>
                    <Input
                      type="number"
                      min="1"
                      className="h-7 w-20 text-xs"
                      value={auditPeriod}
                      onChange={(e) => setAuditPeriod(e.target.value)}
                      disabled={!isAdmin}
                    />
                    <span className="text-xs text-muted-foreground">days</span>
                    {isAdmin && auditPeriodChanged ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        disabled={upsertSettings.isPending || createAuditRule.isPending}
                        onClick={() => void handleAuditPeriodApply()}
                      >
                        Apply
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              {isAdmin ? (
                <Select
                  value={auditTriState}
                  onValueChange={(value) => void handleAuditToggle(value as TriState)}
                  disabled={upsertSettings.isPending || createAuditRule.isPending}
                >
                  <SelectTrigger className="w-36 shrink-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Enabled</SelectItem>
                    <SelectItem value="false">Disabled</SelectItem>
                    {isSubScope ? <SelectItem value="inherit">Inherit</SelectItem> : null}
                  </SelectContent>
                </Select>
              ) : (
                <Badge variant={currentAuditRule ? "default" : "secondary"}>
                  {currentAuditRule ? "Enabled" : "Disabled"}
                </Badge>
              )}
            </div>
          </div>

          {/* Staleness alert row */}
          <div className="rounded-lg border p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-0.5 flex-1 min-w-0">
                <p className="text-sm font-medium">Staleness alerts</p>
                <p className="text-xs text-muted-foreground">
                  Send email alerts when skills haven&rsquo;t been used within a set period.
                </p>
                {currentStalenessRule ? (
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">Alert after</span>
                      <Input
                        type="number"
                        min="1"
                        className="h-7 w-20 text-xs"
                        value={stalenessPeriod}
                        onChange={(e) => setStalenessPeriod(e.target.value)}
                        disabled={!isAdmin}
                      />
                      <span className="text-xs text-muted-foreground">days without use</span>
                      {isAdmin && stalenessPeriodChanged ? (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          disabled={updateStalenessAlertRule.isPending}
                          onClick={() => void handleStalenessPeriodApply()}
                        >
                          Apply
                        </Button>
                      ) : null}
                    </div>
                    {isAdmin ? (
                      <div className="space-y-1.5">
                        <p className="text-xs font-medium text-muted-foreground">Notify</p>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <Checkbox
                            checked={currentStalenessRule.notify_admins}
                            onCheckedChange={(checked) =>
                              void handleStalenessRecipient("notify_admins", Boolean(checked))
                            }
                            disabled={updateStalenessAlertRule.isPending}
                          />
                          <span className="text-xs">Workspace admins</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <Checkbox
                            checked={currentStalenessRule.notify_team_managers}
                            onCheckedChange={(checked) =>
                              void handleStalenessRecipient(
                                "notify_team_managers",
                                Boolean(checked),
                              )
                            }
                            disabled={updateStalenessAlertRule.isPending}
                          />
                          <span className="text-xs">Team managers</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <Checkbox
                            checked={currentStalenessRule.notify_skill_owner}
                            onCheckedChange={(checked) =>
                              void handleStalenessRecipient(
                                "notify_skill_owner",
                                Boolean(checked),
                              )
                            }
                            disabled={updateStalenessAlertRule.isPending}
                          />
                          <span className="text-xs">Skill owners</span>
                        </label>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
              {isAdmin ? (
                <Select
                  value={stalenessTriState}
                  onValueChange={(value) => void handleStalenessToggle(value as TriState)}
                  disabled={
                    upsertSettings.isPending ||
                    createStalenessAlertRule.isPending ||
                    updateStalenessAlertRule.isPending
                  }
                >
                  <SelectTrigger className="w-36 shrink-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Enabled</SelectItem>
                    <SelectItem value="false">Disabled</SelectItem>
                    {isSubScope ? <SelectItem value="inherit">Inherit</SelectItem> : null}
                  </SelectContent>
                </Select>
              ) : (
                <Badge variant={currentStalenessRule ? "default" : "secondary"}>
                  {currentStalenessRule ? "Enabled" : "Disabled"}
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
