import * as React from "react"

import { ChevronDownIcon, XIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type { KoinoflowMetadata, RiskLevel } from "@/types"

type KoinoflowMetadataFormProps = {
  value: KoinoflowMetadata
  onChange: (value: KoinoflowMetadata) => void
  availableProcessSlugs?: string[]
}

function TagInput({
  id,
  placeholder,
  items,
  onAdd,
  onRemove,
  suggestions,
}: {
  id: string
  placeholder: string
  items: string[]
  onAdd: (value: string) => void
  onRemove: (value: string) => void
  suggestions?: string[]
}) {
  const [input, setInput] = React.useState("")
  const listId = suggestions ? `${id}-suggestions` : undefined

  function commit() {
    const next = input.trim()
    if (!next) {
      setInput("")
      return
    }
    if (!items.includes(next)) onAdd(next)
    setInput("")
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          id={id}
          list={listId}
          placeholder={placeholder}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === ",") {
              event.preventDefault()
              commit()
            }
          }}
        />
        <Button type="button" variant="outline" onClick={commit}>
          Add
        </Button>
      </div>
      {suggestions && suggestions.length > 0 ? (
        <datalist id={listId}>
          {suggestions
            .filter((slug) => !items.includes(slug))
            .map((slug) => (
              <option key={slug} value={slug} />
            ))}
        </datalist>
      ) : null}
      {items.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <Badge key={item} variant="secondary" className="gap-1 pr-1">
              {item}
              <button
                className="rounded-full p-0.5 text-muted-foreground transition hover:bg-background hover:text-foreground"
                type="button"
                onClick={() => onRemove(item)}
              >
                <XIcon className="size-3" aria-hidden />
                <span className="sr-only">Remove {item}</span>
              </button>
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function KoinoflowMetadataForm({
  value,
  onChange,
  availableProcessSlugs,
}: KoinoflowMetadataFormProps) {
  const [open, setOpen] = React.useState(false)

  function update<K extends keyof KoinoflowMetadata>(field: K, next: KoinoflowMetadata[K]) {
    onChange({ ...value, [field]: next })
  }

  return (
    <div className="rounded-2xl border bg-card p-5">
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">Koinoflow advanced</h2>
            <p className="text-sm text-muted-foreground">
              Signals for AI clients (sent over MCP). These help agents find this process and behave
              safely. Not exported to <code>.skill</code> files.
            </p>
          </div>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-1 shrink-0">
              <ChevronDownIcon
                className={`size-4 transition-transform ${open ? "rotate-180" : ""}`}
              />
              {open ? "Hide" : "Show"}
            </Button>
          </CollapsibleTrigger>
        </div>

        <CollapsibleContent className="mt-4 space-y-5">
          <div className="space-y-2">
            <Label htmlFor="kf-keywords">Retrieval keywords</Label>
            <TagInput
              id="kf-keywords"
              placeholder="release, ship, prod-push"
              items={value.retrieval_keywords}
              onAdd={(v) => update("retrieval_keywords", [...value.retrieval_keywords, v])}
              onRemove={(v) =>
                update(
                  "retrieval_keywords",
                  value.retrieval_keywords.filter((k) => k !== v),
                )
              }
            />
            <p className="text-xs text-muted-foreground">
              Synonyms AI clients can match against when the user's phrasing differs from your title
              and description.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Risk level</Label>
              <Select
                value={value.risk_level ?? "none"}
                onValueChange={(v) => update("risk_level", v === "none" ? null : (v as RiskLevel))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Unset" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Unset</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Included in the AI context so agents can calibrate caution and approval prompts.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="kf-approval" className="flex items-center gap-2">
                <Switch
                  id="kf-approval"
                  checked={value.requires_human_approval}
                  onCheckedChange={(checked) => update("requires_human_approval", checked)}
                />
                <span>Require human approval</span>
              </Label>
              <p className="text-xs text-muted-foreground">
                Agents are instructed to pause and confirm with the user before executing steps.
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="kf-prereqs">Prerequisites (process slugs)</Label>
            <TagInput
              id="kf-prereqs"
              placeholder="setup-production-access"
              items={value.prerequisites}
              suggestions={availableProcessSlugs}
              onAdd={(v) => update("prerequisites", [...value.prerequisites, v])}
              onRemove={(v) =>
                update(
                  "prerequisites",
                  value.prerequisites.filter((slug) => slug !== v),
                )
              }
            />
            <p className="text-xs text-muted-foreground">
              AI is told to read these processes before acting on this one.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="kf-audience">Audience</Label>
            <TagInput
              id="kf-audience"
              placeholder="on-call, engineers"
              items={value.audience}
              onAdd={(v) => update("audience", [...value.audience, v])}
              onRemove={(v) =>
                update(
                  "audience",
                  value.audience.filter((a) => a !== v),
                )
              }
            />
            <p className="text-xs text-muted-foreground">
              Helps disambiguate retrieval when multiple processes have similar titles.
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
