import * as React from "react"
import {
  CheckIcon,
  Loader2Icon,
  SparklesIcon,
  StopCircleIcon,
  XIcon,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import type { SkillSystemKind } from "@/api/client"

const API_BASE = "/api/v1"

type SseEvent =
  | { type: "start"; data: { model: string; file_path: string; instruction: string } }
  | { type: "delta"; data: { text: string } }
  | { type: "done"; data: { stop_reason: string | null; model: string; usage: Record<string, number> } }
  | { type: "error"; data: { message: string } }

type ParsedSse = { event: string; data: string }

function parseSseChunk(buffer: string): { events: ParsedSse[]; rest: string } {
  const events: ParsedSse[] = []
  const segments = buffer.split("\n\n")
  // The last segment may be incomplete — keep it in the buffer.
  const rest = segments.pop() ?? ""
  for (const segment of segments) {
    if (!segment.trim()) continue
    let event = "message"
    const dataLines: string[] = []
    for (const line of segment.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim()
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim())
    }
    if (dataLines.length === 0) continue
    events.push({ event, data: dataLines.join("\n") })
  }
  return { events, rest }
}

export type AiEditPanelHandle = {
  isStreaming: () => boolean
  cancel: () => void
}

export const AiEditPanel = React.forwardRef<
  AiEditPanelHandle,
  {
    skillSlug: string
    versionNumber: number | null
    filePath: string | null
    systemKind?: SkillSystemKind
    canWrite: boolean
    /** Latest run id, used to give Claude the recent error/logs as context. */
    runIdForContext?: string | null
    /** Called continuously as new tokens stream in (full draft text so far). */
    onStreamUpdate: (draft: string) => void
    /** Called once the stream finishes successfully. */
    onStreamComplete: (draft: string) => void
    /** Called when the user cancels or the stream errors out. */
    onStreamCancel: () => void
  }
>(function AiEditPanel(
  {
    skillSlug,
    versionNumber,
    filePath,
    systemKind,
    canWrite,
    runIdForContext,
    onStreamUpdate,
    onStreamComplete,
    onStreamCancel,
  },
  ref,
) {
  const [instruction, setInstruction] = React.useState("")
  const [streaming, setStreaming] = React.useState(false)
  const [draft, setDraft] = React.useState<string>("")
  const [model, setModel] = React.useState<string | null>(null)
  const [usage, setUsage] = React.useState<Record<string, number> | null>(null)
  const [tokenCount, setTokenCount] = React.useState(0)
  const abortRef = React.useRef<AbortController | null>(null)

  React.useImperativeHandle(
    ref,
    () => ({
      isStreaming: () => streaming,
      cancel: () => abortRef.current?.abort(),
    }),
    [streaming],
  )

  function reset() {
    setDraft("")
    setUsage(null)
    setModel(null)
    setTokenCount(0)
  }

  async function startStream() {
    if (!canWrite) {
      toast.error("You need write access to use AI assist.")
      return
    }
    if (!filePath) {
      toast.error("Pick a file in the editor first.")
      return
    }
    if (!versionNumber) {
      toast.error("This skill has no version to edit yet.")
      return
    }
    if (instruction.trim().length === 0) {
      toast.error("Describe what you want changed.")
      return
    }

    reset()
    setStreaming(true)
    onStreamUpdate("")

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const url = `${API_BASE}/skills/${skillSlug}/versions/${versionNumber}/files/${encodeURIComponent(filePath)}/ai-edit${
        systemKind ? `?system_kind=${systemKind}` : ""
      }`
      const csrfToken = document.cookie
        .split("; ")
        .find((part) => part.startsWith("csrftoken="))
        ?.split("=")[1]

      const response = await fetch(url, {
        method: "POST",
        signal: controller.signal,
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        },
        body: JSON.stringify({
          instruction: instruction.trim(),
          run_id: runIdForContext ?? null,
        }),
      })

      if (!response.ok || !response.body) {
        const text = await response.text().catch(() => "")
        throw new Error(text || `AI edit request failed (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let accumulated = ""
      let tokens = 0

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, rest } = parseSseChunk(buffer)
        buffer = rest
        for (const evt of events) {
          let parsed: SseEvent | null = null
          try {
            parsed = { type: evt.event as SseEvent["type"], data: JSON.parse(evt.data) } as SseEvent
          } catch {
            continue
          }
          if (parsed.type === "start") {
            setModel(parsed.data.model)
          } else if (parsed.type === "delta") {
            accumulated += parsed.data.text
            tokens += 1
            setDraft(accumulated)
            setTokenCount(tokens)
            onStreamUpdate(accumulated)
          } else if (parsed.type === "done") {
            setUsage(parsed.data.usage ?? {})
          } else if (parsed.type === "error") {
            throw new Error(parsed.data.message)
          }
        }
      }

      setStreaming(false)
      onStreamComplete(accumulated)
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === "AbortError"
      setStreaming(false)
      if (aborted) {
        toast.info("AI edit cancelled")
      } else {
        toast.error(error instanceof Error ? error.message : "AI edit failed")
      }
      onStreamCancel()
    } finally {
      abortRef.current = null
    }
  }

  function handleStop() {
    abortRef.current?.abort()
  }

  function handleAccept() {
    if (!draft) return
    onStreamComplete(draft)
    setInstruction("")
    setDraft("")
    setTokenCount(0)
    setUsage(null)
    toast.success("AI suggestion applied to the editor")
  }

  function handleReject() {
    setDraft("")
    setTokenCount(0)
    setUsage(null)
    onStreamCancel()
  }

  const hasDraft = draft.length > 0
  const inactiveDisabled = !canWrite || !filePath || !versionNumber || streaming

  return (
    <div className="space-y-2 rounded-lg border bg-gradient-to-br from-violet-500/5 via-fuchsia-500/5 to-sky-500/5 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium">
          <SparklesIcon className="size-3.5 text-violet-500" />
          AI assist
          <span className="rounded bg-background px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">
            {model ?? "claude-sonnet-4-6"}
          </span>
        </div>
        {streaming ? (
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Loader2Icon className="size-3 animate-spin" />
            streaming · {tokenCount} chunks
          </span>
        ) : usage ? (
          <span className="text-[11px] text-muted-foreground">
            in {usage.input_tokens ?? 0} · out {usage.output_tokens ?? 0}
            {usage.cache_read_input_tokens ? ` · cached ${usage.cache_read_input_tokens}` : ""}
          </span>
        ) : null}
      </div>

      <Textarea
        value={instruction}
        onChange={(event) => setInstruction(event.target.value)}
        rows={2}
        disabled={streaming}
        placeholder={
          filePath
            ? `What should we change in ${filePath}? e.g. "wrap the API call in retry logic" or "fix the KeyError when 'amount' is missing"`
            : "Pick a file from the editor first."
        }
        className={cn(
          "min-h-[60px] resize-none border-violet-500/30 bg-background text-xs",
          streaming ? "opacity-70" : "",
        )}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault()
            void startStream()
          }
        }}
      />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground">
          {runIdForContext ? "Recent run logs included as context · " : ""}
          ⌘/Ctrl + Enter to run
        </span>
        <div className="flex items-center gap-1">
          {streaming ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleStop}
              className="h-7 gap-1 text-xs"
            >
              <StopCircleIcon className="size-3" />
              Stop
            </Button>
          ) : null}
          {hasDraft && !streaming ? (
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleReject}
                className="h-7 gap-1 text-xs text-muted-foreground"
              >
                <XIcon className="size-3" /> Discard
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={handleAccept}
                className="h-7 gap-1 bg-violet-600 text-xs text-white hover:bg-violet-700"
              >
                <CheckIcon className="size-3" /> Keep
              </Button>
            </>
          ) : null}
          <Button
            type="button"
            size="sm"
            onClick={() => void startStream()}
            disabled={inactiveDisabled || instruction.trim().length === 0}
            className="h-7 gap-1 bg-violet-600 text-xs text-white hover:bg-violet-700 disabled:opacity-50"
          >
            {streaming ? (
              <Loader2Icon className="size-3 animate-spin" />
            ) : (
              <SparklesIcon className="size-3" />
            )}
            {hasDraft && !streaming ? "Regenerate" : "Generate"}
          </Button>
        </div>
      </div>
    </div>
  )
})
