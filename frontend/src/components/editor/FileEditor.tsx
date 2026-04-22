import * as React from "react"

import { cn } from "@/lib/utils"

type FileEditorProps = {
  path: string
  content: string
  fileType: string
  readOnly?: boolean
  onChange?: (path: string, content: string) => void
}

const LANGUAGE_LABELS: Record<string, string> = {
  python: "Python",
  markdown: "Markdown",
  html: "HTML",
  yaml: "YAML",
  javascript: "JavaScript",
  typescript: "TypeScript",
  shell: "Shell",
  text: "Plain Text",
  other: "Other",
}

export function FileEditor({
  path,
  content,
  fileType,
  readOnly = false,
  onChange,
}: FileEditorProps) {
  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    onChange?.(path, e.target.value)
  }

  const label = LANGUAGE_LABELS[fileType] ?? fileType

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-1.5">
        <span className="truncate text-xs font-medium text-foreground">{path}</span>
        <span className="ml-2 shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {label}
        </span>
      </div>
      <textarea
        className={cn(
          "flex-1 resize-none bg-background p-3 font-mono text-xs leading-relaxed text-foreground outline-none",
          readOnly && "cursor-default select-text",
        )}
        value={content}
        readOnly={readOnly}
        onChange={readOnly ? undefined : handleChange}
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="off"
      />
    </div>
  )
}
