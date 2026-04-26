import * as React from "react"

import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  Clock3Icon,
  DownloadIcon,
  GlobeIcon,
  HistoryIcon,
  MoreHorizontalIcon,
  PencilIcon,
  RocketIcon,
  SaveIcon,
  Trash2Icon,
  UploadIcon,
  UserMinusIcon,
  XIcon,
} from "lucide-react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useDeleteSkill,
  useDepartments,
  useEffectiveSettings,
  useSkill,
  usePublishSkill,
  useReviewSkill,
  useSkills,
  useUnshareSkillFromMyTeam,
  useUpdateSkill,
  useUpdateVersionSummary,
  useVersion,
  useVersionFile,
  useVersionFiles,
  useVersions,
  useCreateVersion,
  useWorkspaceMembers,
} from "@/api/client"
import { FileEditor } from "@/components/editor/FileEditor"
import { FrontmatterForm } from "@/components/editor/FrontmatterForm"
import { KoinoflowMetadataForm } from "@/components/editor/KoinoflowMetadataForm"
import { MarkdownEditor } from "@/components/editor/MarkdownEditor"
import { DiscoveryEmbeddingStatusBadge } from "@/components/skills/DiscoveryEmbeddingStatusBadge"
import { FileTreeBrowser } from "@/components/skills/FileTreeBrowser"
import { KoinoflowMetadataStrip } from "@/components/skills/KoinoflowMetadataStrip"
import { SkillMetadataPanel } from "@/components/skills/SkillMetadataPanel"
import { VersionTimeline } from "@/components/skills/VersionTimeline"
import { ScopeDialog } from "@/components/skills/ScopeDialog"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { ErrorState } from "@/components/shared/ErrorState"
import { MarkdownContent } from "@/components/shared/MarkdownContent"
import { PageHeader } from "@/components/shared/PageHeader"
import { StatusBadge } from "@/components/shared/StatusBadge"
import { useAuth } from "@/hooks/useAuth"
import { useSkillImport } from "@/hooks/use-skill-import"
import { buildWorkspacePath, formatRelativeDate, getDisplayName } from "@/lib/format"
import { parseFrontmatter, serializeFrontmatter } from "@/lib/frontmatter"
import { apiFetch } from "@/api/client"
import {
  EMPTY_KOINOFLOW_METADATA,
  type KoinoflowMetadata,
  type SkillFrontmatter,
  type VersionFile,
  type VersionFileDetail,
  type VersionFileInput,
} from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"

type SavedSnapshot = {
  markdown: string
  frontmatterYaml: string
  koinoflowMetadataJson: string
}

function normalizeKoinoflowMetadata(raw: unknown): KoinoflowMetadata {
  const value = (raw ?? {}) as Partial<KoinoflowMetadata>
  const stringArray = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
  const validRisk = ["low", "medium", "high", "critical"] as const
  type Risk = (typeof validRisk)[number]
  const risk =
    typeof value.risk_level === "string" &&
    (validRisk as readonly string[]).includes(value.risk_level)
      ? (value.risk_level as Risk)
      : null

  return {
    retrieval_keywords: stringArray(value.retrieval_keywords),
    risk_level: risk,
    requires_human_approval: value.requires_human_approval === true,
    prerequisites: stringArray(value.prerequisites),
    audience: stringArray(value.audience),
  }
}

function koinoflowMetadataToJson(metadata: KoinoflowMetadata): string {
  return JSON.stringify({
    retrieval_keywords: metadata.retrieval_keywords,
    risk_level: metadata.risk_level,
    requires_human_approval: metadata.requires_human_approval,
    prerequisites: metadata.prerequisites,
    audience: metadata.audience,
  })
}

function resetFileEditorState(
  files: VersionFile[] | undefined,
  setEditFileMetas: React.Dispatch<React.SetStateAction<VersionFile[]>>,
  setEditFileContents: React.Dispatch<React.SetStateAction<Record<string, string>>>,
  setEditFilePayloads: React.Dispatch<React.SetStateAction<Record<string, VersionFileInput>>>,
  setFilesModified: React.Dispatch<React.SetStateAction<boolean>>,
  setSelectedFilePath: React.Dispatch<React.SetStateAction<string | null>>,
) {
  setEditFileMetas(files ?? [])
  setEditFileContents({})
  setEditFilePayloads({})
  setFilesModified(false)
  setSelectedFilePath(null)
}

export function SkillViewPage() {
  const navigate = useNavigate()
  const { workspace, skillSlug } = useParams<{ workspace: string; skillSlug: string }>()
  const { user, isAdmin, isEditor } = useAuth()

  const skillQuery = useSkill(skillSlug ?? "")
  const canWrite = skillQuery.data?.visibility === "workspace" ? isAdmin : isEditor
  const versionsQuery = useVersions(skillSlug ?? "")
  const membersQuery = useWorkspaceMembers()
  const updateSkill = useUpdateSkill(skillSlug ?? "")
  const publishSkill = usePublishSkill(skillSlug ?? "")
  const reviewSkill = useReviewSkill(skillSlug ?? "")
  const deleteSkill = useDeleteSkill()
  const unshareFromMyTeam = useUnshareSkillFromMyTeam(skillSlug ?? "")
  const createVersion = useCreateVersion(skillSlug ?? "")
  const updateVersionSummary = useUpdateVersionSummary(
    skillSlug ?? "",
    versionsQuery.data?.[0]?.version_number ?? null,
  )

  const latestVersionNumber = versionsQuery.data?.[0]?.version_number ?? null
  const publishedVersionNumber = skillQuery.data?.current_version?.version_number ?? null
  const needsLatestDraft =
    latestVersionNumber !== null && latestVersionNumber !== publishedVersionNumber

  const latestVersionQuery = useVersion(
    skillSlug ?? "",
    needsLatestDraft ? latestVersionNumber : null,
  )

  const departmentLookupQuery = useDepartments()
  const department = departmentLookupQuery.data?.find(
    (item) =>
      item.slug === skillQuery.data?.department_slug &&
      item.team_slug === skillQuery.data?.team_slug,
  )
  const sharedDepartments = React.useMemo(() => {
    if (!departmentLookupQuery.data || !skillQuery.data?.shared_with_ids?.length) return []
    const ids = new Set(skillQuery.data.shared_with_ids)
    return departmentLookupQuery.data.filter((d) => ids.has(d.id))
  }, [departmentLookupQuery.data, skillQuery.data?.shared_with_ids])
  const allDepartments = React.useMemo(() => {
    const result = department ? [department] : []
    return [...result, ...sharedDepartments]
  }, [department, sharedDepartments])

  const settingsQuery = useEffectiveSettings()
  const requireChangeSummary = settingsQuery.data?.require_change_summary === true

  const isTeamManager = isEditor && !isAdmin
  const discoveryEmbeddingStatus = skillQuery.data?.discovery_embedding_status
  const refetchSkill = skillQuery.refetch

  React.useEffect(() => {
    if (discoveryEmbeddingStatus !== "pending") {
      return
    }

    const intervalId = window.setInterval(() => {
      void refetchSkill()
    }, 4000)

    return () => window.clearInterval(intervalId)
  }, [discoveryEmbeddingStatus, refetchSkill])

  const [isEditing, setIsEditing] = React.useState(false)
  const [metadataOpen, setMetadataOpen] = React.useState(false)
  const [scopeOpen, setScopeOpen] = React.useState(false)
  const [unshareOpen, setUnshareOpen] = React.useState(false)
  const [publishOpen, setPublishOpen] = React.useState(false)
  const [publishSummary, setPublishSummary] = React.useState("")
  const [deleteOpen, setDeleteOpen] = React.useState(false)

  const [title, setTitle] = React.useState("")
  const [description, setDescription] = React.useState("")
  const [ownerId, setOwnerId] = React.useState("unassigned")

  const [frontmatter, setFrontmatter] = React.useState<SkillFrontmatter>({
    name: "",
    description: "",
    tags: [],
  })
  const [markdown, setMarkdown] = React.useState("")
  const [koinoflowMetadata, setKoinoflowMetadata] = React.useState<KoinoflowMetadata>({
    ...EMPTY_KOINOFLOW_METADATA,
  })

  const allSkillsQuery = useSkills({ limit: 200 })
  const prerequisiteSuggestions = React.useMemo(
    () =>
      (allSkillsQuery.data?.items ?? [])
        .map((p) => p.slug)
        .filter((slug) => slug !== skillSlug),
    [allSkillsQuery.data, skillSlug],
  )

  const { fileInput: importFileInput, openFilePicker: openImportPicker } = useSkillImport(
    (data) => {
      setFrontmatter(data.frontmatter)
      setMarkdown(data.contentMd)
      setKoinoflowMetadata(data.koinoflowMetadata)
      if (data.supportFiles.length > 0) {
        setEditFileMetas(
          data.supportFiles.map((f, i) => ({
            id: `import-${i}`,
            path: f.path,
            file_type: f.file_type,
            mime_type: f.mime_type ?? "application/octet-stream",
            encoding: f.encoding ?? (f.content_base64 ? "base64" : "utf-8"),
            size_bytes:
              f.size_bytes ??
              (f.content !== undefined && f.content !== null ? new Blob([f.content]).size : 0),
          })),
        )
        const contents: Record<string, string> = {}
        const payloads: Record<string, VersionFileInput> = {}
        for (const f of data.supportFiles) {
          contents[f.path] = f.content ?? ""
          payloads[f.path] = f
        }
        setEditFileContents(contents)
        setEditFilePayloads(payloads)
        setFilesModified(true)
      }
      setIsEditing(true)
      toast.success("Skill imported from file")
    },
  )

  const [changeSummary, setChangeSummary] = React.useState("")
  const [savedSnapshot, setSavedSnapshot] = React.useState<SavedSnapshot | null>(null)
  const [initializedVersion, setInitializedVersion] = React.useState<number | null>(null)

  // File state for support files
  const [editFileMetas, setEditFileMetas] = React.useState<VersionFile[]>([])
  const [editFileContents, setEditFileContents] = React.useState<Record<string, string>>({})
  const [editFilePayloads, setEditFilePayloads] = React.useState<Record<string, VersionFileInput>>(
    {},
  )
  const [filesModified, setFilesModified] = React.useState(false)
  const [selectedFilePath, setSelectedFilePath] = React.useState<string | null>(null)
  const [activeTab, setActiveTab] = React.useState<"skill" | "files">("skill")

  const hasUnpublishedDraft =
    latestVersionNumber !== null &&
    latestVersionNumber > (skillQuery.data?.current_version?.version_number ?? 0)
  const displayVersion = hasUnpublishedDraft
    ? (latestVersionQuery.data ?? skillQuery.data?.current_version ?? null)
    : (skillQuery.data?.current_version ?? latestVersionQuery.data ?? null)
  const isViewingDraft =
    displayVersion !== null &&
    displayVersion.version_number !== skillQuery.data?.current_version?.version_number

  const viewVersionNumber = displayVersion?.version_number ?? null
  const viewFilesQuery = useVersionFiles(skillSlug ?? "", viewVersionNumber)
  // New files added locally have an empty id — they don't exist on the
  // server yet, so don't try to fetch them (would 404 as "File not found").
  const selectedFileIsLocalOnly =
    selectedFilePath !== null && editFileMetas.some((f) => f.path === selectedFilePath && !f.id)
  const editingFileQuery = useVersionFile(
    skillSlug ?? "",
    viewVersionNumber,
    isEditing && !selectedFileIsLocalOnly ? selectedFilePath : null,
  )
  const viewingFileQuery = useVersionFile(
    skillSlug ?? "",
    viewVersionNumber,
    !isEditing ? selectedFilePath : null,
  )

  React.useEffect(() => {
    if (skillQuery.data) {
      setTitle(skillQuery.data.title)
      setDescription(skillQuery.data.description)
      setOwnerId(skillQuery.data.owner?.id ?? "unassigned")
    }
  }, [skillQuery.data])

  const initialVersion = latestVersionQuery.data ?? skillQuery.data?.current_version ?? null
  const hasNoVersions = versionsQuery.data !== undefined && versionsQuery.data.length === 0

  React.useEffect(() => {
    if (!skillQuery.data) {
      return
    }

    if (initialVersion) {
      if (initializedVersion === initialVersion.version_number) {
        return
      }

      const nextFrontmatter = parseFrontmatter(initialVersion.frontmatter_yaml, {
        name: skillQuery.data.slug,
        description: skillQuery.data.description,
        tags: [],
      })
      const nextMetadata = normalizeKoinoflowMetadata(initialVersion.koinoflow_metadata)

      const nextSnapshot: SavedSnapshot = {
        markdown: initialVersion.content_md,
        frontmatterYaml: serializeFrontmatter(nextFrontmatter),
        koinoflowMetadataJson: koinoflowMetadataToJson(nextMetadata),
      }

      setFrontmatter(nextFrontmatter)
      setMarkdown(initialVersion.content_md)
      setKoinoflowMetadata(nextMetadata)
      setChangeSummary("")
      setSavedSnapshot(nextSnapshot)
      setInitializedVersion(initialVersion.version_number)
    } else if (hasNoVersions && initializedVersion !== 0) {
      const scaffoldFrontmatter: SkillFrontmatter = {
        name: skillQuery.data.slug,
        description: skillQuery.data.description,
        tags: [],
      }
      const scaffoldMetadata: KoinoflowMetadata = { ...EMPTY_KOINOFLOW_METADATA }
      const scaffoldMd = `# ${skillQuery.data.title}\n\nDescribe this skill, prerequisites, and critical steps here.`
      const scaffoldYaml = serializeFrontmatter(scaffoldFrontmatter)

      setFrontmatter(scaffoldFrontmatter)
      setMarkdown(scaffoldMd)
      setKoinoflowMetadata(scaffoldMetadata)
      setChangeSummary("")
      setSavedSnapshot({
        markdown: scaffoldMd,
        frontmatterYaml: scaffoldYaml,
        koinoflowMetadataJson: koinoflowMetadataToJson(scaffoldMetadata),
      })
      setInitializedVersion(0)
    }
  }, [initialVersion, initializedVersion, skillQuery.data, hasNoVersions])

  React.useEffect(() => {
    if (displayVersion) {
      resetFileEditorState(
        displayVersion.files,
        setEditFileMetas,
        setEditFileContents,
        setEditFilePayloads,
        setFilesModified,
        setSelectedFilePath,
      )
    }
  }, [displayVersion?.version_number]) // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (editingFileQuery.data && selectedFilePath && isEditing) {
      setEditFileContents((prev) => ({
        ...prev,
        [selectedFilePath]: editingFileQuery.data!.content ?? "",
      }))
      setEditFilePayloads((prev) => ({
        ...prev,
        [selectedFilePath]: {
          path: editingFileQuery.data!.path,
          content: editingFileQuery.data!.content,
          content_base64: editingFileQuery.data!.content_base64,
          file_type: editingFileQuery.data!.file_type,
          mime_type: editingFileQuery.data!.mime_type,
          encoding: editingFileQuery.data!.encoding,
          size_bytes: editingFileQuery.data!.size_bytes,
        },
      }))
    }
  }, [editingFileQuery.data, selectedFilePath, isEditing])

  const hasUnsavedChanges = React.useMemo(() => {
    if (!savedSnapshot) return false
    const currentYaml = serializeFrontmatter(frontmatter)
    const currentMetadataJson = koinoflowMetadataToJson(koinoflowMetadata)
    return (
      savedSnapshot.markdown !== markdown ||
      savedSnapshot.frontmatterYaml !== currentYaml ||
      savedSnapshot.koinoflowMetadataJson !== currentMetadataJson ||
      filesModified
    )
  }, [savedSnapshot, frontmatter, markdown, koinoflowMetadata, filesModified])

  const nextVersionNumber = (latestVersionNumber ?? 0) + 1

  const handleSave = React.useCallback(async () => {
    if (!skillQuery.data) return
    if (!hasUnsavedChanges) {
      toast.info("No changes to save")
      return
    }

    try {
      const nameAsTitle = frontmatter.name || skillQuery.data.title
      if (
        nameAsTitle !== skillQuery.data.title ||
        frontmatter.description !== skillQuery.data.description
      ) {
        await updateSkill.mutateAsync({
          title: nameAsTitle,
          description: frontmatter.description,
        })
      }

      const frontmatterYaml = serializeFrontmatter(frontmatter)

      let filesPayload: VersionFileInput[] | undefined = undefined
      if (filesModified) {
        const allFiles: VersionFileInput[] = []
        for (const meta of editFileMetas) {
          let payload = editFilePayloads[meta.path]
          if (!payload && editFileContents[meta.path] !== undefined) {
            payload = {
              path: meta.path,
              content: editFileContents[meta.path],
              file_type: meta.file_type,
              mime_type: meta.mime_type,
              encoding: meta.encoding,
            }
          }
          if (!payload && viewVersionNumber !== null) {
            const detail = await apiFetch<VersionFileDetail>(
              `/skills/${skillSlug}/versions/${viewVersionNumber}/files/${encodeURIComponent(meta.path)}`,
            )
            payload = {
              path: detail.path,
              content: detail.content,
              content_base64: detail.content_base64,
              file_type: detail.file_type,
              mime_type: detail.mime_type,
              encoding: detail.encoding,
              size_bytes: detail.size_bytes,
            }
          }
          if (payload) {
            allFiles.push(payload)
          }
        }
        filesPayload = allFiles
      }

      const version = await createVersion.mutateAsync({
        content_md: markdown,
        frontmatter_yaml: frontmatterYaml,
        change_summary:
          changeSummary.trim() ||
          (latestVersionNumber === null
            ? "Initial version"
            : requireChangeSummary
              ? "Updated skill"
              : ""),
        files: filesPayload,
        koinoflow_metadata: koinoflowMetadata,
      })

      setSavedSnapshot({
        markdown,
        frontmatterYaml,
        koinoflowMetadataJson: koinoflowMetadataToJson(koinoflowMetadata),
      })
      setInitializedVersion(version.version_number)
      setChangeSummary("")
      setFilesModified(false)
      toast.success(`Saved as v${version.version_number}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to save skill"
      if (message.includes("No changes detected")) {
        toast.info("No changes detected since the last version")
      } else {
        toast.error(message)
      }
    }
  }, [
    changeSummary,
    createVersion,
    editFileContents,
    editFileMetas,
    editFilePayloads,
    filesModified,
    frontmatter,
    hasUnsavedChanges,
    koinoflowMetadata,
    latestVersionNumber,
    markdown,
    skillQuery.data,
    skillSlug,
    requireChangeSummary,
    updateSkill,
    viewVersionNumber,
  ])

  React.useEffect(() => {
    if (!isEditing) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "s") {
        event.preventDefault()
        void handleSave()
      }
      if (event.key === "Escape") {
        if (hasUnsavedChanges) {
          if (window.confirm("Discard unsaved changes?")) {
            setIsEditing(false)
          }
        } else {
          setIsEditing(false)
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isEditing, handleSave, hasUnsavedChanges])

  function handleEnterEdit() {
    setIsEditing(true)
  }

  function handleCancelEdit() {
    if (hasUnsavedChanges) {
      const shouldLeave = window.confirm("You have unsaved changes. Discard them?")
      if (!shouldLeave) return
    }
    if (skillQuery.data) {
      if (initialVersion) {
        const restored = parseFrontmatter(initialVersion.frontmatter_yaml, {
          name: skillQuery.data.slug,
          description: skillQuery.data.description,
          tags: [],
        })
        setFrontmatter(restored)
        setMarkdown(initialVersion.content_md)
        setKoinoflowMetadata(normalizeKoinoflowMetadata(initialVersion.koinoflow_metadata))
      } else {
        setFrontmatter({
          name: skillQuery.data.slug,
          description: skillQuery.data.description,
          tags: [],
        })
        setMarkdown(
          `# ${skillQuery.data.title}\n\nDescribe this skill, prerequisites, and critical steps here.`,
        )
        setKoinoflowMetadata({ ...EMPTY_KOINOFLOW_METADATA })
      }
      setChangeSummary("")
    }
    resetFileEditorState(
      displayVersion?.files,
      setEditFileMetas,
      setEditFileContents,
      setEditFilePayloads,
      setFilesModified,
      setSelectedFilePath,
    )
    setIsEditing(false)
  }

  async function handleReviewAndPublish() {
    if (hasUnsavedChanges) {
      await handleSave()
    }
    setIsEditing(false)
  }

  async function handleUpdateMetadata() {
    try {
      await updateSkill.mutateAsync({
        title,
        description,
        owner_id: ownerId === "unassigned" ? null : ownerId,
      })
      toast.success("Skill updated")
      setMetadataOpen(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update skill")
    }
  }

  async function handlePublish() {
    try {
      const currentSummary = versionsQuery.data?.[0]?.change_summary ?? ""
      if (publishSummary.trim() !== currentSummary) {
        await updateVersionSummary.mutateAsync({ change_summary: publishSummary.trim() })
      }
      await publishSkill.mutateAsync()
      toast.success(
        `Published ${latestVersionNumber ? `v${latestVersionNumber}` : "latest version"}`,
      )
      setPublishOpen(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to publish skill")
    }
  }

  async function handlePublishDirect() {
    try {
      await publishSkill.mutateAsync()
      toast.success(
        `Published ${latestVersionNumber ? `v${latestVersionNumber}` : "latest version"}`,
      )
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to publish skill")
    }
  }

  async function handleReview() {
    try {
      await reviewSkill.mutateAsync()
      toast.success("Review timestamp updated")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update review timestamp")
    }
  }

  async function handleDelete() {
    if (!skillQuery.data) return

    try {
      await deleteSkill.mutateAsync(skillQuery.data.slug)
      toast.success("Skill deleted")
      navigate(buildWorkspacePath(workspace, "/skills"), { replace: true })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to delete skill")
    }
  }

  async function handleUnshareFromMyTeam() {
    try {
      await unshareFromMyTeam.mutateAsync()
      toast.success("Skill removed from your team")
      setUnshareOpen(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to remove from team")
    }
  }

  async function handleExportSkill() {
    if (!skillQuery.data) return

    const skillName = skillQuery.data.slug
    try {
      const response = await fetch(`/api/v1/skills/${skillName}/export`, {
        credentials: "include",
      })
      if (!response.ok) throw new Error("Export failed")
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `${skillName}.skill`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error("Failed to export skill")
    }
  }

  if (skillQuery.isError) {
    return (
      <ErrorState
        message={
          skillQuery.error instanceof Error
            ? skillQuery.error.message
            : "Unable to load skill"
        }
        onRetry={() => void skillQuery.refetch()}
      />
    )
  }

  if (!skillQuery.data) {
    return <EmptyState title="Loading skill" description="Fetching skill details..." />
  }

  return (
    <div className="space-y-6">
      {importFileInput}

      <Button asChild size="sm" variant="ghost">
        <Link to={buildWorkspacePath(workspace, "/skills")}>
          <ArrowLeftIcon />
          All skills
        </Link>
      </Button>

      {isViewingDraft ? (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/15 px-3 py-2 text-sm font-medium text-amber-900 dark:text-amber-200">
          <AlertTriangleIcon className="size-4 shrink-0" />
          Draft — you are viewing the latest unpublished version.
        </div>
      ) : null}

      {hasUnpublishedDraft ? (
        <div className="flex items-center gap-2 rounded-md border border-blue-500/40 bg-blue-500/15 px-3 py-2 text-sm font-medium text-blue-900 dark:text-blue-200">
          <Clock3Icon className="size-4 shrink-0" />A newer unpublished draft exists. The published
          version remains live until you publish the latest changes.
        </div>
      ) : null}

      <PageHeader
        title={skillQuery.data.title}
        description={skillQuery.data.description || "No description yet."}
        action={
          <div className="flex flex-wrap gap-2">
            {isEditing ? (
              <>
                <Button
                  disabled={
                    !hasUnsavedChanges || createVersion.isPending || updateSkill.isPending
                  }
                  onClick={() => void handleSave()}
                  title="Save new version (⌘/Ctrl+S)"
                >
                  <SaveIcon aria-hidden />
                  {createVersion.isPending || updateSkill.isPending
                    ? "Saving…"
                    : hasUnsavedChanges
                      ? `Save v${nextVersionNumber}`
                      : "No changes"}
                </Button>
                <Button
                  variant="outline"
                  disabled={
                    !hasUnsavedChanges || createVersion.isPending || updateSkill.isPending
                  }
                  onClick={() => void handleReviewAndPublish()}
                  title="Save and return to view mode"
                >
                  <SaveIcon aria-hidden />
                  Save & exit
                </Button>
                <Button variant="ghost" onClick={handleCancelEdit} title="Discard changes (Esc)">
                  <XIcon aria-hidden />
                  Cancel
                </Button>
              </>
            ) : (
              <>
                {canWrite ? (
                  <Button variant="outline" onClick={handleEnterEdit}>
                    <PencilIcon />
                    Edit skill
                  </Button>
                ) : null}
                {canWrite && (needsLatestDraft || skillQuery.data.status === "draft") ? (
                  <Button
                    disabled={publishSkill.isPending}
                    onClick={() => {
                      if (requireChangeSummary) {
                        setPublishSummary(versionsQuery.data?.[0]?.change_summary ?? "")
                        setPublishOpen(true)
                      } else {
                        void handlePublishDirect()
                      }
                    }}
                  >
                    <RocketIcon />
                    {publishSkill.isPending
                      ? "Publishing..."
                      : latestVersionNumber
                        ? `Publish v${latestVersionNumber}`
                        : "Publish"}
                  </Button>
                ) : null}
              </>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon">
                  <MoreHorizontalIcon />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={() =>
                    navigate(
                      buildWorkspacePath(
                        workspace,
                        `/skills/${skillQuery.data?.slug}/history`,
                      ),
                    )
                  }
                >
                  <HistoryIcon className="mr-2 size-4" />
                  History
                </DropdownMenuItem>
                {canWrite ? (
                  <DropdownMenuItem onClick={() => setMetadataOpen(true)}>
                    <PencilIcon className="mr-2 size-4" />
                    Metadata
                  </DropdownMenuItem>
                ) : null}
                {canWrite ? (
                  <DropdownMenuItem onClick={() => setScopeOpen(true)}>
                    <GlobeIcon className="mr-2 size-4" />
                    Change scope
                  </DropdownMenuItem>
                ) : null}
                {isTeamManager && skillQuery.data.is_shared_with_requester_team ? (
                  <DropdownMenuItem onClick={() => setUnshareOpen(true)}>
                    <UserMinusIcon className="mr-2 size-4" />
                    Remove from my team
                  </DropdownMenuItem>
                ) : null}
                {canWrite && skillQuery.data.status === "published" ? (
                  <DropdownMenuItem onClick={() => void handleReview()}>
                    <Clock3Icon className="mr-2 size-4" aria-hidden />
                    Mark validated
                  </DropdownMenuItem>
                ) : null}
                {isEditing && canWrite ? (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={openImportPicker}>
                      <UploadIcon className="mr-2 size-4" />
                      Import .skill
                    </DropdownMenuItem>
                  </>
                ) : null}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => void handleExportSkill()}>
                  <DownloadIcon className="mr-2 size-4" />
                  Export .skill
                </DropdownMenuItem>
                {isEditing && isAdmin ? (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeleteOpen(true)}
                    >
                      <Trash2Icon className="mr-2 size-4" />
                      Delete
                    </DropdownMenuItem>
                  </>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        }
      />

      {isEditing ? (
        <div className="space-y-6">
          <FrontmatterForm value={frontmatter} onChange={setFrontmatter} />

          <KoinoflowMetadataForm
            value={koinoflowMetadata}
            onChange={setKoinoflowMetadata}
            availableProcessSlugs={prerequisiteSuggestions}
          />

          <Card>
            <CardHeader>
              <CardTitle>Instructions</CardTitle>
              <CardDescription>
                Markdown body — the instructions the AI agent receives when this skill is invoked.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MarkdownEditor value={markdown} onChange={setMarkdown} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Change summary</CardTitle>
              <CardDescription>
                Describe what changed in this version for reviewers and history pages.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <Label htmlFor="change-summary">Summary</Label>
              <Input
                id="change-summary"
                placeholder="Updated deployment steps for the new pipeline"
                value={changeSummary}
                onChange={(event) => setChangeSummary(event.target.value)}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Support Files</CardTitle>
              <CardDescription>
                Scripts, references, templates, and other files attached to this skill.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-[200px_minmax(0,1fr)]">
                <div className="border-r pr-3">
                  <FileTreeBrowser
                    files={editFileMetas}
                    selectedPath={selectedFilePath}
                    onFileSelect={setSelectedFilePath}
                    editMode={true}
                    onFileAdd={(file) => {
                      setEditFileMetas((prev) => [
                        ...prev,
                        {
                          id: "",
                          path: file.path,
                          file_type: file.file_type,
                          mime_type: file.mime_type ?? "text/plain",
                          encoding: file.encoding ?? "utf-8",
                          size_bytes: 0,
                        },
                      ])
                      setEditFileContents((prev) => ({ ...prev, [file.path]: file.content ?? "" }))
                      setEditFilePayloads((prev) => ({ ...prev, [file.path]: file }))
                      setSelectedFilePath(file.path)
                      setFilesModified(true)
                    }}
                    onFileDelete={(path) => {
                      setEditFileMetas((prev) => prev.filter((f) => f.path !== path))
                      setEditFileContents((prev) => {
                        const next = { ...prev }
                        delete next[path]
                        return next
                      })
                      setEditFilePayloads((prev) => {
                        const next = { ...prev }
                        delete next[path]
                        return next
                      })
                      if (selectedFilePath === path) setSelectedFilePath(null)
                      setFilesModified(true)
                    }}
                  />
                </div>
                <div className="min-h-[200px]">
                  {selectedFilePath ? (
                    editingFileQuery.isLoading ? (
                      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                        Loading file…
                      </div>
                    ) : editingFileQuery.isError ? (
                      <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-center text-xs text-destructive">
                        <span>
                          Couldn&rsquo;t load {selectedFilePath}.{" "}
                          {editingFileQuery.error instanceof Error
                            ? editingFileQuery.error.message
                            : ""}
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void editingFileQuery.refetch()}
                        >
                          Retry
                        </Button>
                      </div>
                    ) : (
                      <FileEditor
                        path={selectedFilePath}
                        content={editFileContents[selectedFilePath] ?? ""}
                        fileType={
                          editFileMetas.find((f) => f.path === selectedFilePath)?.file_type ??
                          "text"
                        }
                        mimeType={
                          editFileMetas.find((f) => f.path === selectedFilePath)?.mime_type ??
                          editFilePayloads[selectedFilePath]?.mime_type
                        }
                        contentBase64={editFilePayloads[selectedFilePath]?.content_base64}
                        sizeBytes={
                          editFileMetas.find((f) => f.path === selectedFilePath)?.size_bytes
                        }
                        readOnly={false}
                        onChange={(path, content) => {
                          setEditFileContents((prev) => ({ ...prev, [path]: content }))
                          setEditFilePayloads((prev) => ({
                            ...prev,
                            [path]: {
                              path,
                              content,
                              content_base64: null,
                              file_type:
                                editFileMetas.find((f) => f.path === path)?.file_type ?? "text",
                              mime_type:
                                editFileMetas.find((f) => f.path === path)?.mime_type ??
                                "text/plain",
                              encoding: "utf-8",
                              size_bytes: new TextEncoder().encode(content).length,
                            },
                          }))
                          setEditFileMetas((prev) =>
                            prev.map((f) =>
                              f.path === path
                                ? { ...f, size_bytes: new TextEncoder().encode(content).length }
                                : f,
                            ),
                          )
                          setFilesModified(true)
                        }}
                      />
                    )
                  ) : (
                    <div className="flex h-full min-h-[200px] items-center justify-center rounded-lg border border-dashed text-xs text-muted-foreground">
                      Select a file to edit
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-4">
            {skillQuery.data.needs_audit ? (
              <Card className="border-destructive/30 bg-destructive/5">
                <CardContent className="flex items-center justify-between gap-4 pt-6">
                  <div className="flex items-center gap-3 text-sm text-destructive">
                    <AlertTriangleIcon className="size-5 shrink-0" />
                    <span>
                      This skill is overdue for validation.
                      {skillQuery.data.owner?.id !== user?.id
                        ? " Only the skill owner can mark it validated."
                        : ""}
                    </span>
                  </div>
                  {user && skillQuery.data.owner?.id === user.id ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0 border-destructive/30 text-destructive hover:bg-destructive/10"
                      disabled={reviewSkill.isPending}
                      onClick={() => void handleReview()}
                    >
                      <CheckCircle2Icon className="mr-1 size-4" aria-hidden />
                      {reviewSkill.isPending ? "Validating…" : "Mark validated"}
                    </Button>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            {displayVersion ? (
              <>
                <KoinoflowMetadataStrip
                  metadata={normalizeKoinoflowMetadata(displayVersion.koinoflow_metadata)}
                  workspaceSlug={workspace}
                />
                <Card>
                  <CardHeader className="border-b">
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>Skill instructions</CardTitle>
                        <CardDescription>
                          Viewing{" "}
                          {displayVersion.version_number
                            ? `v${displayVersion.version_number}`
                            : "current version"}
                        </CardDescription>
                      </div>
                      {(viewFilesQuery.data?.length ?? 0) > 0 && (
                        <div className="flex rounded-md border text-xs">
                          <button
                            className={`px-3 py-1.5 ${activeTab === "skill" ? "bg-primary text-primary-foreground rounded-l-md" : "text-muted-foreground hover:text-foreground"}`}
                            onClick={() => setActiveTab("skill")}
                          >
                            Skill
                          </button>
                          <button
                            className={`px-3 py-1.5 ${activeTab === "files" ? "bg-primary text-primary-foreground rounded-r-md" : "text-muted-foreground hover:text-foreground"}`}
                            onClick={() => setActiveTab("files")}
                          >
                            Files ({viewFilesQuery.data?.length ?? 0})
                          </button>
                        </div>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="pt-6">
                    {activeTab === "skill" ? (
                      <MarkdownContent content={displayVersion.content_md} />
                    ) : (
                      <div className="grid gap-4 md:grid-cols-[180px_minmax(0,1fr)]">
                        <div className="border-r pr-3">
                          <FileTreeBrowser
                            files={viewFilesQuery.data ?? []}
                            selectedPath={selectedFilePath}
                            onFileSelect={setSelectedFilePath}
                          />
                        </div>
                        <div className="min-h-[300px]">
                          {selectedFilePath ? (
                            viewingFileQuery.isLoading ? (
                              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                                Loading...
                              </div>
                            ) : viewingFileQuery.data ? (
                              <FileEditor
                                path={viewingFileQuery.data.path}
                                content={viewingFileQuery.data.content}
                                fileType={viewingFileQuery.data.file_type}
                                mimeType={viewingFileQuery.data.mime_type}
                                contentBase64={viewingFileQuery.data.content_base64}
                                sizeBytes={viewingFileQuery.data.size_bytes}
                                readOnly={true}
                              />
                            ) : null
                          ) : (
                            <div className="flex h-full min-h-[300px] items-center justify-center rounded-lg border border-dashed text-xs text-muted-foreground">
                              Select a file to view its content
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </>
            ) : (
              <EmptyState
                title="No content available"
                description="Start editing to create the first version of this skill."
                action={
                  canWrite ? <Button onClick={handleEnterEdit}>Open editor</Button> : undefined
                }
              />
            )}
          </div>

          <div className="space-y-4">
            {displayVersion ? (
              <SkillMetadataPanel
                frontmatter={parseFrontmatter(displayVersion.frontmatter_yaml, {
                  name: skillQuery.data.slug,
                  description: skillQuery.data.description,
                  tags: [],
                })}
              />
            ) : null}
            <Card>
              <CardHeader>
                <CardTitle>Skill details</CardTitle>
                <CardDescription>Workspace context and ownership.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="space-y-1">
                  <p className="text-muted-foreground">Status</p>
                  <StatusBadge status={skillQuery.data.status} />
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground">Semantic discovery</p>
                  <DiscoveryEmbeddingStatusBadge
                    status={skillQuery.data.discovery_embedding_status}
                  />
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground">Version</p>
                  <p className="font-medium">
                    {skillQuery.data.current_version
                      ? `Published v${skillQuery.data.current_version.version_number}`
                      : latestVersionNumber
                        ? `Latest draft v${latestVersionNumber}`
                        : "No versions yet"}
                  </p>
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground">Owner</p>
                  <p className="font-medium">{getDisplayName(skillQuery.data.owner)}</p>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <p className="text-muted-foreground">
                      {skillQuery.data.visibility === "team" ||
                      skillQuery.data.visibility === "workspace"
                        ? "Deployment"
                        : allDepartments.length > 1
                          ? "Departments"
                          : "Department"}
                    </p>
                    {canWrite ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:text-foreground"
                        onClick={() => setScopeOpen(true)}
                        title="Change scope"
                      >
                        <GlobeIcon className="size-3.5" />
                      </Button>
                    ) : null}
                  </div>
                  {skillQuery.data.visibility === "team" ? (
                    <Button asChild className="h-auto p-0 text-left" variant="link">
                      <Link
                        to={buildWorkspacePath(workspace, `/teams/${skillQuery.data.team_slug}`)}
                      >
                        {skillQuery.data.team_name} (team-wide)
                      </Link>
                    </Button>
                  ) : skillQuery.data.visibility === "workspace" ? (
                    <p className="font-medium">Workspace-wide</p>
                  ) : allDepartments.length <= 1 ? (
                    department ? (
                      <Button asChild className="h-auto p-0 text-left" variant="link">
                        <Link to={buildWorkspacePath(workspace, `/depts/${department.id}`)}>
                          {skillQuery.data.team_name} / {skillQuery.data.department_name}
                        </Link>
                      </Button>
                    ) : (
                      <p className="font-medium">
                        {skillQuery.data.team_name} / {skillQuery.data.department_name}
                      </p>
                    )
                  ) : (
                    <Collapsible>
                      <CollapsibleTrigger className="group flex w-full items-center justify-between gap-1">
                        <Button asChild className="h-auto p-0 text-left" variant="link">
                          <Link
                            to={buildWorkspacePath(workspace, `/depts/${department?.id}`)}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {skillQuery.data.team_name} / {skillQuery.data.department_name}
                          </Link>
                        </Button>
                        <span className="flex items-center gap-1">
                          <Badge variant="secondary" className="text-[10px] tabular-nums">
                            +{sharedDepartments.length}
                          </Badge>
                          <ChevronDownIcon className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
                        </span>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div className="mt-1.5 space-y-1 border-l-2 border-border pl-3">
                          {sharedDepartments.map((dept) => (
                            <Button
                              key={dept.id}
                              asChild
                              className="h-auto p-0 text-left text-xs"
                              variant="link"
                            >
                              <Link to={buildWorkspacePath(workspace, `/depts/${dept.id}`)}>
                                {dept.team_name} / {dept.name}
                              </Link>
                            </Button>
                          ))}
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  )}
                </div>
                <div className="space-y-1">
                  <p className="text-muted-foreground">Last validated</p>
                  <p className="font-medium">
                    {formatRelativeDate(skillQuery.data.last_reviewed_at, "Not validated yet")}
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Version history</CardTitle>
                  <CardDescription>Who changed what and when.</CardDescription>
                </div>
                <Button
                  asChild
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-muted-foreground"
                >
                  <Link
                    to={buildWorkspacePath(
                      workspace,
                      `/skills/${skillQuery.data.slug}/history`,
                    )}
                  >
                    <HistoryIcon className="mr-1 size-3" />
                    Full history
                  </Link>
                </Button>
              </CardHeader>
              <CardContent>
                <VersionTimeline
                  skillSlug={skillQuery.data.slug}
                  publishedVersionNumber={publishedVersionNumber}
                />
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      <Dialog open={metadataOpen} onOpenChange={setMetadataOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit skill metadata</DialogTitle>
            <DialogDescription>
              Update the title, description, and owner surfaced across the workspace.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="skill-title-edit">Title</Label>
              <Input
                id="skill-title-edit"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-description-edit">Description</Label>
              <Textarea
                id="skill-description-edit"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Owner</Label>
              <Select value={ownerId} onValueChange={setOwnerId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select an owner" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unassigned">Unassigned</SelectItem>
                  {membersQuery.data?.map((member) => (
                    <SelectItem key={member.id} value={member.id}>
                      {getDisplayName(member)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMetadataOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!title.trim() || updateSkill.isPending}
              onClick={() => void handleUpdateMetadata()}
            >
              {updateSkill.isPending ? "Saving..." : "Save changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={publishOpen} onOpenChange={setPublishOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Publish {latestVersionNumber ? `v${latestVersionNumber}` : "latest version"}
            </DialogTitle>
            <DialogDescription>
              This will make the latest version available to AI clients and workspace consumers.
            </DialogDescription>
          </DialogHeader>
          {latestVersionNumber !== null && latestVersionNumber > 1 ? (
            <div className="space-y-2">
              <Label htmlFor="publish-summary">
                Change summary
                {requireChangeSummary ? <span className="ml-1 text-destructive">*</span> : null}
              </Label>
              <Textarea
                id="publish-summary"
                placeholder="Describe what changed in this version..."
                value={publishSummary}
                onChange={(e) => setPublishSummary(e.target.value)}
                rows={3}
              />
              {requireChangeSummary ? (
                <p className="text-xs text-muted-foreground">
                  A change summary is required by workspace policy before publishing.
                </p>
              ) : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={publishSkill.isPending || updateVersionSummary.isPending}
              onClick={() => setPublishOpen(false)}
            >
              Cancel
            </Button>
            <Button
              disabled={
                publishSkill.isPending ||
                updateVersionSummary.isPending ||
                (requireChangeSummary &&
                  latestVersionNumber !== null &&
                  latestVersionNumber > 1 &&
                  !publishSummary.trim())
              }
              onClick={() => void handlePublish()}
            >
              <RocketIcon className="mr-1 size-4" />
              {publishSkill.isPending || updateVersionSummary.isPending
                ? "Publishing..."
                : "Publish"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DeleteConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        entityName={skillQuery.data.title}
        description="This permanently deletes the skill and all of its version history."
        pending={deleteSkill.isPending}
        onConfirm={handleDelete}
      />

      <DeleteConfirmDialog
        open={unshareOpen}
        onOpenChange={setUnshareOpen}
        entityName={skillQuery.data.title}
        title="Remove from your team?"
        description="Your team members will no longer see this skill in their list. The skill remains available to other teams it is shared with."
        confirmLabel="Remove from my team"
        requireTyping={false}
        pending={unshareFromMyTeam.isPending}
        onConfirm={handleUnshareFromMyTeam}
      />

      <ScopeDialog
        open={scopeOpen}
        onOpenChange={setScopeOpen}
        skill={skillQuery.data}
        isAdmin={isAdmin}
      />
    </div>
  )
}
