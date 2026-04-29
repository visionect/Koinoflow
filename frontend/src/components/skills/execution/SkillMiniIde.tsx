import * as React from "react"
import {
  AlertCircleIcon,
  CheckIcon,
  Loader2Icon,
  RotateCcwIcon,
  SaveIcon,
  ZapIcon,
} from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import {
  apiFetch,
  queryKeys,
  useCreateVersion,
  useVersion,
  useVersionFile,
  useVersionFiles,
  type SkillSystemKind,
} from "@/api/client"
import { FileEditor } from "@/components/editor/FileEditor"
import { FileTreeBrowser } from "@/components/skills/FileTreeBrowser"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { VersionFileDetail, VersionFileInput } from "@/types"

import { AiEditPanel } from "./AiEditPanel"

function buildScopeQuery(systemKind?: SkillSystemKind): string {
  return systemKind ? `?system_kind=${systemKind}` : ""
}

export type SkillMiniIdeHandle = {
  /** Returns true if there are unsaved changes. */
  isDirty: () => boolean
}

export const SkillMiniIde = React.forwardRef<
  SkillMiniIdeHandle,
  {
    skillSlug: string
    versionNumber: number | null
    systemKind?: SkillSystemKind
    canWrite: boolean
    onSavedAndRun?: (newVersionNumber: number) => void
    onSaved?: (newVersionNumber: number) => void
    /** Latest run id, passed to AI assist for failure context. */
    latestRunId?: string | null
  }
>(function SkillMiniIde(
  { skillSlug, versionNumber, systemKind, canWrite, onSavedAndRun, onSaved, latestRunId },
  ref,
) {
  const queryClient = useQueryClient()
  const filesQuery = useVersionFiles(skillSlug, versionNumber, systemKind)
  const versionQuery = useVersion(skillSlug, versionNumber, systemKind)
  const createVersion = useCreateVersion(skillSlug, systemKind)

  const [selectedPath, setSelectedPath] = React.useState<string | null>(null)
  const [editedContent, setEditedContent] = React.useState<Record<string, string>>({})
  const [saving, setSaving] = React.useState(false)
  const [savePhase, setSavePhase] = React.useState<"idle" | "loading" | "saving">("idle")
  // AI streaming preview: when set, replaces the editor's view of the selected
  // file with the live token-by-token draft. Accept moves it into editedContent.
  const [aiPreview, setAiPreview] = React.useState<{ path: string; text: string } | null>(null)
  const [aiStreaming, setAiStreaming] = React.useState(false)

  const fileQuery = useVersionFile(
    skillSlug,
    versionNumber,
    selectedPath,
    systemKind,
  )

  // Auto-select first file (typically run.py / entrypoint) when files load.
  React.useEffect(() => {
    if (selectedPath !== null) return
    const files = filesQuery.data
    if (!files || files.length === 0) return
    const entrypoint = files.find((f) => f.path === "run.py") ?? files[0]
    if (!entrypoint) return
    setSelectedPath(entrypoint.path)
  }, [filesQuery.data, selectedPath])

  const isDirty = Object.keys(editedContent).length > 0

  React.useImperativeHandle(ref, () => ({ isDirty: () => isDirty }), [isDirty])

  function handleEdit(path: string, content: string) {
    setEditedContent((prev) => ({ ...prev, [path]: content }))
  }

  function handleResetFile() {
    if (!selectedPath) return
    setEditedContent((prev) => {
      const next = { ...prev }
      delete next[selectedPath]
      return next
    })
  }

  async function buildFilesPayload(): Promise<VersionFileInput[] | null> {
    const metas = filesQuery.data ?? []
    if (metas.length === 0) return []
    const scopeQuery = buildScopeQuery(systemKind)
    const out: VersionFileInput[] = []
    for (const meta of metas) {
      const editedText = editedContent[meta.path]
      let detail: VersionFileDetail | null = null
      try {
        // Pull from query cache if we can; otherwise fetch.
        const cached = queryClient.getQueryData<VersionFileDetail>(
          queryKeys.skills.file(skillSlug, versionNumber ?? 0, meta.path, systemKind),
        )
        detail =
          cached ??
          (await apiFetch<VersionFileDetail>(
            `/skills/${skillSlug}/versions/${versionNumber}/files/${encodeURIComponent(meta.path)}${scopeQuery}`,
          ))
      } catch (error) {
        toast.error(
          `Could not load ${meta.path}: ${error instanceof Error ? error.message : "unknown error"}`,
        )
        return null
      }

      const content =
        editedText !== undefined ? editedText : (detail?.content ?? null)
      out.push({
        path: meta.path,
        content,
        content_base64: editedText !== undefined ? null : (detail?.content_base64 ?? null),
        file_type: meta.file_type,
        mime_type: meta.mime_type,
        encoding: editedText !== undefined ? "utf-8" : (detail?.encoding ?? "utf-8"),
        size_bytes:
          editedText !== undefined ? new Blob([editedText]).size : (detail?.size_bytes ?? 0),
      })
    }
    return out
  }

  async function performSave(then: "done" | "rerun"): Promise<number | null> {
    if (!isDirty) {
      toast.info("No changes to save")
      return null
    }
    if (!versionNumber || !versionQuery.data) {
      toast.error("Cannot save: no current version loaded")
      return null
    }
    setSaving(true)
    try {
      setSavePhase("loading")
      const files = await buildFilesPayload()
      if (files === null) return null
      setSavePhase("saving")
      const newVersion = await createVersion.mutateAsync({
        content_md: versionQuery.data.content_md,
        frontmatter_yaml: versionQuery.data.frontmatter_yaml ?? "",
        change_summary: `Sandbox edit · updated ${Object.keys(editedContent).length} file(s)`,
        files,
      })
      setEditedContent({})
      toast.success(`Saved as v${newVersion.version_number}`)
      if (then === "rerun") {
        onSavedAndRun?.(newVersion.version_number)
      } else {
        onSaved?.(newVersion.version_number)
      }
      return newVersion.version_number
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not save changes"
      if (message.includes("No changes detected")) {
        toast.info("No changes detected since the last version")
      } else {
        toast.error(message)
      }
      return null
    } finally {
      setSaving(false)
      setSavePhase("idle")
    }
  }

  const aiPreviewActive =
    aiPreview !== null && selectedPath !== null && aiPreview.path === selectedPath
  const editorContent =
    selectedPath === null
      ? null
      : aiPreviewActive
        ? aiPreview!.text
        : editedContent[selectedPath] !== undefined
          ? editedContent[selectedPath]
          : (fileQuery.data?.content ?? null)
  const editorMeta =
    selectedPath !== null
      ? (filesQuery.data?.find((f) => f.path === selectedPath) ?? null)
      : null
  const fileIsDirty = selectedPath !== null && editedContent[selectedPath] !== undefined

  function handleAiUpdate(draft: string) {
    if (!selectedPath) return
    setAiPreview({ path: selectedPath, text: draft })
  }

  function handleAiComplete(draft: string) {
    setAiStreaming(false)
    if (!selectedPath) return
    if (draft && draft.trim().length > 0) {
      setEditedContent((prev) => ({ ...prev, [selectedPath]: draft }))
    }
    setAiPreview(null)
  }

  function handleAiCancel() {
    setAiStreaming(false)
    setAiPreview(null)
  }

  if (!versionNumber) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
        Publish or create a skill version before editing files in the sandbox.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <h4 className="text-sm font-medium">Mini IDE</h4>
          <span className="text-[11px] text-muted-foreground">
            Editing v{versionNumber}
            {isDirty ? (
              <span className="ml-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-300">
                {Object.keys(editedContent).length} unsaved
              </span>
            ) : null}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {fileIsDirty ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleResetFile}
              disabled={saving}
              className="h-7 gap-1 px-2 text-xs"
            >
              <RotateCcwIcon className="size-3" /> Revert file
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void performSave("done")}
            disabled={!canWrite || !isDirty || saving}
            className="h-7 gap-1 px-2 text-xs"
          >
            {saving && savePhase === "saving" ? (
              <Loader2Icon className="size-3 animate-spin" />
            ) : (
              <SaveIcon className="size-3" />
            )}
            Save as new version
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => void performSave("rerun")}
            disabled={!canWrite || !isDirty || saving}
            className="h-7 gap-1 px-2 text-xs"
          >
            {saving ? (
              <Loader2Icon className="size-3 animate-spin" />
            ) : (
              <ZapIcon className="size-3" />
            )}
            Save & rerun
          </Button>
        </div>
      </div>

      {!canWrite ? (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-800 dark:text-amber-200">
          <AlertCircleIcon className="size-3.5" />
          <span>You need write access on this skill to edit files.</span>
        </div>
      ) : null}

      <div className="grid gap-2 lg:grid-cols-[200px_minmax(0,1fr)]">
        <div className="overflow-hidden rounded-lg border bg-background">
          {filesQuery.isLoading ? (
            <p className="p-3 text-xs text-muted-foreground">Loading files…</p>
          ) : filesQuery.data && filesQuery.data.length > 0 ? (
            <FileTreeBrowser
              files={filesQuery.data}
              selectedPath={selectedPath}
              onFileSelect={(path) => setSelectedPath(path)}
            />
          ) : (
            <p className="p-3 text-xs text-muted-foreground">No files in this version.</p>
          )}
        </div>
        <div className="h-[360px]">
          {selectedPath === null ? (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed text-xs text-muted-foreground">
              Pick a file from the tree to edit it.
            </div>
          ) : fileQuery.isLoading && editedContent[selectedPath] === undefined ? (
            <div className="flex h-full items-center justify-center rounded-lg border text-xs text-muted-foreground">
              Loading {selectedPath}…
            </div>
          ) : editorMeta ? (
            <div className="flex h-full flex-col">
              {aiPreviewActive ? (
                <div className="flex items-center gap-1.5 rounded-t-lg border border-b-0 bg-violet-500/10 px-3 py-1 text-[11px] text-violet-800 dark:text-violet-200">
                  <span className="size-1.5 animate-pulse rounded-full bg-violet-500" />
                  AI preview · {selectedPath} · {aiPreview!.text.length} chars (Keep / Discard
                  below)
                </div>
              ) : fileIsDirty ? (
                <div className="flex items-center gap-1.5 rounded-t-lg border border-b-0 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-800 dark:text-amber-200">
                  <span className="size-1.5 rounded-full bg-amber-500" />
                  Unsaved changes in {selectedPath}
                </div>
              ) : (
                <div className="flex items-center gap-1.5 rounded-t-lg border border-b-0 bg-muted/40 px-3 py-1 text-[11px] text-muted-foreground">
                  <CheckIcon className="size-3" />
                  Synced with v{versionNumber}
                </div>
              )}
              <div className={cn("flex-1 overflow-hidden", fileIsDirty ? "" : "")}>
                <FileEditor
                  path={editorMeta.path}
                  content={editorContent}
                  fileType={editorMeta.file_type}
                  mimeType={editorMeta.mime_type}
                  contentBase64={fileQuery.data?.content_base64}
                  sizeBytes={editorMeta.size_bytes}
                  readOnly={!canWrite || aiPreviewActive || aiStreaming}
                  onChange={handleEdit}
                />
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <AiEditPanel
        skillSlug={skillSlug}
        versionNumber={versionNumber}
        filePath={selectedPath}
        systemKind={systemKind}
        canWrite={canWrite}
        runIdForContext={latestRunId ?? null}
        onStreamUpdate={(draft) => {
          setAiStreaming(true)
          handleAiUpdate(draft)
        }}
        onStreamComplete={handleAiComplete}
        onStreamCancel={handleAiCancel}
      />
    </div>
  )
})

