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

const API_BASE = "/api/v1"

type SseEvent =
  | { type: "start"; data: { model: string; skill_slug: string; instruction: string } }
  | { type: "delta"; data: { text: string } }
  | { type: "done"; data: { stop_reason: string | null; model: string; usage: Record<string, number> } }
  | { type: "error"; data: { message: string } }
  | { type: "rate_limit"; data: { message: string; remaining: number; reset_at: string } }

type ParsedSse = { event: string; data: string }

function parseSseChunk(buffer: string): { events: ParsedSse[]; rest: string } {
  const events: ParsedSse[] = []
  const segments = buffer.split("\n\n")
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

export type AiSkillGeneratorHandle = {
  isStreaming: () => boolean
  cancel: () => void
}

export const AiSkillGenerator = React.forwardRef<
  AiSkillGeneratorHandle,
  {
    workspaceSlug: string
    /** Called continuously as new tokens stream in (full draft text so far). */
    onStreamUpdate: (draft: string) => void
    /** Called once the stream finishes successfully with generated skill content. */
    onStreamComplete: (skillSlug: string, contentMd: string, frontmatterYaml: string) => void
    /** Called when the user cancels or the stream errors out. */
    onStreamCancel: () => void
  }
>(function AiSkillGenerator(
  {
    workspaceSlug,
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
  const [skillSlug, setSkillSlug] = React.useState<string>("")
  const [frontmatterYaml, setFrontmatterYaml] = React.useState<string>("")
  const [rateLimitRemaining, setRateLimitRemaining] = React.useState<number | null>(null)
  const [rateLimitResetAt, setRateLimitResetAt] = React.useState<string | null>(null)
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
    setSkillSlug("")
    setFrontmatterYaml("")
    setRateLimitRemaining(null)
    setRateLimitResetAt(null)
  }

  async function startStream() {
    if (!workspaceSlug) {
      toast.error("Workspace is required.")
      return
    }
    if (instruction.trim().length === 0) {
      toast.error("Describe what skill you want to create.")
      return
    }

    reset()
    setStreaming(true)
    onStreamUpdate("")

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const url = `${API_BASE}/skills/ai-generate?workspace=${encodeURIComponent(workspaceSlug)}`
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
        }),
      })

      // Check rate limit headers
      const remaining = response.headers.get("X-RateLimit-Remaining")
      const resetAt = response.headers.get("X-RateLimit-Reset-At")
      if (remaining !== null) {
        setRateLimitRemaining(Number(remaining))
      }
      if (resetAt !== null) {
        setRateLimitResetAt(resetAt)
      }

      if (!response.ok || !response.body) {
        const text = await response.text().catch(() => "")
        if (response.status === 429) {
          throw new Error(text || "Rate limit exceeded. Try again later.")
        }
        throw new Error(text || `AI generation failed (${response.status})`)
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
            setSkillSlug(parsed.data.skill_slug)
          } else if (parsed.type === "delta") {
            accumulated += parsed.data.text
            tokens += 1
            setDraft(accumulated)
            setTokenCount(tokens)
            onStreamUpdate(accumulated)
          } else if (parsed.type === "done") {
            setUsage(parsed.data.usage ?? {})
            // Extract frontmatter from the beginning of the content
            const fmMatch = accumulated.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/)
            if (fmMatch != null) {
              setFrontmatterYaml(fmMatch[1] ?? "")
            }
          } else if (parsed.type === "error") {
            throw new Error(parsed.data.message)
          } else if (parsed.type === "rate_limit") {
            toast.warning(parsed.data.message)
            setRateLimitRemaining(parsed.data.remaining)
            setRateLimitResetAt(parsed.data.reset_at)
          }
        }
      }

      setStreaming(false)
      if (skillSlug && accumulated) {
        onStreamComplete(skillSlug, accumulated, frontmatterYaml)
      }
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === "AbortError"
      setStreaming(false)
      if (aborted) {
        toast.info("AI generation cancelled")
      } else {
        toast.error(error instanceof Error ? error.message : "AI generation failed")
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
    if (!draft || !skillSlug) return
    onStreamComplete(skillSlug, draft, frontmatterYaml)
    setInstruction("")
    setDraft("")
    setTokenCount(0)
    setUsage(null)
    toast.success("AI-generated skill content ready for editing")
  }

  function handleReject() {
    setDraft("")
    setTokenCount(0)
    setUsage(null)
    onStreamCancel()
  }

  const hasDraft = draft.length > 0
  const inactiveDisabled = !workspaceSlug || streaming

  return (
    <div className="space-y-2 rounded-lg border bg-gradient-to-br from-violet-500/5 via-fuchsia-500/5 to-sky-500/5 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium">
          <SparklesIcon className="size-3.5 text-violet-500" />
          AI-assisted writing
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

      {/* Rate limit indicator */}
      {rateLimitRemaining !== null && !streaming && (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-[10px] text-muted-foreground">
          <span>
            {rateLimitRemaining} AI generation{rateLimitRemaining !== 1 ? "s" : ""} remaining today
            {rateLimitResetAt ? ` · resets ${new Date(rateLimitResetAt).toLocaleTimeString()}` : ""}
          </span>
        </div>
      )}

      <Textarea
        value={instruction}
        onChange={(event) => setInstruction(event.target.value)}
        rows={3}
        disabled={streaming}
        placeholder={
          `Describe the skill you want to create. Be specific about:\n` +
          `• What the skill does (e.g., "Deploy a Docker container to Kubernetes")\n` +
          `• What inputs it needs (e.g., "cluster name, namespace, image tag")\n` +
          `• Any specific steps or error handling required`
        }
        className={cn(
          "min-h-[100px] resize-none border-violet-500/30 bg-background text-xs",
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
          ⌘/Ctrl + Enter to generate
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
                <CheckIcon className="size-3" /> Use this skill
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
            {hasDraft && !streaming ? "Regenerate" : "Generate skill"}
          </Button>
        </div>
      </div>
    </div>
  )
})