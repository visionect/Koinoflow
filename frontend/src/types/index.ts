export type WorkspaceRole = "admin" | "team_manager" | "member"
export type ProcessStatus = "draft" | "published"
export type SkillVisibility = "department" | "team" | "workspace"
export type DiscoveryEmbeddingStatus = "not_applicable" | "pending" | "ready"
export type ThemeMode = "light" | "dark" | "system"

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
}

export interface Workspace {
  id: string
  name: string
  slug: string
  created_at: string
}

export interface Member extends User {
  role: string
  team_id: string | null
  team_name: string | null
  department_ids: string[]
}

export interface PendingInvitation {
  id: string
  email: string
  role: string
  team_name: string | null
  department_names: string[]
  invited_by_email: string | null
  status: "pending" | "accepted" | "expired" | "cancelled"
  created_at: string
  expires_at: string
}

export interface InviteMemberInput {
  email: string
  role: string
  team_id?: string | null
  department_ids?: string[]
}

export interface InviteResponse {
  detail: string
}

export interface MeResponse {
  user: User | null
  workspace_slug: string | null
  role: WorkspaceRole | null
  subscription_status: string | null
  trial_end: string | null
  feature_flags: string[]
  billing_enabled: boolean
}

export interface Team {
  id: string
  name: string
  slug: string
  department_count: number
  created_at: string
}

export interface Department {
  id: string
  name: string
  slug: string
  team_slug: string
  team_name: string
  owner: User | null
  skill_count: number
  created_at: string
}

export interface TeamDetail {
  id: string
  name: string
  slug: string
  departments: Department[]
  created_at: string
}

export interface VersionFile {
  id: string
  path: string
  file_type: string
  mime_type: string
  encoding: string
  size_bytes: number
}

export interface VersionFileDetail extends VersionFile {
  content: string | null
  content_base64: string | null
}

export interface VersionFileInput {
  path: string
  content?: string | null
  content_base64?: string | null
  file_type: string
  mime_type?: string | null
  encoding?: string | null
  size_bytes?: number
}

export interface FileDiffEntry {
  path: string
  status: "added" | "modified" | "deleted"
  old_size: number | null
  new_size: number | null
  hunks?: DiffHunk[]
}

export type RiskLevel = "low" | "medium" | "high" | "critical"

export interface KoinoflowMetadata {
  retrieval_keywords: string[]
  risk_level: RiskLevel | null
  requires_human_approval: boolean
  prerequisites: string[]
  audience: string[]
}

export const EMPTY_KOINOFLOW_METADATA: KoinoflowMetadata = {
  retrieval_keywords: [],
  risk_level: null,
  requires_human_approval: false,
  prerequisites: [],
  audience: [],
}

export interface SkillVersion {
  id: string
  version_number: number
  content_md: string
  frontmatter_yaml: string
  change_summary: string
  authored_by: User | null
  created_at: string
  files: VersionFile[]
  koinoflow_metadata: KoinoflowMetadata
  reverted_from_version_number: number | null
}

export interface SkillVersionBrief {
  id: string
  version_number: number
  change_summary: string
  authored_by: User | null
  created_at: string
  reverted_from_version_number: number | null
}

export interface RevertVersionInput {
  change_summary?: string
}

export interface DiffHunk {
  old_start: number
  old_count: number
  new_start: number
  new_count: number
  lines: string[]
}

export interface DiffStats {
  additions: number
  deletions: number
  total_hunks: number
}

export interface VersionDiff {
  old_version: SkillVersionBrief
  new_version: SkillVersionBrief
  hunks: DiffHunk[]
  stats: DiffStats
  file_diff: FileDiffEntry[]
}

export interface Skill {
  id: string
  title: string
  slug: string
  description: string
  status: ProcessStatus
  visibility: SkillVisibility
  shared_with_ids: string[]
  department_slug: string
  department_name: string
  team_slug: string
  team_name: string
  owner: User | null
  current_version_number: number | null
  last_reviewed_at: string | null
  needs_audit: boolean
  risk_level: RiskLevel | null
  retrieval_keywords: string[]
  requires_human_approval: boolean
  discovery_embedding_status: DiscoveryEmbeddingStatus
  created_at: string
  updated_at: string
}

export interface SkillDetail {
  id: string
  title: string
  slug: string
  description: string
  status: ProcessStatus
  visibility: SkillVisibility
  shared_with_ids: string[]
  is_shared_with_requester_team: boolean
  department_slug: string
  department_name: string
  team_slug: string
  team_name: string
  system_kind: string
  owner: User | null
  current_version: SkillVersion | null
  last_reviewed_at: string | null
  needs_audit: boolean
  discovery_embedding_status: DiscoveryEmbeddingStatus
  created_at: string
  updated_at: string
}

export interface ProcessAuditRule {
  id: string
  period_days: number
  created_at: string
}

export interface ProcessAuditRuleBrief {
  id: string
  period_days: number
}

export interface StalenessAlertRule {
  id: string
  period_days: number
  notify_admins: boolean
  notify_team_managers: boolean
  notify_skill_owner: boolean
  created_at: string
}

export interface StalenessAlertRuleBrief {
  id: string
  period_days: number
  notify_admins: boolean
  notify_team_managers: boolean
  notify_skill_owner: boolean
}

export interface CreateStalenessAlertRuleInput {
  period_days: number
  notify_admins: boolean
  notify_team_managers: boolean
  notify_skill_owner: boolean
}

export interface UpdateStalenessAlertRuleInput {
  period_days?: number
  notify_admins?: boolean
  notify_team_managers?: boolean
  notify_skill_owner?: boolean
}

export interface EffectiveSettings {
  require_review_before_publish: boolean | null
  enable_version_history: boolean | null
  enable_api_access: boolean | null
  require_change_summary: boolean | null
  allow_agent_skill_updates: boolean | null
  skill_audit: ProcessAuditRuleBrief | null
  staleness_alert: StalenessAlertRuleBrief | null
}

export interface UpsertSettingsInput {
  workspace_id: string
  team_id?: string | null
  department_id?: string | null
  require_review_before_publish?: boolean | null
  enable_version_history?: boolean | null
  enable_api_access?: boolean | null
  require_change_summary?: boolean | null
  allow_agent_skill_updates?: boolean | null
  skill_audit_id?: string | null
  staleness_alert_id?: string | null
}

export interface UpdateVersionSummaryInput {
  change_summary: string
}

export type ApiKeyRole = "admin" | "team_manager" | "member"

export interface ApiKeyRoleOption {
  value: ApiKeyRole
  label: string
  description: string
  requires_team: boolean
  requires_departments: boolean
}

export interface ApiKey {
  id: string
  label: string
  key_prefix: string
  is_active: boolean
  expires_at: string | null
  created_at: string
  created_by: User | null
  role: ApiKeyRole
  team_id: string | null
  team_name: string | null
  department_ids: string[]
}

export interface CreatedApiKey {
  id: string
  label: string
  key_prefix: string
  raw_key: string
  expires_at: string | null
  created_at: string
  role: ApiKeyRole
}

export interface Agent {
  id: string
  name: string
  description: string
  token_prefix: string
  masked_token: string
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export interface CreatedAgent extends Agent {
  token: string
}

export interface CreateAgentInput {
  name: string
  description?: string
}

export interface UpdateAgentInput {
  name?: string
  description?: string
  is_active?: boolean
}

export interface ImportAgentSkillInput {
  title: string
  slug: string
  description?: string
  content_md: string
  frontmatter_yaml?: string
  files?: VersionFileInput[]
  deploy_to_all: boolean
  agent_ids: string[]
}

export interface CreateAgentSkillInput {
  title: string
  slug: string
  description?: string
  deploy_to_all: boolean
  agent_ids: string[]
}

export interface AgentSkill {
  id: string
  title: string
  slug: string
  description: string
  deploy_to_all: boolean
  agent_ids: string[]
  created_at: string
  updated_at: string
}

export interface AgentUsageEvent extends UsageEvent {
  agent_id: string | null
  agent_name: string | null
}

export interface AgentAnalytics {
  total_calls: number
  active_agents: number
  skills_touched: number
  by_agent: Array<{ agent_id: string | null; agent_name: string; count: number }>
  by_skill: Array<{ skill_id: string; skill_slug: string; skill_title: string; count: number }>
}

export interface UsageEvent {
  id: string
  skill_title: string
  skill_slug: string
  version_number: number
  client_id: string
  client_type: string
  tool_name: string
  called_at: string
}

export interface SkillUsageSummary {
  skill_slug: string
  skill_title: string
  total_calls: number
  last_called_at: string | null
  unique_clients: number
  client_type_breakdown: Record<string, number>
}

export interface PaginatedResponse<T> {
  items: T[]
  count: number
}

export interface ApiOkResponse {
  ok: true
}

export interface CreateWorkspaceInput {
  name: string
  slug: string
}

export interface CreateTeamInput {
  name: string
  slug: string
}

export interface UpdateTeamInput {
  name?: string
}

export interface CreateDepartmentInput {
  team_slug: string
  name: string
  slug: string
  owner_id?: string | null
}

export interface UpdateDepartmentInput {
  name?: string
  owner_id?: string | null
}

export interface CreateSkillInput {
  department_id: string
  title: string
  slug: string
  description?: string
  owner_id?: string | null
  visibility?: SkillVisibility
  shared_with_ids?: string[]
}

export interface UpdateSkillInput {
  title?: string
  description?: string
  owner_id?: string | null
  visibility?: SkillVisibility
  shared_with_ids?: string[]
}

export interface CreateVersionInput {
  content_md: string
  frontmatter_yaml?: string
  change_summary?: string
  files?: VersionFileInput[]
  koinoflow_metadata?: KoinoflowMetadata
}

export interface CreateApiKeyInput {
  label: string
  expires_at?: string | null
  role?: ApiKeyRole
  team_id?: string | null
  department_ids?: string[]
}

export interface ProcessListFilters {
  department?: string
  team?: string
  status?: ProcessStatus
  search?: string
  limit?: number
  offset?: number
}

export interface UsageEventFilters {
  skill?: string
  client_type?: string
  days?: number
  limit?: number
  offset?: number
}

export interface CoverageData {
  consumed_count: number
  published_count: number
  percentage: number
}

export interface StaleReliedOn {
  skill_slug: string
  skill_title: string
  days_since_review: number
  call_count: number
  owner_email: string | null
  owner_first_name: string | null
}

export interface DailyTrend {
  date: string
  count: number
}

export interface ClientBreakdown {
  client_type: string
  count: number
  percentage: number
}

export interface UsageKpis {
  total_calls: number
  total_calls_previous: number
  active_clients: number
  processes_touched: number
  peak_day_date: string | null
  peak_day_count: number
}

export interface CoverageGap {
  skill_slug: string
  skill_title: string
  owner_first_name: string | null
  days_since_published: number
}

export interface ToolBreakdown {
  tool_name: string
  count: number
  percentage: number
}

export interface UsageAnalytics {
  coverage: CoverageData
  stale_but_relied_on: StaleReliedOn[]
  daily_trend: DailyTrend[]
  client_breakdown: ClientBreakdown[]
  kpis: UsageKpis
  coverage_gap: CoverageGap[]
  tool_breakdown: ToolBreakdown[]
}

export interface CaptureFunnel {
  synced_pages: number
  candidates_extracted: number
  candidates_promoted: number
  has_connector: boolean
}

export type ConnectorStatus = "active" | "expired" | "error" | "disconnected"
export type AutomationTier = "ready" | "needs_integration" | "manual_only"
export type CandidateStatus = "pending" | "promoted" | "dismissed"

export interface SyncJobBrief {
  status: string
  pages_updated: number
  finished_at: string | null
}

export interface ExtractionJobBrief {
  id: string
  status: string
  pages_scored: number
  pages_extracted: number
  candidates_created: number
  started_at: string | null
  finished_at: string | null
}

export interface ExtractionJob extends ExtractionJobBrief {
  error_message: string
  created_at: string
}

export interface ConnectorCredential {
  id: string
  provider: string
  site_url: string
  status: ConnectorStatus
  connected_by_email: string | null
  last_sync_job: SyncJobBrief | null
  last_extraction_job: ExtractionJobBrief | null
  synced_pages_count: number
  changed_pages_count: number
  created_at: string
}

export interface IntegrationNeed {
  system: string
  steps_affected: string[]
  reason: string
  access_required: string
  api_endpoint?: string | null
  mcp_server?: string | null
  documentation_url?: string | null
  auth_method?: string | null
}

export interface CandidateSourceBrief {
  id: string
  page_title: string
  page_external_url: string
}

export interface CaptureCandidate {
  id: string
  title: string
  slug: string
  description: string
  probability_score: number
  automation_tier: AutomationTier
  automation_reasoning: string
  integration_needs: IntegrationNeed[]
  status: CandidateStatus
  promoted_skill_slug: string | null
  sources: CandidateSourceBrief[] | null
  created_at: string
}

export interface CandidateListResponse {
  items: CaptureCandidate[]
  next_cursor: string | null
  total: number
}

export interface CandidateListFilters {
  status?: string
  automation_tier?: string
  search?: string
  cursor?: string
  limit?: number
}

export interface PromoteCandidateInput {
  department_id: string
  owner_id?: string | null
  title?: string | null
  description?: string | null
}

export interface McpConnectionUser {
  id: string
  email: string
}

export type McpScopeType = "workspace" | "team" | "department"

export interface McpConnectionScopeDepartment {
  id: string
  name: string
  team_name: string
}

export interface McpConnectionScope {
  scope_type: McpScopeType
  team_id: string | null
  team_name: string | null
  department_ids: string[]
  departments: McpConnectionScopeDepartment[]
}

export interface McpConnection {
  id: string
  client_name: string
  user: McpConnectionUser | null
  scopes: string
  created_at: string
  last_used_at: string | null
  is_active: boolean
  connection_scope: McpConnectionScope | null
}

export interface McpConnectionScopeInput {
  scope_type: McpScopeType
  team_id?: string | null
  department_ids?: string[]
}

export interface SkillFrontmatter {
  name: string
  description: string
  tags: string[]
  [key: string]: unknown
}
