import * as React from "react"

import { ChevronRightIcon } from "lucide-react"

import { VISIBILITY_OPTIONS, groupDepartmentsByTeam } from "@/lib/skill-visibility"
import type { TeamGroup } from "@/lib/skill-visibility"
import type { Department, SkillVisibility } from "@/types"
import { cn } from "@/lib/utils"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"

function TeamTreeNode({
  group,
  sharedWithIds,
  onToggleDept,
  onToggleTeam,
}: {
  group: TeamGroup
  sharedWithIds: Set<string>
  onToggleDept: (id: string) => void
  onToggleTeam: (deptIds: string[], checked: boolean) => void
}) {
  const deptIds = group.departments.map((d) => d.id)
  const selectedCount = deptIds.filter((id) => sharedWithIds.has(id)).length
  const allSelected = selectedCount === deptIds.length
  const someSelected = selectedCount > 0 && !allSelected

  return (
    <Collapsible defaultOpen>
      <div className="flex items-center gap-2">
        <Checkbox
          checked={allSelected ? true : someSelected ? "indeterminate" : false}
          onCheckedChange={(checked) => onToggleTeam(deptIds, checked === true)}
        />
        <CollapsibleTrigger className="group flex flex-1 cursor-pointer items-center gap-1 py-1 text-xs font-semibold text-foreground hover:text-foreground/80">
          <ChevronRightIcon
            className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-90"
            aria-hidden
          />
          {group.teamName}
          {selectedCount > 0 ? (
            <span className="ml-auto font-normal text-muted-foreground">
              {selectedCount}/{deptIds.length}
            </span>
          ) : null}
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent>
        <div className="ml-6 mt-0.5 space-y-0.5">
          {group.departments.map((dept) => (
            <label
              key={dept.id}
              className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted/50"
            >
              <Checkbox
                checked={sharedWithIds.has(dept.id)}
                onCheckedChange={() => onToggleDept(dept.id)}
              />
              {dept.name}
            </label>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

type VisibilityScopeSelectorProps = {
  ownerDepartmentId: string
  ownerTeamSlug: string
  visibility: SkillVisibility
  onVisibilityChange: (v: SkillVisibility) => void
  sharedWithIds: Set<string>
  onSharedWithIdsChange: (ids: Set<string>) => void
  allDepartments: Department[]
  /** When true, the Workspace-wide option is shown as disabled with a hint */
  disableWorkspace?: boolean
  /** Used by create flow to exclude the selected team's departments from the shareable list */
  excludeTeamSlug?: string
  /** Display name for the owning team, used in the "Team-wide" card description */
  ownerTeamName?: string
}

export function VisibilityScopeSelector({
  ownerDepartmentId,
  ownerTeamSlug,
  visibility,
  onVisibilityChange,
  sharedWithIds,
  onSharedWithIdsChange,
  allDepartments,
  disableWorkspace = false,
  excludeTeamSlug,
  ownerTeamName,
}: VisibilityScopeSelectorProps) {
  const allGroups = React.useMemo(() => groupDepartmentsByTeam(allDepartments), [allDepartments])

  const shareableDepartments = React.useMemo(() => {
    if (visibility === "workspace" || visibility === "team") return []
    return allDepartments.filter((d) => d.id !== ownerDepartmentId)
  }, [allDepartments, ownerDepartmentId, visibility])

  const shareableGroups = React.useMemo(
    () => groupDepartmentsByTeam(shareableDepartments),
    [shareableDepartments],
  )

  const shareableTeams = React.useMemo(
    () =>
      visibility === "team"
        ? allGroups.filter((t) => t.teamSlug !== ownerTeamSlug && t.teamSlug !== excludeTeamSlug)
        : [],
    [visibility, allGroups, ownerTeamSlug, excludeTeamSlug],
  )

  const showSharedWith =
    visibility !== "workspace" &&
    (visibility === "team" ? shareableTeams.length > 0 : shareableDepartments.length > 0)

  function toggleDept(deptId: string) {
    const next = new Set(sharedWithIds)
    if (next.has(deptId)) next.delete(deptId)
    else next.add(deptId)
    onSharedWithIdsChange(next)
  }

  function toggleTeam(deptIds: string[], checked: boolean) {
    const next = new Set(sharedWithIds)
    for (const id of deptIds) {
      if (checked) next.add(id)
      else next.delete(id)
    }
    onSharedWithIdsChange(next)
  }

  function toggleTeamShare(deptIds: string[], checked: boolean) {
    const next = new Set(sharedWithIds)
    for (const id of deptIds) {
      if (checked) next.add(id)
      else next.delete(id)
    }
    onSharedWithIdsChange(next)
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Who can see this skill</Label>
        <RadioGroup
          value={visibility}
          onValueChange={(v) => {
            onVisibilityChange(v as SkillVisibility)
            onSharedWithIdsChange(new Set())
          }}
          className="grid grid-cols-3 gap-2"
        >
          {VISIBILITY_OPTIONS.map((option) => {
            const Icon = option.icon
            const isSelected = visibility === option.value
            const isDisabled = option.value === "workspace" && disableWorkspace

            return (
              <label
                key={option.value}
                title={
                  isDisabled ? "Only workspace admins can set workspace-wide visibility" : undefined
                }
                className={cn(
                  "relative flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-center transition-colors",
                  isSelected
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "border-border hover:border-muted-foreground/30 hover:bg-muted/50",
                  isDisabled && "cursor-not-allowed opacity-50",
                )}
              >
                <RadioGroupItem value={option.value} className="sr-only" disabled={isDisabled} />
                <Icon
                  className={cn("size-4", isSelected ? "text-primary" : "text-muted-foreground")}
                  aria-hidden
                />
                <span
                  className={cn(
                    "text-xs font-medium leading-none",
                    isSelected ? "text-primary" : "text-foreground",
                  )}
                >
                  {option.label}
                </span>
                <span className="text-[10px] leading-tight text-muted-foreground">
                  {option.description(visibility === "team" ? ownerTeamName : undefined)}
                </span>
              </label>
            )
          })}
        </RadioGroup>
        {disableWorkspace ? (
          <p className="text-xs text-muted-foreground">
            Only workspace admins can set workspace-wide visibility.
          </p>
        ) : null}
      </div>

      {showSharedWith ? (
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <Label>Also share with</Label>
            {sharedWithIds.size > 0 ? (
              <span className="text-xs text-muted-foreground">
                {sharedWithIds.size} department{sharedWithIds.size !== 1 ? "s" : ""}
              </span>
            ) : null}
          </div>
          <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border p-2">
            {visibility === "team"
              ? shareableTeams.map((team) => {
                  const deptIds = team.departments.map((d) => d.id)
                  const checkedCount = deptIds.filter((id) => sharedWithIds.has(id)).length
                  const allChecked = checkedCount === deptIds.length && deptIds.length > 0
                  const someChecked = checkedCount > 0 && !allChecked
                  return (
                    <label
                      key={team.teamSlug}
                      className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted/50"
                    >
                      <Checkbox
                        checked={allChecked ? true : someChecked ? "indeterminate" : false}
                        onCheckedChange={(c) => toggleTeamShare(deptIds, c === true)}
                      />
                      {team.teamName}
                    </label>
                  )
                })
              : shareableGroups.map((group) => (
                  <TeamTreeNode
                    key={group.teamSlug}
                    group={group}
                    sharedWithIds={sharedWithIds}
                    onToggleDept={toggleDept}
                    onToggleTeam={toggleTeam}
                  />
                ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
