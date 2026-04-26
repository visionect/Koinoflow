import * as React from "react"

import { XIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { SkillFrontmatter } from "@/types"

type FrontmatterFormProps = {
  value: SkillFrontmatter
  onChange: (value: SkillFrontmatter) => void
}

export function FrontmatterForm({ value, onChange }: FrontmatterFormProps) {
  const [tagInput, setTagInput] = React.useState("")

  function updateField<K extends keyof SkillFrontmatter>(
    field: K,
    fieldValue: SkillFrontmatter[K],
  ) {
    onChange({
      ...value,
      [field]: fieldValue,
    })
  }

  function addTag() {
    const nextTag = tagInput.trim()

    if (!nextTag || value.tags.includes(nextTag)) {
      setTagInput("")
      return
    }

    updateField("tags", [...value.tags, nextTag])
    setTagInput("")
  }

  function removeTag(tag: string) {
    updateField(
      "tags",
      value.tags.filter((currentTag) => currentTag !== tag),
    )
  }

  return (
    <div className="rounded-2xl border bg-card p-5">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Skill metadata</h2>
        <p className="text-sm text-muted-foreground">
          Structured frontmatter AI clients use to discover and describe this skill. Client-specific
          fields (e.g. Claude&rsquo;s <code className="font-mono">allowed-tools</code>) are
          preserved on save but not editable here — edit the raw skill file to change them.
        </p>
      </div>

      <div className="grid gap-4">
        <div className="space-y-2">
          <Label htmlFor="frontmatter-name">Name</Label>
          <Input
            id="frontmatter-name"
            placeholder="deploy-to-prod"
            value={value.name}
            onChange={(event) => updateField("name", event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Short identifier clients use when invoking this skill (lowercase, hyphens, numbers).
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="frontmatter-description">Description</Label>
          <Textarea
            id="frontmatter-description"
            placeholder="When to use this skill and what it does..."
            value={value.description}
            onChange={(event) => updateField("description", event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            AI clients use this to decide when to invoke the skill. Front-load the key use case.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="frontmatter-tags">Tags</Label>
          <div className="flex gap-2">
            <Input
              id="frontmatter-tags"
              placeholder="Add a tag and press Enter"
              value={tagInput}
              onChange={(event) => setTagInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault()
                  addTag()
                }
              }}
            />
            <Button type="button" variant="outline" onClick={addTag}>
              Add
            </Button>
          </div>

          <div className="flex flex-wrap gap-2">
            {value.tags.map((tag) => (
              <Badge key={tag} variant="secondary" className="gap-1 pr-1">
                {tag}
                <button
                  className="rounded-full p-0.5 text-muted-foreground transition hover:bg-background hover:text-foreground"
                  type="button"
                  onClick={() => removeTag(tag)}
                  aria-label={`Remove tag ${tag}`}
                >
                  <XIcon className="size-3" aria-hidden />
                  <span className="sr-only">Remove {tag}</span>
                </button>
              </Badge>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
