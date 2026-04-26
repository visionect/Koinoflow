import { ChevronDownIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { SkillFrontmatter } from "@/types"

const KNOWN_KEYS = new Set(["name", "description", "tags"])

function stringifyValue(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  if (Array.isArray(value)) return value.map(stringifyValue).join(", ")
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 py-2 text-sm">
      <p className="text-muted-foreground">{label}</p>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export function SkillMetadataPanel({ frontmatter }: { frontmatter: SkillFrontmatter }) {
  const extraEntries = Object.entries(frontmatter).filter(([key]) => !KNOWN_KEYS.has(key))

  return (
    <Card>
      <Collapsible defaultOpen>
        <CollapsibleTrigger className="group flex w-full items-start justify-between gap-3 text-left">
          <CardHeader className="flex-1">
            <CardTitle className="text-base">Skill metadata</CardTitle>
            <CardDescription>
              Frontmatter AI clients read when deciding how to invoke this skill.
            </CardDescription>
          </CardHeader>
          <div className="mr-4 mt-5 shrink-0 text-muted-foreground">
            <ChevronDownIcon
              className="size-4 transition-transform group-data-[state=open]:rotate-180"
              aria-hidden
            />
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="divide-y pb-4 pt-0">
            <Row label="Name">
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                {frontmatter.name || "—"}
              </code>
            </Row>
            <Row label="Description">
              <p className="whitespace-pre-wrap">{frontmatter.description || "—"}</p>
            </Row>
            {frontmatter.tags.length > 0 ? (
              <Row label="Tags">
                <div className="flex flex-wrap gap-1">
                  {frontmatter.tags.map((tag) => (
                    <Badge key={tag} variant="secondary">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </Row>
            ) : null}
            {extraEntries.length > 0 ? (
              <Row label="Extra frontmatter">
                <dl className="space-y-1 text-xs">
                  {extraEntries.map(([key, val]) => (
                    <div key={key} className="flex items-start gap-2 font-mono">
                      <dt className="shrink-0 text-muted-foreground">{key}:</dt>
                      <dd className="min-w-0 break-words">{stringifyValue(val)}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-2 text-xs text-muted-foreground">
                  Client-specific keys preserved on save. Edit them in the raw skill file.
                </p>
              </Row>
            ) : null}
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}
