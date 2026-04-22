export type WorkspaceRole = "admin" | "team_manager" | "member"
export type ProcessStatus = "draft" | "published"
export type ProcessVisibility = "department" | "team" | "workspace"
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
  process_count: number
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
  size_bytes: number
}

export interface VersionFileDetail extends VersionFile {
  content: string
}

export interface VersionFileInput {
  path: string
  content: string
  file_type: string
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

export interface ProcessVersion {
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

export interface ProcessVersionBrief {
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
  old_version: ProcessVersionBrief
  new_version: ProcessVersionBrief
  hunks: DiffHunk[]
  stats: DiffStats
  file_diff: FileDiffEntry[]
}

export interface Process {
  id: string
  title: string
  slug: string
  description: string
  status: ProcessStatus
  visibility: ProcessVisibility
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
  created_at: string
  updated_at: string
}

export interface ProcessDetail {
  id: string
  title: string
  slug: string
  description: string
  status: ProcessStatus
  visibility: ProcessVisibility
  shared_with_ids: string[]
  is_shared_with_requester_team: boolean
  department_slug: string
  department_name: string
  team_slug: string
  team_name: string
  owner: User | null
  current_version: ProcessVersion | null
  last_reviewed_at: string | null
  needs_audit: boolean
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
  notify_process_owner: boolean
  created_at: string
}

export interface StalenessAlertRuleBrief {
  id: string
  period_days: number
  notify_admins: boolean
  notify_team_managers: boolean
  notify_process_owner: boolean
}

export interface CreateStalenessAlertRuleInput {
  period_days: number
  notify_admins: boolean
  notify_team_managers: boolean
  notify_process_owner: boolean
}

export interface UpdateStalenessAlertRuleInput {
  period_days?: number
  notify_admins?: boolean
  notify_team_managers?: boolean
  notify_process_owner?: boolean
}

export interface EffectiveSettings {
  require_review_before_publish: boolean | null
  enable_version_history: boolean | null
  enable_api_access: boolean | null
  require_change_summary: boolean | null
  allow_agent_process_updates: boolean | null
  process_audit: ProcessAuditRuleBrief | null
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
  allow_agent_process_updates?: boolean | null
  process_audit_id?: string | null
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

export interface UsageEvent {
  id: string
  process_title: string
  process_slug: string
  version_number: number
  client_id: string
  client_type: string
  tool_name: string
  called_at: string
}

export interface ProcessUsageSummary {
  process_slug: string
  process_title: string
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

export interface CreateProcessInput {
  department_id: string
  title: string
  slug: string
  description?: string
  owner_id?: string | null
  visibility?: ProcessVisibility
  shared_with_ids?: string[]
}

export interface UpdateProcessInput {
  title?: string
  description?: string
  owner_id?: string | null
  visibility?: ProcessVisibility
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
  process?: string
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
  process_slug: string
  process_title: string
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
  process_slug: string
  process_title: string
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
  promoted_process_slug: string | null
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

export interface ProcessFrontmatter {
  name: string
  description: string
  tags: string[]
  [key: string]: unknown
}
