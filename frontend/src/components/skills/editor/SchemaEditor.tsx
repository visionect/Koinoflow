import * as React from "react"
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

/**
 * Inline schema editor for input/output JSON schemas in the skill editor.
 * Supports both visual form mode and raw JSON mode.
 */
export function SchemaEditor({
  value,
  onChange,
  label = "Schema",
  mode = "visual",
  readOnly = false,
}: {
  value: Record<string, unknown> | null
  onChange: (next: Record<string, unknown> | null) => void
  label?: string
  mode?: "visual" | "json"
  readOnly?: boolean
}) {
  const [activeMode, setActiveMode] = React.useState<"visual" | "json">(mode)
  const [jsonText, setJsonText] = React.useState(() =>
    value ? JSON.stringify(value, null, 2) : "{}"
  )
  const [jsonError, setJsonError] = React.useState<string | null>(null)

  const hasSchema = value !== null && typeof value === "object" && !Array.isArray(value)

  function handleJsonChange(text: string) {
    setJsonText(text)
    const trimmed = text.trim()
    if (trimmed === "") {
      setJsonError(null)
      return
    }
    try {
      const parsed = JSON.parse(text)
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setJsonError("Must be a JSON object")
        return
      }
      setJsonError(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Invalid JSON"
      setJsonError(msg)
    }
  }

  function handleCommit() {
    if (jsonError) {
      toast.error("Fix JSON errors before committing.")
      return
    }
    try {
      const parsed = JSON.parse(jsonText)
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        toast.error("Schema must be a JSON object")
        return
      }
      onChange(parsed)
      toast.success("Schema updated")
    } catch {
      toast.error("Invalid JSON — could not update schema")
    }
  }

  function handleLoadDefault() {
    const defaults = {
      type: "object",
      properties: {
        example_field: {
          type: "string",
          description: "An example field",
        },
      },
      required: ["example_field"],
    }
    setJsonText(JSON.stringify(defaults, null, 2))
    setJsonError(null)
    setActiveMode("json")
    toast.info("Default template loaded — edit it to match your skill")
  }

  return (
    <div className="space-y-3 rounded-lg border bg-card p-3">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">{label}</Label>
        {hasSchema ? (
          <Tabs
            value={activeMode}
            onValueChange={(v) => setActiveMode(v as "visual" | "json")}
            className="w-auto"
          >
            <TabsList className="h-6 gap-0 p-0.5">
              <TabsTrigger value="visual" className="h-5 text-[10px] px-1.5">
                Visual
              </TabsTrigger>
              <TabsTrigger value="json" className="h-5 text-[10px] px-1.5">
                JSON
              </TabsTrigger>
            </TabsList>
          </Tabs>
        ) : null}
      </div>

      {activeMode === "visual" && hasSchema ? (
        <VisualSchemaEditor
          schema={value}
          onChange={onChange}
          readOnly={readOnly}
        />
      ) : (
        <div className="space-y-2">
          <Textarea
            value={jsonText}
            onChange={(e) => handleJsonChange(e.target.value)}
            rows={10}
            spellCheck={false}
            className={cn(
              "font-mono text-xs",
              jsonError ? "border-destructive" : "",
            )}
            placeholder='{"type": "object", "properties": {}}'
            disabled={readOnly}
          />
          {jsonError ? (
            <p className="flex items-center gap-1.5 text-xs text-destructive">
              <AlertCircleIcon className="size-3" /> {jsonError}
            </p>
          ) : (
            <p className="text-[10px] text-muted-foreground">
              Edit the JSON schema directly. Click "Apply" when done.
            </p>
          )}
          <div className="flex items-center gap-1.5">
            {!hasSchema && !readOnly ? (
              <Button
                variant="outline"
                size="sm"
                onClick={handleLoadDefault}
                className="h-6 gap-1 px-1.5 text-[10px]"
              >
                Load default template
              </Button>
            ) : null}
            {hasSchema && !readOnly ? (
              <Button
                size="sm"
                onClick={handleCommit}
                disabled={!!jsonError}
                className="h-6 gap-1 px-1.5 text-[10px]"
              >
                <CheckCircle2Icon className="size-3" /> Apply
              </Button>
            ) : null}
          </div>
        </div>
      )}

      {!hasSchema && !readOnly ? (
        <div className="flex items-center justify-between rounded-md border border-dashed bg-muted/30 p-2">
          <p className="text-[11px] text-muted-foreground">
            No schema defined yet. Add a template to enable form-based input.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadDefault}
            className="h-6 gap-1 px-1.5 text-[10px]"
          >
            <PlusIcon className="size-3" /> Add template
          </Button>
        </div>
      ) : null}
    </div>
  )
}

/**
 * Visual editor for a JSON schema object with type properties.
 */
function VisualSchemaEditor({
  schema,
  onChange,
  readOnly,
}: {
  schema: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  readOnly?: boolean
}) {
  const properties = (schema.properties as Record<string, unknown>) ?? {}
  const required = Array.isArray(schema.required) ? schema.required : []

  function updateProperty(name: string, updates: Record<string, unknown>) {
    const next = {
      ...schema,
      properties: {
        ...properties,
        [name]: {
          ...(properties[name] as Record<string, unknown>),
          ...updates,
        },
      },
    }
    onChange(next)
  }

  function addProperty() {
    const name = prompt("Property name:")
    if (!name || name.trim() === "") return
    const trimmed = name.trim()
    if (properties[trimmed]) {
      toast.error("Property already exists")
      return
    }
    updateProperty(trimmed, {
      type: "string",
      description: "",
    })
    toast.success(`Property "${trimmed}" added`)
  }

  function removeProperty(name: string) {
    if (!confirm(`Remove property "${name}"?`)) return
    const nextProps = { ...properties }
    delete nextProps[name]
    updateProperty(name, {})
    // Actually remove it
    const finalNext = {
      ...schema,
      properties: nextProps,
      required: required.filter((r) => r !== name),
    }
    onChange(finalNext)
    toast.success(`Property "${name}" removed`)
  }

  function updateRequired(next: string[]) {
    onChange({ ...schema, required: next })
  }

  return (
    <div className="space-y-3">
      {/* Top-level schema controls */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Label className="text-[11px]">Type:</Label>
          <span className="text-[11px] font-mono text-muted-foreground">
            {String(schema.type ?? "object")}
          </span>
        </div>
      </div>

      {/* Properties list */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs">Properties</Label>
          {!readOnly ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={addProperty}
              className="h-6 gap-1 px-1.5 text-[10px] text-muted-foreground"
            >
              <PlusIcon className="size-3" /> Add
            </Button>
          ) : null}
        </div>

        {Object.keys(properties).length === 0 ? (
          <p className="rounded-md border border-dashed bg-muted/30 p-2 text-center text-[11px] text-muted-foreground">
            No properties defined. Click "Add" to create a new property.
          </p>
        ) : (
          <div className="space-y-2">
            {Object.entries(properties).map(([name, propSchema]) => {
              const ps = propSchema as Record<string, unknown>
              const isRequired = required.includes(name)
              return (
                <div
                  key={name}
                  className="rounded-md border bg-background p-2 space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-medium">{name}</span>
                    {!readOnly ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeProperty(name)}
                        className="h-5 gap-0.5 px-1 text-[10px] text-destructive"
                      >
                        <Trash2Icon className="size-3" />
                      </Button>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <Label className="text-[10px]">Type:</Label>
                    {!readOnly ? (
                      <select
                        value={String(ps.type ?? "string")}
                        onChange={(e) =>
                          updateProperty(name, { type: e.target.value })
                        }
                        className="h-6 rounded border bg-transparent px-1 text-[10px]"
                      >
                        <option value="string">string</option>
                        <option value="integer">integer</option>
                        <option value="number">number</option>
                        <option value="boolean">boolean</option>
                        <option value="array">array</option>
                        <option value="object">object</option>
                      </select>
                    ) : (
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {String(ps.type ?? "string")}
                      </span>
                    )}
                    <div className="flex items-center gap-1">
                      <Switch
                        checked={isRequired}
                        onCheckedChange={(checked) => {
                          const nextRequired = checked
                            ? [...required, name]
                            : required.filter((r) => r !== name)
                          updateRequired(nextRequired)
                        }}
                        disabled={readOnly}
                      />
                      <span className="text-[10px] text-muted-foreground">
                        required
                      </span>
                    </div>
                  </div>
                  {!readOnly ? (
                    <Input
                      value={String(ps.description ?? "")}
                      onChange={(e) =>
                        updateProperty(name, { description: e.target.value })
                      }
                      placeholder="Field description"
                      className="h-6 text-[10px]"
                    />
                  ) : (
                    ps.description ? (
                      <p className="text-[10px] text-muted-foreground">
                        {String(ps.description)}
                      </p>
                    ) : null)
                  }
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}