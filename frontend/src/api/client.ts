import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import type {
  ApiKey,
  ApiKeyRoleOption,
  ApiOkResponse,
  CandidateListFilters,
  CandidateListResponse,
  CaptureCandidate,
  ConnectorCredential,
  CreateApiKeyInput,
  CreateDepartmentInput,
  CreateSkillInput,
  CreateTeamInput,
  CreateVersionInput,
  CreateWorkspaceInput,
  CreatedApiKey,
  Department,
  EffectiveSettings,
  ExtractionJob,
  FileDiffEntry,
  InviteMemberInput,
  InviteResponse,
  McpConnection,
  McpConnectionScope,
  McpConnectionScopeInput,
  MeResponse,
  Member,
  PaginatedResponse,
  PendingInvitation,
  Skill,
  ProcessAuditRule,
  StalenessAlertRule,
  CreateStalenessAlertRuleInput,
  UpdateStalenessAlertRuleInput,
  SkillDetail,
  ProcessListFilters,
  SkillUsageSummary,
  SkillVersion,
  SkillVersionBrief,
  PromoteCandidateInput,
  RevertVersionInput,
  Team,
  TeamDetail,
  UpdateDepartmentInput,
  UpdateSkillInput,
  UpdateTeamInput,
  UpdateVersionSummaryInput,
  UpsertSettingsInput,
  UsageAnalytics,
  UsageEvent,
  UsageEventFilters,
  CaptureFunnel,
  VersionDiff,
  VersionFile,
  VersionFileDetail,
  Workspace,
} from "@/types"

const API_BASE = "/api/v1"
const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"])

export class ApiError extends Error {
  status: number
  payload: unknown

  constructor(message: string, status: number, payload: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.payload = payload
  }
}

type SearchValue = string | number | boolean | null | undefined

function getCsrfToken() {
  if (typeof document === "undefined") {
    return null
  }

  const token = document.cookie
    .split("; ")
    .find((part) => part.startsWith("csrftoken="))
    ?.split("=")
    .slice(1)
    .join("=")

  return token ?? null
}

function buildSearchParams(params: Record<string, SearchValue>) {
  const searchParams = new URLSearchParams()

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue
    }

    searchParams.set(key, String(value))
  }

  return searchParams.toString()
}

function extractErrorMessage(response: Response, payload: unknown) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail
  }

  if (
    payload &&
    typeof payload === "object" &&
    "message" in payload &&
    typeof payload.message === "string"
  ) {
    return payload.message
  }

  if (typeof payload === "string" && payload.trim().length > 0 && !payload.includes("<html")) {
    return payload
  }

  if (response.status >= 500) {
    return "Something went wrong. Please try again in a moment."
  }

  return `Request failed with status ${response.status}`
}

export async function apiFetch<T>(path: string, options: RequestInit = {}) {
  const method = options.method?.toUpperCase() ?? "GET"
  const headers = new Headers(options.headers)
  const shouldSetJsonContentType = options.body !== undefined && !(options.body instanceof FormData)

  headers.set("Accept", "application/json")

  if (shouldSetJsonContentType && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  if (MUTATION_METHODS.has(method)) {
    const csrfToken = getCsrfToken()
    if (csrfToken && !headers.has("X-CSRFToken")) {
      headers.set("X-CSRFToken", csrfToken)
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    headers,
    credentials: "include",
  })

  const contentType = response.headers.get("content-type") ?? ""
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "")

  if (!response.ok) {
    throw new ApiError(extractErrorMessage(response, payload), response.status, payload)
  }

  if (response.status === 204 || payload === "") {
    return undefined as T
  }

  return payload as T
}

export const queryKeys = {
  auth: {
    me: ["auth", "me"] as const,
  },
  workspaces: {
    detail: (slug: string) => ["workspaces", slug] as const,
  },
  members: {
    all: ["members"] as const,
  },
  invitations: {
    all: ["invitations"] as const,
  },
  teams: {
    all: ["teams"] as const,
    detail: (slug: string) => ["teams", slug] as const,
  },
  departments: {
    all: (team?: string) => ["departments", team ?? "all"] as const,
    detail: (id: string) => ["departments", "detail", id] as const,
    bySlug: (slug: string) => ["departments", "slug", slug] as const,
  },
  skills: {
    all: (filters?: ProcessListFilters) => ["skills", filters ?? {}] as const,
    detail: (slug: string) => ["skills", "detail", slug] as const,
    versions: (slug: string) => ["skills", "versions", slug] as const,
    version: (slug: string, versionNumber: number) =>
      ["skills", "versions", slug, versionNumber] as const,
    versionDiff: (slug: string, versionNumber: number) =>
      ["skills", "versions", slug, versionNumber, "diff"] as const,
    files: (slug: string, versionNumber: number) =>
      ["skills", "files", slug, versionNumber] as const,
    file: (slug: string, versionNumber: number, path: string) =>
      ["skills", "files", slug, versionNumber, path] as const,
    fileDiff: (slug: string, versionNumber: number) =>
      ["skills", "files", slug, versionNumber, "diff"] as const,
  },
  settings: {
    effective: (teamId?: string, departmentId?: string) =>
      ["settings", "effective", teamId ?? "", departmentId ?? ""] as const,
  },
  auditRules: {
    all: ["audit-rules"] as const,
  },
  stalenessAlertRules: {
    all: ["staleness-alert-rules"] as const,
  },
  apiKeys: {
    all: ["api-keys"] as const,
    roles: ["api-key-roles"] as const,
  },
  mcp: {
    connections: ["mcp", "connections"] as const,
  },
  usage: {
    events: (filters?: UsageEventFilters) => ["usage", "events", filters ?? {}] as const,
    summary: (days: number) => ["usage", "summary", days] as const,
    analytics: (days: number) => ["usage", "analytics", days] as const,
  },
  connectors: {
    all: ["connectors"] as const,
    captureStats: ["connectors", "capture-stats"] as const,
    extractionJobs: (credentialId: string) =>
      ["connectors", credentialId, "extraction-jobs"] as const,
    candidates: (credentialId: string, filters?: CandidateListFilters) =>
      ["connectors", credentialId, "candidates", filters ?? {}] as const,
    candidate: (credentialId: string, candidateId: string) =>
      ["connectors", credentialId, "candidates", candidateId] as const,
  },
}

function invalidateWorkspaceStructure(queryClient: ReturnType<typeof useQueryClient>) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.teams.all }),
    queryClient.invalidateQueries({ queryKey: ["departments"] }),
    queryClient.invalidateQueries({ queryKey: ["skills"] }),
  ])
}

export function useMe() {
  return useQuery({
    queryKey: queryKeys.auth.me,
    queryFn: () => apiFetch<MeResponse>("/auth/me"),
    retry: false,
  })
}

export function useWorkspace(slug: string) {
  return useQuery({
    queryKey: queryKeys.workspaces.detail(slug),
    queryFn: () => apiFetch<Workspace>(`/workspaces/${slug}`),
    enabled: Boolean(slug),
  })
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateWorkspaceInput) =>
      apiFetch<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async (workspace) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.auth.me }),
        queryClient.setQueryData(queryKeys.workspaces.detail(workspace.slug), workspace),
      ])
    },
  })
}

export function useWorkspaceMembers() {
  return useQuery({
    queryKey: queryKeys.members.all,
    queryFn: async () => {
      const res = await apiFetch<{ items: Member[]; count: number }>("/members")
      return res.items
    },
  })
}

export function useInviteMember() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: InviteMemberInput) =>
      apiFetch<InviteResponse>("/members", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.members.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.invitations.all }),
      ])
    },
  })
}

export function useRemoveMember() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (userId: string) =>
      apiFetch<ApiOkResponse>(`/members/${userId}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.members.all })
    },
  })
}

export function usePendingInvitations() {
  return useQuery({
    queryKey: queryKeys.invitations.all,
    queryFn: async () => {
      const res = await apiFetch<{ items: PendingInvitation[]; count: number }>("/invitations")
      return res.items
    },
  })
}

export function useCancelInvitation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ApiOkResponse>(`/invitations/${id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.invitations.all })
    },
  })
}

export function useTeams() {
  return useQuery({
    queryKey: queryKeys.teams.all,
    queryFn: async () => {
      const res = await apiFetch<{ items: Team[]; count: number }>("/teams")
      return res.items
    },
  })
}

export function useTeam(slug: string) {
  return useQuery({
    queryKey: queryKeys.teams.detail(slug),
    queryFn: () => apiFetch<TeamDetail>(`/teams/${slug}`),
    enabled: Boolean(slug),
  })
}

export function useCreateTeam() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateTeamInput) =>
      apiFetch<Team>("/teams", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.teams.all })
    },
  })
}

export function useUpdateTeam(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateTeamInput) =>
      apiFetch<Team>(`/teams/${slug}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.teams.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.teams.detail(slug) }),
      ])
    },
  })
}

export function useDeleteTeam() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (slug: string) =>
      apiFetch<ApiOkResponse>(`/teams/${slug}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await invalidateWorkspaceStructure(queryClient)
    },
  })
}

export function useDepartments(team?: string) {
  return useQuery({
    queryKey: queryKeys.departments.all(team),
    queryFn: async () => {
      const query = buildSearchParams({ team })
      const res = await apiFetch<{ items: Department[]; count: number }>(
        `/departments${query ? `?${query}` : ""}`,
      )
      return res.items
    },
  })
}

export function useDepartment(id: string) {
  return useQuery({
    queryKey: queryKeys.departments.detail(id),
    queryFn: () => apiFetch<Department>(`/departments/${id}`),
    enabled: Boolean(id),
  })
}

export function useDepartmentBySlug(slug: string) {
  const departmentsQuery = useDepartments()

  return {
    ...departmentsQuery,
    data: departmentsQuery.data?.find((department) => department.slug === slug) ?? null,
  }
}

export function useCreateDepartment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateDepartmentInput) =>
      apiFetch<Department>("/departments", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async (_department, payload) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.departments.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.departments.all(payload.team_slug) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.teams.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.teams.detail(payload.team_slug) }),
      ])
    },
  })
}

export function useUpdateDepartment(id: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateDepartmentInput) =>
      apiFetch<Department>(`/departments/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.departments.detail(id) }),
        queryClient.invalidateQueries({ queryKey: ["departments"] }),
        queryClient.invalidateQueries({ queryKey: ["teams"] }),
      ])
    },
  })
}

export function useDeleteDepartment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ApiOkResponse>(`/departments/${id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await invalidateWorkspaceStructure(queryClient)
    },
  })
}

export function useSkilles(filters?: ProcessListFilters) {
  return useQuery({
    queryKey: queryKeys.skills.all(filters),
    queryFn: () => {
      const query = buildSearchParams({
        department: filters?.department,
        team: filters?.team,
        status: filters?.status,
        search: filters?.search,
        limit: filters?.limit,
        offset: filters?.offset,
      })

      return apiFetch<PaginatedResponse<Skill>>(`/skills${query ? `?${query}` : ""}`)
    },
  })
}

export function useSkill(slug: string) {
  return useQuery({
    queryKey: queryKeys.skills.detail(slug),
    queryFn: () => apiFetch<SkillDetail>(`/skills/${slug}`),
    enabled: Boolean(slug),
  })
}

export function useCreateSkill() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateSkillInput) =>
      apiFetch<SkillDetail>("/skills", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async (skill) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["skills"] }),
        queryClient.invalidateQueries({ queryKey: ["departments"] }),
        queryClient.setQueryData(queryKeys.skills.detail(skill.slug), skill),
      ])
    },
  })
}

export function useUpdateSkill(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateSkillInput) =>
      apiFetch<SkillDetail>(`/skills/${slug}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["skills"] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.detail(slug) }),
      ])
    },
  })
}

export function useUnshareProcessFromMyTeam(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiFetch<SkillDetail>(`/skills/${slug}/shared-with/my-team`, {
        method: "DELETE",
      }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(queryKeys.skills.detail(slug), updated)
      await queryClient.invalidateQueries({ queryKey: ["skills"] })
    },
  })
}

export function useDeleteSkill() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (slug: string) =>
      apiFetch<ApiOkResponse>(`/skills/${slug}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await invalidateWorkspaceStructure(queryClient)
    },
  })
}

export function useVersions(slug: string) {
  return useQuery({
    queryKey: queryKeys.skills.versions(slug),
    queryFn: async () => {
      const res = await apiFetch<{ items: SkillVersionBrief[]; count: number }>(
        `/skills/${slug}/versions`,
      )
      return res.items
    },
    enabled: Boolean(slug),
  })
}

export function useVersion(slug: string, versionNumber: number | null) {
  return useQuery({
    queryKey: queryKeys.skills.version(slug, versionNumber ?? 0),
    queryFn: () => apiFetch<SkillVersion>(`/skills/${slug}/versions/${versionNumber}`),
    enabled: Boolean(slug) && versionNumber !== null,
  })
}

export function useVersionDiff(slug: string, versionNumber: number | null) {
  return useQuery({
    queryKey: queryKeys.skills.versionDiff(slug, versionNumber ?? 0),
    queryFn: () => apiFetch<VersionDiff>(`/skills/${slug}/versions/${versionNumber}/diff`),
    enabled: Boolean(slug) && versionNumber !== null && versionNumber > 1,
  })
}

export function useVersionFiles(slug: string, versionNumber: number | null) {
  return useQuery({
    queryKey: queryKeys.skills.files(slug, versionNumber ?? 0),
    queryFn: () => apiFetch<VersionFile[]>(`/skills/${slug}/versions/${versionNumber}/files`),
    enabled: Boolean(slug) && versionNumber !== null,
  })
}

export function useVersionFile(slug: string, versionNumber: number | null, path: string | null) {
  return useQuery({
    queryKey: queryKeys.skills.file(slug, versionNumber ?? 0, path ?? ""),
    queryFn: () =>
      apiFetch<VersionFileDetail>(
        `/skills/${slug}/versions/${versionNumber}/files/${encodeURIComponent(path ?? "")}`,
      ),
    enabled: Boolean(slug) && versionNumber !== null && Boolean(path),
  })
}

export function useFileDiff(slug: string, versionNumber: number | null) {
  return useQuery({
    queryKey: queryKeys.skills.fileDiff(slug, versionNumber ?? 0),
    queryFn: () =>
      apiFetch<{
        old_version_number: number
        new_version_number: number
        entries: FileDiffEntry[]
      }>(`/skills/${slug}/versions/${versionNumber}/file-diff`),
    enabled: Boolean(slug) && versionNumber !== null && versionNumber > 1,
  })
}

export function useCreateVersion(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateVersionInput) =>
      apiFetch<SkillVersion>(`/skills/${slug}/versions`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.versions(slug) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.detail(slug) }),
        queryClient.invalidateQueries({ queryKey: ["skills", "files", slug] }),
      ])
    },
  })
}

export function useRevertVersion(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      targetVersionNumber,
      payload,
    }: {
      targetVersionNumber: number
      payload: RevertVersionInput
    }) =>
      apiFetch<SkillVersion>(`/skills/${slug}/versions/${targetVersionNumber}/revert`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.versions(slug) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.detail(slug) }),
        queryClient.invalidateQueries({ queryKey: ["skills", "files", slug] }),
      ])
    },
  })
}

export function useUpdateVersionSummary(slug: string, versionNumber: number | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpdateVersionSummaryInput) =>
      apiFetch<SkillVersionBrief>(`/skills/${slug}/versions/${versionNumber}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.versions(slug) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.detail(slug) }),
      ])
    },
  })
}

export function usePublishSkill(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiFetch<SkillDetail>(`/skills/${slug}/publish`, {
        method: "POST",
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["skills"] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.detail(slug) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.versions(slug) }),
      ])
    },
  })
}

export function useReviewSkill(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () =>
      apiFetch<SkillDetail>(`/skills/${slug}/review`, {
        method: "POST",
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["skills"] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.skills.detail(slug) }),
      ])
    },
  })
}

export function useEffectiveSettings(teamId?: string, departmentId?: string) {
  return useQuery({
    queryKey: queryKeys.settings.effective(teamId, departmentId),
    queryFn: () => {
      const query = buildSearchParams({ team_id: teamId, department_id: departmentId })
      return apiFetch<EffectiveSettings>(`/settings${query ? `?${query}` : ""}`)
    },
  })
}

export function useUpsertSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: UpsertSettingsInput) =>
      apiFetch<unknown>("/settings", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings"] })
    },
  })
}

export function useAuditRules() {
  return useQuery({
    queryKey: queryKeys.auditRules.all,
    queryFn: async () => {
      const res = await apiFetch<{ items: ProcessAuditRule[]; count: number }>("/audit-rules")
      return res.items
    },
  })
}

export function useCreateAuditRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: { period_days: number }) =>
      apiFetch<ProcessAuditRule>("/audit-rules", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auditRules.all })
    },
  })
}

export function useDeleteAuditRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ApiOkResponse>(`/audit-rules/${id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.auditRules.all }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
      ])
    },
  })
}

export function useStalenessAlertRules() {
  return useQuery({
    queryKey: queryKeys.stalenessAlertRules.all,
    queryFn: async () => {
      const res = await apiFetch<{ items: StalenessAlertRule[]; count: number }>(
        "/staleness-alert-rules",
      )
      return res.items
    },
  })
}

export function useCreateStalenessAlertRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateStalenessAlertRuleInput) =>
      apiFetch<StalenessAlertRule>("/staleness-alert-rules", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.stalenessAlertRules.all })
    },
  })
}

export function useUpdateStalenessAlertRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, ...payload }: UpdateStalenessAlertRuleInput & { id: string }) =>
      apiFetch<StalenessAlertRule>(`/staleness-alert-rules/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.stalenessAlertRules.all }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
      ])
    },
  })
}

export function useDeleteStalenessAlertRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ApiOkResponse>(`/staleness-alert-rules/${id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.stalenessAlertRules.all }),
        queryClient.invalidateQueries({ queryKey: ["settings"] }),
      ])
    },
  })
}

export function useApiKeyRoles() {
  return useQuery({
    queryKey: queryKeys.apiKeys.roles,
    queryFn: () => apiFetch<ApiKeyRoleOption[]>("/api-key-roles"),
    staleTime: Infinity,
  })
}

export function useApiKeys() {
  return useQuery({
    queryKey: queryKeys.apiKeys.all,
    queryFn: async () => {
      const res = await apiFetch<{ items: ApiKey[]; count: number }>("/api-keys")
      return res.items
    },
  })
}

export function useCreateApiKey() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateApiKeyInput) =>
      apiFetch<CreatedApiKey>("/api-keys", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
    },
  })
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ApiOkResponse>(`/api-keys/${id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
    },
  })
}

export function useMcpConnections() {
  return useQuery({
    queryKey: queryKeys.mcp.connections,
    queryFn: async () => {
      const res = await apiFetch<{ items: McpConnection[]; count: number }>("/mcp/connections")
      return res.items
    },
  })
}

export function useRevokeMcpConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ApiOkResponse>(`/mcp/connections/${id}`, {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.mcp.connections })
    },
  })
}

export function useUpdateMcpConnectionScope() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, ...payload }: McpConnectionScopeInput & { id: string }) =>
      apiFetch<McpConnectionScope>(`/mcp/connections/${id}/scope`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.mcp.connections })
    },
  })
}

export function useUsageEvents(filters?: UsageEventFilters) {
  return useQuery({
    queryKey: queryKeys.usage.events(filters),
    queryFn: () => {
      const query = buildSearchParams({
        skill: filters?.skill,
        client_type: filters?.client_type,
        days: filters?.days ?? 30,
        limit: filters?.limit,
        offset: filters?.offset,
      })

      return apiFetch<PaginatedResponse<UsageEvent>>(`/usage${query ? `?${query}` : ""}`)
    },
  })
}

export function useUsageSummary(days = 30) {
  return useQuery({
    queryKey: queryKeys.usage.summary(days),
    queryFn: async () => {
      const res = await apiFetch<{ items: SkillUsageSummary[]; count: number }>(
        `/usage/summary?days=${days}`,
      )
      return res.items
    },
  })
}

export function useUsageAnalytics(days = 30) {
  return useQuery({
    queryKey: queryKeys.usage.analytics(days),
    queryFn: () => apiFetch<UsageAnalytics>(`/usage/analytics?days=${days}`),
  })
}

export function useCaptureFunnel() {
  return useQuery({
    queryKey: queryKeys.connectors.captureStats,
    queryFn: () => apiFetch<CaptureFunnel>("/connectors/capture-stats"),
  })
}

export function useConnectors() {
  return useQuery({
    queryKey: queryKeys.connectors.all,
    queryFn: () => apiFetch<ConnectorCredential[]>("/connectors/"),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      const hasSyncRunning = data.some(
        (c) => c.last_sync_job?.status === "pending" || c.last_sync_job?.status === "running",
      )
      return hasSyncRunning ? 3000 : false
    },
  })
}

export function useDisconnectConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiFetch<ApiOkResponse>(`/connectors/${id}`, { method: "DELETE" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.connectors.all })
    },
  })
}

export function useTriggerSync() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<{ job_id: string }>(`/connectors/${id}/sync`, { method: "POST" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.connectors.all })
    },
  })
}

export function useTriggerExtraction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credentialId: string) =>
      apiFetch<{ job_id: string }>(`/connectors/${credentialId}/extract`, { method: "POST" }),
    onSuccess: async (_data, credentialId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.connectors.all }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.connectors.extractionJobs(credentialId),
        }),
      ])
    },
  })
}

export function useExtractionJobs(credentialId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.connectors.extractionJobs(credentialId),
    queryFn: () => apiFetch<ExtractionJob[]>(`/connectors/${credentialId}/extraction-jobs?limit=5`),
    enabled: Boolean(credentialId) && enabled,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      const isRunning = data.some((j) => j.status === "pending" || j.status === "running")
      return isRunning ? 2000 : false
    },
  })
}

export function useCandidates(credentialId: string, filters?: CandidateListFilters) {
  return useQuery({
    queryKey: queryKeys.connectors.candidates(credentialId, filters),
    queryFn: () => {
      const query = buildSearchParams({
        status: filters?.status ?? "pending",
        automation_tier: filters?.automation_tier,
        search: filters?.search,
        cursor: filters?.cursor,
        limit: filters?.limit ?? 50,
      })
      return apiFetch<CandidateListResponse>(
        `/connectors/${credentialId}/candidates${query ? `?${query}` : ""}`,
      )
    },
    enabled: Boolean(credentialId),
  })
}

export function useCandidate(credentialId: string, candidateId: string) {
  return useQuery({
    queryKey: queryKeys.connectors.candidate(credentialId, candidateId),
    queryFn: () =>
      apiFetch<CaptureCandidate>(`/connectors/${credentialId}/candidates/${candidateId}`),
    enabled: Boolean(credentialId) && Boolean(candidateId),
  })
}

export function usePromoteCandidate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      credentialId,
      candidateId,
      payload,
    }: {
      credentialId: string
      candidateId: string
      payload: PromoteCandidateInput
    }) =>
      apiFetch<{ skill_slug: string }>(
        `/connectors/${credentialId}/candidates/${candidateId}/promote`,
        { method: "POST", body: JSON.stringify(payload) },
      ),
    onSuccess: async (_data, { credentialId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.connectors.candidates(credentialId),
        }),
        queryClient.invalidateQueries({ queryKey: ["skills"] }),
      ])
    },
  })
}

export function useDismissCandidate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ credentialId, candidateId }: { credentialId: string; candidateId: string }) =>
      apiFetch<{ ok: true }>(`/connectors/${credentialId}/candidates/${candidateId}/dismiss`, {
        method: "POST",
      }),
    onSuccess: async (_data, { credentialId }) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.connectors.candidates(credentialId),
      })
    },
  })
}
