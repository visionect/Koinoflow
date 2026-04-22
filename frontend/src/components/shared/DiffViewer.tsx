import { useState } from "react"

import { diffLines } from "diff"
import { ChevronDownIcon, ChevronRightIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import type { DiffHunk, DiffStats, FileDiffEntry } from "@/types"

type DiffViewerProps = {
  oldText: string
  newText: string
  oldLabel: string
  newLabel: string
}

export function DiffViewer({ oldText, newText, oldLabel, newLabel }: DiffViewerProps) {
  const changes = diffLines(oldText, newText)

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="rounded-md bg-diff-remove px-2 py-1 text-diff-remove-foreground">
          {oldLabel}
        </span>
        <span>to</span>
        <span className="rounded-md bg-diff-add px-2 py-1 text-diff-add-foreground">
          {newLabel}
        </span>
      </div>
      <pre className="max-h-[70svh] overflow-auto rounded-xl border bg-muted/40 p-4 text-sm leading-6">
        {changes.map((change, index) => (
          <span
            key={`${index}-${change.count ?? 0}`}
            className={cn(
              "block whitespace-pre-wrap px-2",
              change.added && "bg-diff-add text-diff-add-foreground",
              change.removed && "bg-diff-remove text-diff-remove-foreground",
            )}
          >
            {change.value}
          </span>
        ))}
      </pre>
    </div>
  )
}

type UnifiedDiffViewerProps = {
  hunks: DiffHunk[]
  stats: DiffStats
  oldLabel: string
  newLabel: string
}

export function UnifiedDiffViewer({ hunks, stats, oldLabel, newLabel }: UnifiedDiffViewerProps) {
  const [wrap, setWrap] = useState(true)

  if (hunks.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        No content changes between these versions.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="rounded-md bg-diff-remove px-2 py-1 font-medium text-diff-remove-foreground">
              {oldLabel}
            </span>
            <span className="text-muted-foreground">to</span>
            <span className="rounded-md bg-diff-add px-2 py-1 font-medium text-diff-add-foreground">
              {newLabel}
            </span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <span className="font-mono text-diff-add-foreground">+{stats.additions}</span>
            <span className="font-mono text-diff-remove-foreground">-{stats.deletions}</span>
          </div>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-1.5 text-muted-foreground">
          <input
            type="checkbox"
            className="size-3.5 accent-primary"
            checked={wrap}
            onChange={(e) => setWrap(e.target.checked)}
          />
          Wrap long lines
        </label>
      </div>

      <div className="overflow-hidden rounded-xl border">
        {hunks.map((hunk, hunkIdx) => {
          let oldLine = hunk.old_start
          let newLine = hunk.new_start

          return (
            <div key={hunkIdx}>
              <div className="border-b bg-info/10 px-4 py-1.5 font-mono text-xs text-info">
                @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@
              </div>
              <div className="font-mono text-[13px] leading-[22px]">
                {hunk.lines.map((line, lineIdx) => {
                  const prefix = line[0] ?? " "
                  const content = line.slice(1)
                  const isAdd = prefix === "+"
                  const isRemove = prefix === "-"

                  let oldNum: number | null = null
                  let newNum: number | null = null

                  if (isAdd) {
                    newNum = newLine++
                  } else if (isRemove) {
                    oldNum = oldLine++
                  } else {
                    oldNum = oldLine++
                    newNum = newLine++
                  }

                  return (
                    <div
                      key={`${hunkIdx}-${lineIdx}`}
                      className={cn("flex", isAdd && "bg-diff-add", isRemove && "bg-diff-remove")}
                    >
                      <span className="w-10 shrink-0 select-none border-r px-1 text-right text-[11px] leading-[22px] text-muted-foreground/60">
                        {oldNum ?? ""}
                      </span>
                      <span className="w-10 shrink-0 select-none border-r px-1 text-right text-[11px] leading-[22px] text-muted-foreground/60">
                        {newNum ?? ""}
                      </span>
                      <span
                        className={cn(
                          "w-5 shrink-0 select-none text-center",
                          isAdd && "text-diff-add-foreground",
                          isRemove && "text-diff-remove-foreground",
                        )}
                      >
                        {isAdd ? "+" : isRemove ? "-" : " "}
                      </span>
                      <span
                        className={cn(
                          "min-w-0 flex-1 pr-4",
                          wrap ? "whitespace-pre-wrap break-all" : "overflow-x-auto whitespace-pre",
                          isAdd && "text-diff-add-foreground",
                          isRemove && "text-diff-remove-foreground",
                        )}
                      >
                        {content}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function FileDiffHunks({ hunks }: { hunks: DiffHunk[] }) {
  return (
    <div className="mt-1 overflow-hidden rounded-lg border">
      {hunks.map((hunk, hunkIdx) => {
        let oldLine = hunk.old_start
        let newLine = hunk.new_start
        return (
          <div key={hunkIdx}>
            <div className="border-b bg-info/10 px-4 py-1 font-mono text-xs text-info">
              @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@
            </div>
            <div className="font-mono text-[13px] leading-[22px]">
              {hunk.lines.map((line, lineIdx) => {
                const prefix = line[0] ?? " "
                const content = line.slice(1)
                const isAdd = prefix === "+"
                const isRemove = prefix === "-"

                let oldNum: number | null = null
                let newNum: number | null = null
                if (isAdd) {
                  newNum = newLine++
                } else if (isRemove) {
                  oldNum = oldLine++
                } else {
                  oldNum = oldLine++
                  newNum = newLine++
                }

                return (
                  <div
                    key={`${hunkIdx}-${lineIdx}`}
                    className={cn("flex", isAdd && "bg-diff-add", isRemove && "bg-diff-remove")}
                  >
                    <span className="w-10 shrink-0 select-none border-r px-1 text-right text-[11px] leading-[22px] text-muted-foreground/60">
                      {oldNum ?? ""}
                    </span>
                    <span className="w-10 shrink-0 select-none border-r px-1 text-right text-[11px] leading-[22px] text-muted-foreground/60">
                      {newNum ?? ""}
                    </span>
                    <span
                      className={cn(
                        "w-5 shrink-0 select-none text-center",
                        isAdd && "text-diff-add-foreground",
                        isRemove && "text-diff-remove-foreground",
                      )}
                    >
                      {isAdd ? "+" : isRemove ? "-" : " "}
                    </span>
                    <span
                      className={cn(
                        "min-w-0 flex-1 whitespace-pre-wrap break-all pr-4",
                        isAdd && "text-diff-add-foreground",
                        isRemove && "text-diff-remove-foreground",
                      )}
                    >
                      {content}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function FileDiffEntryRow({ entry }: { entry: FileDiffEntry }) {
  const [expanded, setExpanded] = useState(false)
  const isAdded = entry.status === "added"
  const isDeleted = entry.status === "deleted"
  const isModified = entry.status === "modified"
  const prefix = isAdded ? "+" : isDeleted ? "-" : "~"
  const sizeInfo = isAdded
    ? entry.new_size !== null
      ? `(${(entry.new_size / 1024).toFixed(1)} KB)`
      : ""
    : isDeleted
      ? ""
      : entry.old_size !== null && entry.new_size !== null
        ? `(${(entry.old_size / 1024).toFixed(1)} KB → ${(entry.new_size / 1024).toFixed(1)} KB)`
        : ""
  const hasHunks = entry.hunks && entry.hunks.length > 0

  return (
    <div>
      <button
        type="button"
        className={cn(
          "flex w-full items-baseline gap-1.5 rounded font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring",
          hasHunks ? "cursor-pointer" : "cursor-default",
          isAdded && "text-diff-add-foreground",
          isDeleted && "text-diff-remove-foreground",
          isModified && "text-info",
        )}
        onClick={() => hasHunks && setExpanded((v) => !v)}
        disabled={!hasHunks}
        aria-expanded={hasHunks ? expanded : undefined}
        aria-label={
          hasHunks ? `${expanded ? "Collapse" : "Expand"} diff for ${entry.path}` : undefined
        }
      >
        <span className="shrink-0 font-bold" aria-hidden>
          {prefix}
        </span>
        <span>{entry.path}</span>
        {sizeInfo && <span className="text-muted-foreground">{sizeInfo}</span>}
        {isDeleted && !sizeInfo && <span className="text-muted-foreground">(deleted)</span>}
        {hasHunks &&
          (expanded ? (
            <ChevronDownIcon
              className="ml-auto size-3.5 shrink-0 text-muted-foreground"
              aria-hidden
            />
          ) : (
            <ChevronRightIcon
              className="ml-auto size-3.5 shrink-0 text-muted-foreground"
              aria-hidden
            />
          ))}
      </button>
      {expanded && hasHunks && <FileDiffHunks hunks={entry.hunks!} />}
    </div>
  )
}

type FileDiffSummaryProps = {
  entries: FileDiffEntry[]
}

export function FileDiffSummary({ entries }: FileDiffSummaryProps) {
  if (entries.length === 0) {
    return null
  }

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">Files changed:</p>
      <div className="space-y-0.5">
        {entries.map((entry) => (
          <FileDiffEntryRow key={entry.path} entry={entry} />
        ))}
      </div>
    </div>
  )
}
