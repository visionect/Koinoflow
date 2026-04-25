import * as React from "react"

import { cn } from "@/lib/utils"

type FileEditorProps = {
  path: string
  content: string | null
  fileType: string
  mimeType?: string | null
  contentBase64?: string | null
  sizeBytes?: number
  readOnly?: boolean
  onChange?: (path: string, content: string) => void
}

const LANGUAGE_LABELS: Record<string, string> = {
  python: "Python",
  markdown: "Markdown",
  html: "HTML",
  yaml: "YAML",
  json: "JSON",
  javascript: "JavaScript",
  typescript: "TypeScript",
  shell: "Shell",
  image: "Image",
  pdf: "PDF",
  binary: "Binary",
  text: "Plain Text",
  other: "Other",
}

function formatSize(bytes: number | undefined): string {
  if (bytes === undefined) return ""
  if (bytes < 1024) return `${bytes} B`
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(1)} KB`
}

export function FileEditor({
  path,
  content,
  fileType,
  mimeType,
  contentBase64,
  sizeBytes,
  readOnly = false,
  onChange,
}: FileEditorProps) {
  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    onChange?.(path, e.target.value)
  }

  const label = LANGUAGE_LABELS[fileType] ?? fileType
  const isBinary = content === null || fileType === "image" || fileType === "pdf" || fileType === "binary"
  const dataUrl = contentBase64 && mimeType ? `data:${mimeType};base64,${contentBase64}` : null

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-1.5">
        <span className="truncate text-xs font-medium text-foreground">{path}</span>
        <span className="ml-2 shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {label}
        </span>
      </div>
      {isBinary ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 bg-muted/20 p-6 text-center text-xs text-muted-foreground">
          {fileType === "image" && dataUrl ? (
            <img src={dataUrl} alt={path} className="max-h-[420px] max-w-full rounded border bg-background" />
          ) : null}
          <div>
            <p className="font-medium text-foreground">Binary file preview</p>
            <p>{mimeType ?? "application/octet-stream"}</p>
            {sizeBytes !== undefined ? <p>{formatSize(sizeBytes)}</p> : null}
          </div>
        </div>
      ) : (
        <textarea
          className={cn(
            "flex-1 resize-none bg-background p-3 font-mono text-xs leading-relaxed text-foreground outline-none",
            readOnly && "cursor-default select-text",
          )}
          value={content ?? ""}
          readOnly={readOnly}
          onChange={readOnly ? undefined : handleChange}
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="off"
        />
      )}
    </div>
  )
}
