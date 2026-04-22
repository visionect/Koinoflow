import { GlobeIcon, LockIcon, UsersIcon } from "lucide-react"
import type React from "react"

import type { Department, ProcessVisibility } from "@/types"

export const VISIBILITY_OPTIONS: {
  value: ProcessVisibility
  label: string
  description: (teamName?: string) => string
  icon: React.ElementType
}[] = [
  {
    value: "department",
    label: "Department only",
    description: () => "Only members of this department",
    icon: LockIcon,
  },
  {
    value: "team",
    label: "Team-wide",
    description: (teamName) =>
      teamName ? `All members of ${teamName}` : "All members of the team",
    icon: UsersIcon,
  },
  {
    value: "workspace",
    label: "Workspace-wide",
    description: () => "Everyone in the workspace",
    icon: GlobeIcon,
  },
]

export interface TeamGroup {
  teamSlug: string
  teamName: string
  departments: Department[]
}

export function groupDepartmentsByTeam(departments: Department[]): TeamGroup[] {
  const map = new Map<string, TeamGroup>()
  for (const dept of departments) {
    const existing = map.get(dept.team_slug)
    if (existing) {
      existing.departments.push(dept)
    } else {
      map.set(dept.team_slug, {
        teamSlug: dept.team_slug,
        teamName: dept.team_name,
        departments: [dept],
      })
    }
  }
  return [...map.values()]
}
