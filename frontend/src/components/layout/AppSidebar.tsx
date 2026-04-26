import {
  BarChart3Icon,
  BotIcon,
  Building2Icon,
  FileTextIcon,
  KeyRoundIcon,
  LayoutDashboardIcon,
  PlugZapIcon,
  SettingsIcon,
  SparklesIcon,
  UsersIcon,
} from "lucide-react"
import { Link, NavLink, useParams } from "react-router-dom"

import { useEffectiveSettings, useTeams } from "@/api/client"
import { useAuth } from "@/hooks/useAuth"
import { buildWorkspacePath } from "@/lib/format"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarRail,
  SidebarSeparator,
} from "@/components/ui/sidebar"

const MONOGRAM_HUES = [25, 65, 150, 220, 290]

function hashString(input: string): number {
  let hash = 0
  for (let i = 0; i < input.length; i++) {
    hash = (hash * 31 + input.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

function getMonogramHue(key: string): number {
  return MONOGRAM_HUES[hashString(key) % MONOGRAM_HUES.length] ?? 65
}

function getMonogramInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return "?"
  const first = words[0] ?? ""
  const second = words[1] ?? ""
  if (!second) return first.slice(0, 2).toUpperCase() || "?"
  return ((first[0] ?? "") + (second[0] ?? "")).toUpperCase() || "?"
}

function TeamMonogram({ name, slug }: { name: string; slug: string }) {
  const hue = getMonogramHue(slug || name)
  const style = {
    backgroundColor: `oklch(0.82 0.09 ${hue})`,
    color: `oklch(0.25 0.12 ${hue})`,
  }
  return (
    <span
      className="flex size-4 shrink-0 items-center justify-center rounded text-[9px] font-semibold tracking-tight"
      style={style}
      aria-hidden
    >
      {getMonogramInitials(name)}
    </span>
  )
}

const PRIMARY_LINKS = [
  {
    label: "Dashboard",
    icon: LayoutDashboardIcon,
    href: "",
  },
  {
    label: "All Skills",
    icon: FileTextIcon,
    href: "/skills",
  },
  {
    label: "Analytics",
    icon: BarChart3Icon,
    href: "/usage",
  },
]

const CAPTURE_LINKS = [
  {
    label: "Connectors",
    tooltip: "Connect chat and doc sources so Capture can propose new skills.",
    icon: PlugZapIcon,
    href: "/capture/connectors",
  },
  {
    label: "Candidates",
    tooltip: "Review Capture-generated process drafts waiting for approval.",
    icon: SparklesIcon,
    href: "/capture/candidates",
  },
]

const AGENTS_LINKS = [
  {
    label: "Agents",
    tooltip: "Manage AI agents, agent skills, and agent usage.",
    icon: BotIcon,
    href: "/agents",
  },
]

const SETTINGS_LINKS = [
  {
    label: "Settings",
    tooltip: "Workspace policies and audit rules.",
    icon: SettingsIcon,
    href: "/settings",
  },
  {
    label: "Members",
    tooltip: "Invite teammates and manage roles.",
    icon: UsersIcon,
    href: "/settings/members",
  },
  {
    label: "MCP",
    tooltip: "Connect AI clients (Cursor, Claude Desktop, …) to this workspace.",
    icon: BotIcon,
    href: "/settings/mcp",
  },
  {
    label: "API Keys",
    tooltip: "Workspace credentials for REST API and automations.",
    icon: KeyRoundIcon,
    href: "/settings/keys",
  },
]

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  team_manager: "Team manager",
  member: "Member",
  viewer: "Viewer",
}

export function AppSidebar() {
  const { workspace } = useParams<{ workspace: string }>()
  const { data: teams, isLoading } = useTeams()
  const { role, hasFeature } = useAuth()
  const { data: wsSettings } = useEffectiveSettings()
  const apiAccessEnabled = wsSettings?.enable_api_access !== false

  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg" tooltip="Koinoflow home">
              <Link to={buildWorkspacePath(workspace)}>
                <img src="/favicon.svg" alt="Koinoflow" className="size-8 shrink-0" />
                <span className="flex flex-col">
                  <span className="font-semibold">Koinoflow</span>
                  <span className="text-xs text-sidebar-foreground/60">{workspace}</span>
                </span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarSeparator />

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Overview</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {PRIMARY_LINKS.map((item) => (
                <SidebarMenuItem key={item.label}>
                  <SidebarMenuButton asChild tooltip={item.label}>
                    <NavLink to={buildWorkspacePath(workspace, item.href)}>
                      <item.icon />
                      <span>{item.label}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Teams</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Teams">
                  <NavLink to={buildWorkspacePath(workspace, "/teams")}>
                    <Building2Icon />
                    <span>Teams</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {isLoading
                ? Array.from({ length: 3 }).map((_, index) => (
                    <SidebarMenuItem key={index}>
                      <SidebarMenuSkeleton showIcon />
                    </SidebarMenuItem>
                  ))
                : teams?.map((team) => (
                    <SidebarMenuItem key={team.id}>
                      <SidebarMenuButton asChild tooltip={team.name}>
                        <NavLink to={buildWorkspacePath(workspace, `/teams/${team.slug}`)}>
                          <TeamMonogram name={team.name} slug={team.slug} />
                          <span>{team.name}</span>
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {hasFeature("capture") && (
          <SidebarGroup>
            <SidebarGroupLabel>Koinoflow Capture</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {CAPTURE_LINKS.map((item) => (
                  <SidebarMenuItem key={item.label}>
                    <SidebarMenuButton asChild tooltip={item.tooltip ?? item.label}>
                      <NavLink to={buildWorkspacePath(workspace, item.href)}>
                        <item.icon />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {hasFeature("agents") && (
          <SidebarGroup>
            <SidebarGroupLabel>Agents</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {AGENTS_LINKS.map((item) => (
                  <SidebarMenuItem key={item.label}>
                    <SidebarMenuButton asChild tooltip={item.tooltip ?? item.label}>
                      <NavLink to={buildWorkspacePath(workspace, item.href)}>
                        <item.icon />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {SETTINGS_LINKS.filter((item) => item.label !== "API Keys" || apiAccessEnabled).map(
                (item) => (
                  <SidebarMenuItem key={item.label}>
                    <SidebarMenuButton asChild tooltip={item.tooltip ?? item.label}>
                      <NavLink to={buildWorkspacePath(workspace, item.href)}>
                        <item.icon />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ),
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <div className="rounded-xl border bg-background/70 px-3 py-2 text-xs text-muted-foreground">
          Signed in as{" "}
          <span className="font-medium text-foreground">{ROLE_LABELS[role ?? ""] ?? "Viewer"}</span>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
