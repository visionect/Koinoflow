import * as React from "react"

import { MoonIcon, Settings2Icon, SunIcon, UserCircle2Icon } from "lucide-react"
import { Link, useLocation, useParams } from "react-router-dom"
import { toast } from "sonner"
import { useTheme } from "next-themes"

import { apiFetch, useDepartment, useTeam } from "@/api/client"
import { useAuth } from "@/hooks/useAuth"
import { buildWorkspacePath, getInitials, startCase } from "@/lib/format"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { SidebarTrigger } from "@/components/ui/sidebar"

const SEGMENT_LABELS: Record<string, string> = {
  teams: "Teams",
  depts: "Departments",
  skills: "Skills",
  settings: "Settings",
  mcp: "MCP",
  keys: "API keys",
  usage: "Analytics",
  edit: "Edit",
  history: "History",
  members: "Members",
  agents: "Agents",
  capture: "Capture",
  candidates: "Candidates",
  connectors: "Connectors",
}

function getLabel(segment: string) {
  return SEGMENT_LABELS[segment] ?? startCase(segment)
}

export function TopNav() {
  const { pathname } = useLocation()
  const params = useParams<{ workspace: string; departmentId: string; teamSlug: string }>()
  const { workspace } = params
  const { user } = useAuth()
  const { setTheme, resolvedTheme } = useTheme()

  const segments = pathname.split("/").filter(Boolean)
  const workspaceSegments = workspace && segments[0] === workspace ? segments.slice(1) : segments

  const deptIndex = workspaceSegments.indexOf("depts")
  const departmentId = deptIndex !== -1 ? workspaceSegments[deptIndex + 1] : undefined
  const teamIndex = workspaceSegments.indexOf("teams")
  const teamSlug = teamIndex !== -1 ? workspaceSegments[teamIndex + 1] : undefined

  const departmentQuery = useDepartment(departmentId ?? "")
  const teamQuery = useTeam(teamSlug ?? "")

  const dynamicLabels: Record<string, string> = {}
  if (departmentId && departmentQuery.data) {
    dynamicLabels[departmentId] = departmentQuery.data.name
  }
  if (teamSlug && teamQuery.data) {
    dynamicLabels[teamSlug] = teamQuery.data.name
  }

  async function handleLogout() {
    try {
      await apiFetch("/auth/logout", { method: "POST" })
      window.location.href = "/login"
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to log out right now")
    }
  }

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b bg-background/80 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-3">
        <SidebarTrigger />
        <Breadcrumb>
          <BreadcrumbList>
            {workspace ? (
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link to={buildWorkspacePath(workspace)}>Workspace</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
            ) : null}
            {workspaceSegments.map((segment, index) => {
              const isLast = index === workspaceSegments.length - 1
              const href = buildWorkspacePath(
                workspace,
                workspaceSegments.slice(0, index + 1).join("/"),
              )

              const label = dynamicLabels[segment] ?? getLabel(segment)

              return (
                <React.Fragment key={href}>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    {isLast ? (
                      <BreadcrumbPage>{label}</BreadcrumbPage>
                    ) : (
                      <BreadcrumbLink asChild>
                        <Link to={href}>{label}</Link>
                      </BreadcrumbLink>
                    )}
                  </BreadcrumbItem>
                </React.Fragment>
              )
            })}
          </BreadcrumbList>
        </Breadcrumb>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-10 gap-3 rounded-full px-2">
            <Avatar className="size-8 border">
              <AvatarFallback>{getInitials(user)}</AvatarFallback>
            </Avatar>
            <div className="hidden text-left sm:block">
              <p className="text-sm font-medium">{user?.email ?? "Guest"}</p>
              <p className="text-xs text-muted-foreground">Workspace member</p>
            </div>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild>
            <Link to={buildWorkspacePath(workspace, "/settings")}>
              <Settings2Icon />
              Settings
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
            {resolvedTheme === "dark" ? <SunIcon /> : <MoonIcon />}
            Toggle theme
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => void handleLogout()} variant="destructive">
            <UserCircle2Icon />
            Logout
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
