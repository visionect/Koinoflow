import * as React from "react"
import {
  AlertCircleIcon,
  BracesIcon,
  EraserIcon,
  FormInputIcon,
  RotateCcwIcon,
  WandSparklesIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

type JsonSchema = Record<string, unknown>

export type InputsFormValue = Record<string, unknown>

export type InputsFormHandle = {
  /** Read the current value as plain JSON. Returns null if invalid (errors are surfaced). */
  serialize: () => InputsFormValue | null
  /** Reset back to schema defaults / empty object. */
  reset: () => void
  /** Replace the current value (e.g., "rerun with same inputs"). */
  setValue: (value: InputsFormValue) => void
}

type FieldKind =
  | "string"
  | "string-enum"
  | "number"
  | "integer"
  | "boolean"
  | "string-array"
  | "json"

type FieldDescriptor = {
  name: string
  required: boolean
  description?: string
  kind: FieldKind
  enumValues?: string[]
  placeholder?: string
  example?: unknown
  defaultValue?: unknown
  schema: JsonSchema
}

function pickKind(schema: JsonSchema): FieldKind {
  const type = schema.type
  const enumValues = Array.isArray(schema.enum) ? (schema.enum as unknown[]) : null
  if (type === "string" && enumValues && enumValues.every((v) => typeof v === "string")) {
    return "string-enum"
  }
  if (type === "string") return "string"
  if (type === "integer") return "integer"
  if (type === "number") return "number"
  if (type === "boolean") return "boolean"
  if (type === "array") {
    const items = (schema.items as JsonSchema | undefined) ?? {}
    if (items.type === "string") return "string-array"
    return "json"
  }
  return "json"
}

function describeFields(schema: JsonSchema | undefined | null): FieldDescriptor[] | null {
  if (!schema || typeof schema !== "object") return null
  if (schema.type !== "object") return null
  const properties = schema.properties as Record<string, JsonSchema> | undefined
  if (!properties || typeof properties !== "object") return null

  const required = Array.isArray(schema.required) ? (schema.required as string[]) : []
  const fields: FieldDescriptor[] = []
  for (const [name, fieldSchema] of Object.entries(properties)) {
    const kind = pickKind(fieldSchema)
    fields.push({
      name,
      required: required.includes(name),
      description:
        typeof fieldSchema.description === "string" ? fieldSchema.description : undefined,
      kind,
      enumValues: Array.isArray(fieldSchema.enum)
        ? (fieldSchema.enum as unknown[]).filter((v): v is string => typeof v === "string")
        : undefined,
      placeholder: typeof fieldSchema.examples === "object" ? undefined : undefined,
      example: Array.isArray(fieldSchema.examples)
        ? (fieldSchema.examples as unknown[])[0]
        : undefined,
      defaultValue: fieldSchema.default,
      schema: fieldSchema,
    })
  }
  return fields
}

function emptyInitial(fields: FieldDescriptor[] | null): InputsFormValue {
  const out: InputsFormValue = {}
  if (!fields) return out
  for (const f of fields) {
    if (f.defaultValue !== undefined) {
      out[f.name] = f.defaultValue
    }
  }
  return out
}

function buildExample(fields: FieldDescriptor[] | null): InputsFormValue {
  const out: InputsFormValue = {}
  if (!fields) return out
  for (const f of fields) {
    if (f.example !== undefined) {
      out[f.name] = f.example
      continue
    }
    if (f.defaultValue !== undefined) {
      out[f.name] = f.defaultValue
      continue
    }
    if (!f.required) continue
    switch (f.kind) {
      case "string":
        out[f.name] = ""
        break
      case "string-enum":
        out[f.name] = f.enumValues?.[0] ?? ""
        break
      case "integer":
      case "number":
        out[f.name] = 0
        break
      case "boolean":
        out[f.name] = false
        break
      case "string-array":
        out[f.name] = []
        break
      case "json":
      default:
        out[f.name] = null
    }
  }
  return out
}

type FieldErrors = Record<string, string>

function validateAgainstSchema(
  value: InputsFormValue,
  fields: FieldDescriptor[] | null,
): FieldErrors {
  const errors: FieldErrors = {}
  if (!fields) return errors
  for (const f of fields) {
    const v = value[f.name]
    const present = v !== undefined && v !== null && !(typeof v === "string" && v === "")
    if (f.required && !present) {
      errors[f.name] = "Required"
      continue
    }
    if (!present) continue
    switch (f.kind) {
      case "integer":
        if (typeof v !== "number" || !Number.isFinite(v) || !Number.isInteger(v)) {
          errors[f.name] = "Must be an integer"
        }
        break
      case "number":
        if (typeof v !== "number" || !Number.isFinite(v)) {
          errors[f.name] = "Must be a number"
        }
        break
      case "boolean":
        if (typeof v !== "boolean") errors[f.name] = "Must be true or false"
        break
      case "string":
        if (typeof v !== "string") errors[f.name] = "Must be a string"
        break
      case "string-enum":
        if (typeof v !== "string" || !(f.enumValues ?? []).includes(v)) {
          errors[f.name] = "Must be one of the allowed values"
        }
        break
      case "string-array":
        if (!Array.isArray(v) || !v.every((item) => typeof item === "string")) {
          errors[f.name] = "Must be a list of strings"
        }
        break
    }
  }
  return errors
}

function tryParseJson(text: string): { ok: true; value: unknown } | { ok: false; error: string } {
  if (text.trim() === "") return { ok: true, value: {} }
  try {
    return { ok: true, value: JSON.parse(text) as unknown }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Invalid JSON" }
  }
}

export const InputsForm = React.forwardRef<
  InputsFormHandle,
  {
    schema: JsonSchema | undefined | null
    initial?: InputsFormValue
    disabled?: boolean
    onChange?: (value: InputsFormValue, hasErrors: boolean) => void
  }
>(function InputsForm({ schema, initial, disabled, onChange }, ref) {
  const fields = React.useMemo(() => describeFields(schema), [schema])
  const hasFormSupport = fields !== null && fields.length > 0

  const [mode, setMode] = React.useState<"form" | "json">(hasFormSupport ? "form" : "json")
  const [value, setValue] = React.useState<InputsFormValue>(
    () => initial ?? emptyInitial(fields),
  )
  const [jsonText, setJsonText] = React.useState<string>(() =>
    JSON.stringify(initial ?? emptyInitial(fields), null, 2),
  )
  const [jsonError, setJsonError] = React.useState<string | null>(null)
  const [touched, setTouched] = React.useState<Record<string, boolean>>({})

  React.useEffect(() => {
    // If schema-supportedness changes, drop into JSON mode if we lost it.
    if (!hasFormSupport && mode === "form") {
      setMode("json")
    }
  }, [hasFormSupport, mode])

  const fieldErrors = React.useMemo(
    () => validateAgainstSchema(value, fields),
    [value, fields],
  )
  const hasErrors = mode === "json" ? jsonError !== null : Object.keys(fieldErrors).length > 0

  React.useEffect(() => {
    onChange?.(value, hasErrors)
  }, [value, hasErrors, onChange])

  React.useImperativeHandle(
    ref,
    (): InputsFormHandle => ({
      serialize: () => {
        if (mode === "json") {
          const parsed = tryParseJson(jsonText)
          if (!parsed.ok) {
            setJsonError(parsed.error)
            return null
          }
          if (typeof parsed.value !== "object" || parsed.value === null || Array.isArray(parsed.value)) {
            setJsonError("Inputs must be a JSON object")
            return null
          }
          return parsed.value as InputsFormValue
        }
        if (Object.keys(fieldErrors).length > 0) {
          // mark all required fields touched so errors render
          const allTouched: Record<string, boolean> = {}
          for (const k of Object.keys(fieldErrors)) allTouched[k] = true
          setTouched((prev) => ({ ...prev, ...allTouched }))
          return null
        }
        // Strip empty optional strings from output
        const cleaned: InputsFormValue = {}
        for (const f of fields ?? []) {
          const v = value[f.name]
          if (v === undefined) continue
          if (!f.required && v === "") continue
          cleaned[f.name] = v
        }
        return cleaned
      },
      reset: () => {
        const next = emptyInitial(fields)
        setValue(next)
        setJsonText(JSON.stringify(next, null, 2))
        setJsonError(null)
        setTouched({})
      },
      setValue: (next) => {
        setValue(next)
        setJsonText(JSON.stringify(next, null, 2))
        setJsonError(null)
      },
    }),
    [mode, jsonText, fieldErrors, fields, value],
  )

  function updateField(name: string, next: unknown) {
    setValue((prev) => {
      const updated = { ...prev, [name]: next }
      setJsonText(JSON.stringify(updated, null, 2))
      return updated
    })
  }

  function handleJsonChange(text: string) {
    setJsonText(text)
    const parsed = tryParseJson(text)
    if (!parsed.ok) {
      setJsonError(parsed.error)
      return
    }
    if (typeof parsed.value !== "object" || parsed.value === null || Array.isArray(parsed.value)) {
      setJsonError("Inputs must be a JSON object")
      return
    }
    setJsonError(null)
    setValue(parsed.value as InputsFormValue)
  }

  function handleFormatJson() {
    const parsed = tryParseJson(jsonText)
    if (!parsed.ok) {
      setJsonError(parsed.error)
      return
    }
    setJsonText(JSON.stringify(parsed.value, null, 2))
    setJsonError(null)
  }

  function handleLoadExample() {
    const example = buildExample(fields)
    setValue(example)
    setJsonText(JSON.stringify(example, null, 2))
    setJsonError(null)
  }

  function handleClear() {
    setValue({})
    setJsonText("{}")
    setJsonError(null)
    setTouched({})
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-sm font-medium">Inputs</Label>
        <div className="flex items-center gap-1">
          {hasFormSupport ? (
            <Tabs
              value={mode}
              onValueChange={(v) => setMode(v as "form" | "json")}
              className="w-auto"
            >
              <TabsList className="h-7 gap-0 p-0.5">
                <TabsTrigger value="form" className="h-6 gap-1 px-2 text-xs">
                  <FormInputIcon className="size-3" /> Form
                </TabsTrigger>
                <TabsTrigger value="json" className="h-6 gap-1 px-2 text-xs">
                  <BracesIcon className="size-3" /> JSON
                </TabsTrigger>
              </TabsList>
            </Tabs>
          ) : (
            <span className="rounded-md bg-muted px-2 py-1 text-[11px] text-muted-foreground">
              No schema – JSON only
            </span>
          )}
        </div>
      </div>

      {mode === "form" && hasFormSupport ? (
        <div className="space-y-3">
          {fields?.map((field) => (
            <FieldControl
              key={field.name}
              field={field}
              value={value[field.name]}
              error={touched[field.name] ? fieldErrors[field.name] : undefined}
              disabled={disabled}
              onChange={(next) => updateField(field.name, next)}
              onBlur={() => setTouched((prev) => ({ ...prev, [field.name]: true }))}
            />
          ))}
          {fields && fields.length === 0 ? (
            <p className="rounded-md border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground">
              The skill's input schema declares no properties. Use JSON mode to send raw input.
            </p>
          ) : null}
        </div>
      ) : (
        <div className="space-y-1.5">
          <Textarea
            value={jsonText}
            onChange={(event) => handleJsonChange(event.target.value)}
            disabled={disabled}
            rows={8}
            spellCheck={false}
            className={cn(
              "font-mono text-xs",
              jsonError ? "border-destructive focus-visible:ring-destructive/30" : "",
            )}
            placeholder='{"customer_id": "cus_123"}'
          />
          {jsonError ? (
            <p className="flex items-center gap-1.5 text-xs text-destructive">
              <AlertCircleIcon className="size-3" /> {jsonError}
            </p>
          ) : null}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          onClick={handleLoadExample}
          disabled={disabled}
        >
          <WandSparklesIcon className="size-3" /> Load example
        </Button>
        {mode === "json" ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={handleFormatJson}
            disabled={disabled || jsonText.trim() === ""}
          >
            <RotateCcwIcon className="size-3" /> Format
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 text-xs text-muted-foreground"
          onClick={handleClear}
          disabled={disabled}
        >
          <EraserIcon className="size-3" /> Clear
        </Button>
      </div>
    </div>
  )
})

function FieldControl({
  field,
  value,
  error,
  disabled,
  onChange,
  onBlur,
}: {
  field: FieldDescriptor
  value: unknown
  error?: string
  disabled?: boolean
  onChange: (next: unknown) => void
  onBlur: () => void
}) {
  const id = `inputs-${field.name}`
  const labelNode = (
    <div className="flex items-baseline justify-between gap-2">
      <Label htmlFor={id} className="text-xs font-medium">
        {field.name}
        {field.required ? <span className="ml-0.5 text-destructive">*</span> : null}
      </Label>
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {field.kind === "string-enum" ? "enum" : field.kind}
      </span>
    </div>
  )

  let control: React.ReactNode = null

  switch (field.kind) {
    case "string":
      control = (
        <Input
          id={id}
          value={typeof value === "string" ? value : ""}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
          disabled={disabled}
          placeholder={
            typeof field.example === "string" ? field.example : field.placeholder ?? ""
          }
          className={cn("h-8 text-sm", error ? "border-destructive" : "")}
        />
      )
      break
    case "string-enum":
      control = (
        <Select
          value={typeof value === "string" ? value : ""}
          onValueChange={(next) => {
            onChange(next)
            onBlur()
          }}
          disabled={disabled}
        >
          <SelectTrigger id={id} className={cn("h-8 text-sm", error ? "border-destructive" : "")}>
            <SelectValue placeholder="Choose…" />
          </SelectTrigger>
          <SelectContent>
            {(field.enumValues ?? []).map((v) => (
              <SelectItem key={v} value={v} className="text-sm">
                {v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
      break
    case "integer":
    case "number":
      control = (
        <Input
          id={id}
          type="number"
          step={field.kind === "integer" ? 1 : "any"}
          value={typeof value === "number" ? value : ""}
          onChange={(event) => {
            const raw = event.target.value
            if (raw === "") {
              onChange(undefined)
              return
            }
            const num = field.kind === "integer" ? parseInt(raw, 10) : parseFloat(raw)
            onChange(Number.isNaN(num) ? raw : num)
          }}
          onBlur={onBlur}
          disabled={disabled}
          className={cn("h-8 text-sm", error ? "border-destructive" : "")}
        />
      )
      break
    case "boolean":
      control = (
        <div className="flex h-8 items-center gap-2 rounded-md border bg-background px-2.5">
          <Switch
            id={id}
            checked={value === true}
            onCheckedChange={(checked) => {
              onChange(checked)
              onBlur()
            }}
            disabled={disabled}
          />
          <span className="text-xs text-muted-foreground">{value === true ? "true" : "false"}</span>
        </div>
      )
      break
    case "string-array": {
      const text = Array.isArray(value) ? (value as string[]).join("\n") : ""
      control = (
        <Textarea
          id={id}
          value={text}
          onChange={(event) =>
            onChange(
              event.target.value
                .split("\n")
                .map((line) => line.trim())
                .filter((line) => line.length > 0),
            )
          }
          onBlur={onBlur}
          disabled={disabled}
          rows={3}
          spellCheck={false}
          className={cn(
            "min-h-[60px] font-mono text-xs",
            error ? "border-destructive" : "",
          )}
          placeholder="One item per line"
        />
      )
      break
    }
    case "json":
    default: {
      const text =
        value === undefined ? "" : typeof value === "string" ? value : JSON.stringify(value, null, 2)
      control = (
        <Textarea
          id={id}
          value={text}
          onChange={(event) => {
            const raw = event.target.value
            if (raw.trim() === "") {
              onChange(undefined)
              return
            }
            try {
              onChange(JSON.parse(raw))
            } catch {
              onChange(raw)
            }
          }}
          onBlur={onBlur}
          disabled={disabled}
          rows={4}
          spellCheck={false}
          className={cn(
            "min-h-[80px] font-mono text-xs",
            error ? "border-destructive" : "",
          )}
          placeholder="JSON value"
        />
      )
    }
  }

  return (
    <div className="space-y-1">
      {labelNode}
      {control}
      {field.description ? (
        <p className="text-[11px] text-muted-foreground">{field.description}</p>
      ) : null}
      {error ? (
        <p className="flex items-center gap-1 text-[11px] text-destructive">
          <AlertCircleIcon className="size-3" /> {error}
        </p>
      ) : null}
    </div>
  )
}
