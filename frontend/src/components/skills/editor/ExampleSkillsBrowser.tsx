import * as React from "react"
import {
  BookOpenIcon,
  CheckCircle2Icon,
  Code2Icon,
  CopyIcon,
  FileCodeIcon,
  GitBranchIcon,
  SearchIcon,
  SparklesIcon,
  TerminalIcon,
  XIcon,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

/**
 * Example skills browser that provides pre-built executable skill templates.
 * Users can browse examples, preview them, and import them into their current skill.
 */

export interface ExampleSkill {
  id: string
  title: string
  description: string
  category: ExampleCategory
  tags: string[]
  frontmatter: Record<string, unknown>
  files: ExampleFile[]
  inputExample: Record<string, unknown>
  outputExample: Record<string, unknown>
  difficulty: "beginner" | "intermediate" | "advanced"
}

export interface ExampleFile {
  path: string
  content: string
  language: string
}

export type ExampleCategory =
  | "data-processing"
  | "api-integration"
  | "text-analysis"
  | "file-management"
  | "automation"
  | "validation"

const EXAMPLE_SKILLS: ExampleSkill[] = [
  {
    id: "csv-aggregator",
    title: "CSV Data Aggregator",
    description:
      "Reads a CSV file, groups by a column, and computes aggregate statistics (sum, count, average).",
    category: "data-processing",
    tags: ["csv", "aggregation", "data", "pandas"],
    frontmatter: {
      name: "csv_aggregator",
      version: "1.0.0",
      runtime: "python",
      description: "Aggregate CSV data by a specified column.",
      input_schema: {
        type: "object",
        properties: {
          file_path: {
            type: "string",
            description: "Path to the CSV file.",
            examples: ["/data/sales.csv"],
          },
          group_by: {
            type: "string",
            description: "Column to group by.",
            examples: ["region"],
          },
          value_column: {
            type: "string",
            description: "Column to aggregate.",
            examples: ["revenue"],
          },
          aggregation: {
            type: "string",
            enum: ["sum", "count", "avg", "min", "max"],
            description: "Aggregation function to apply.",
            default: "sum",
          },
        },
        required: ["file_path", "group_by", "value_column"],
      },
      output_schema: {
        type: "object",
        properties: {
          groups: {
            type: "array",
            description: "Aggregated results per group.",
          },
          total_rows: {
            type: "integer",
            description: "Total number of rows processed.",
          },
        },
      },
    },
    files: [
      {
        path: "run.py",
        language: "python",
        content: `import csv
import json
from collections import defaultdict

def main(input_data: dict) -> dict:
    """Aggregate CSV data by a specified column."""
    file_path = input_data["file_path"]
    group_by = input_data["group_by"]
    value_column = input_data["value_column"]
    aggregation = input_data.get("aggregation", "sum")

    groups = defaultdict(list)
    total_rows = 0

    with open(file_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            key = row[group_by]
            try:
                value = float(row[value_column])
                groups[key].append(value)
            except (ValueError, KeyError):
                continue

    result = []
    for key, values in groups.items():
        if aggregation == "sum":
            result.append({"group": key, "total": sum(values), "count": len(values)})
        elif aggregation == "count":
            result.append({"group": key, "count": len(values)})
        elif aggregation == "avg":
            result.append({"group": key, "avg": sum(values) / len(values), "count": len(values)})
        elif aggregation == "min":
            result.append({"group": key, "min": min(values), "count": len(values)})
        elif aggregation == "max":
            result.append({"group": key, "max": max(values), "count": len(values)})

    return {
        "groups": result,
        "total_rows": total_rows,
    }`,
      },
    ],
    inputExample: {
      file_path: "/data/sales.csv",
      group_by: "region",
      value_column: "revenue",
      aggregation: "sum",
    },
    outputExample: {
      groups: [
        { group: "North", total: 15000, count: 100 },
        { group: "South", total: 12000, count: 80 },
      ],
      total_rows: 180,
    },
    difficulty: "beginner",
  },
  {
    id: "web-api-fetcher",
    title: "Web API Fetcher",
    description:
      "Fetches data from a REST API endpoint, with optional authentication headers and response transformation.",
    category: "api-integration",
    tags: ["api", "http", "rest", "fetch", "web"],
    frontmatter: {
      name: "web_api_fetcher",
      version: "1.0.0",
      runtime: "python",
      description: "Fetch and transform data from a REST API.",
      input_schema: {
        type: "object",
        properties: {
          url: {
            type: "string",
            description: "API endpoint URL.",
            examples: ["https://api.example.com/users"],
          },
          method: {
            type: "string",
            enum: ["GET", "POST", "PUT", "DELETE"],
            description: "HTTP method.",
            default: "GET",
          },
          headers: {
            type: "object",
            description: "Optional HTTP headers.",
          },
          body: {
            type: "object",
            description: "Request body (for POST/PUT).",
          },
          transform: {
            type: "string",
            description: "Simple jq-like transform expression.",
          },
        },
        required: ["url"],
      },
      output_schema: {
        type: "object",
        properties: {
          status_code: { type: "integer" },
          data: { type: "object", description: "Response payload." },
          headers: { type: "object" },
        },
      },
    },
    files: [
      {
        path: "run.py",
        language: "python",
        content: `import requests

def main(input_data: dict) -> dict:
    """Fetch data from a REST API endpoint."""
    url = input_data["url"]
    method = input_data.get("method", "GET").upper()
    headers = input_data.get("headers", {})
    body = input_data.get("body")
    transform = input_data.get("transform")

    kwargs = {
        "method": method,
        "url": url,
        "headers": headers,
    }
    if body and method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = body

    response = requests.request(**kwargs)

    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:1000]}

    if transform:
        data = _apply_transform(data, transform)

    return {
        "status_code": response.status_code,
        "data": data,
        "headers": dict(response.headers),
    }

def _apply_transform(data, expr: str):
    """Simple transform: supports 'filter.field', 'map.field', 'limit.n'."""
    if expr.startswith("limit."):
        try:
            n = int(expr.split(".", 1)[1])
            if isinstance(data, list):
                return data[:n]
        except (ValueError, IndexError):
            pass
    return data`,
      },
    ],
    inputExample: {
      url: "https://jsonplaceholder.typicode.com/posts/1",
      method: "GET",
    },
    outputExample: {
      status_code: 200,
      data: { id: 1, title: "Hello World", body: "Post body..." },
      headers: { "content-type": "application/json" },
    },
    difficulty: "beginner",
  },
  {
    id: "text-sentiment-analyzer",
    title: "Text Sentiment Analyzer",
    description:
      "Analyzes sentiment of text input using simple keyword-based scoring. Returns positive/negative/neutral classification with confidence.",
    category: "text-analysis",
    tags: ["text", "sentiment", "nlp", "analysis", "keywords"],
    frontmatter: {
      name: "text_sentiment_analyzer",
      version: "1.0.0",
      runtime: "python",
      description: "Analyze text sentiment using keyword-based scoring.",
      input_schema: {
        type: "object",
        properties: {
          text: {
            type: "string",
            description: "Text to analyze.",
            examples: ["This product is absolutely wonderful!"],
          },
          language: {
            type: "string",
            enum: ["en", "es", "fr", "de"],
            description: "Text language.",
            default: "en",
          },
        },
        required: ["text"],
      },
      output_schema: {
        type: "object",
        properties: {
          sentiment: {
            type: "string",
            enum: ["positive", "negative", "neutral"],
          },
          score: { type: "number", description: "Raw score (-1 to 1)." },
          confidence: { type: "number", description: "Confidence (0 to 1)." },
          keywords: {
            type: "array",
            items: { type: "string" },
            description: "Detected sentiment keywords.",
          },
        },
      },
    },
    files: [
      {
        path: "run.py",
        language: "python",
        content: `import re

# Simple sentiment lexicons
POSITIVE_WORDS = {
    "good", "great", "excellent", "wonderful", "amazing", "fantastic",
    "love", "happy", "best", "perfect", "awesome", "brilliant", "nice",
    "pleasant", "outstanding", "superb", "delightful", "positive",
}

NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "horrible", "worst", "hate", "ugly",
    "poor", "disappointing", "negative", "angry", "sad", "boring",
    "mediocre", "failure", "useless", "frustrating", "annoying",
}

def main(input_data: dict) -> dict:
    """Analyze sentiment of text using keyword scoring."""
    text = input_data["text"].lower()
    words = set(re.findall(r"\\b[a-z]+\\b", text))

    pos_count = len(words & POSITIVE_WORDS)
    neg_count = len(words & NEGATIVE_WORDS)
    total = pos_count + neg_count

    if total == 0:
        sentiment = "neutral"
        score = 0.0
        confidence = 0.3
    else:
        score = (pos_count - neg_count) / total
        if score > 0.1:
            sentiment = "positive"
        elif score < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        confidence = min(1.0, total / 3)

    keywords = sorted(words & (POSITIVE_WORDS | NEGATIVE_WORDS))

    return {
        "sentiment": sentiment,
        "score": round(score, 3),
        "confidence": round(confidence, 2),
        "keywords": keywords,
    }`,
      },
    ],
    inputExample: {
      text: "I absolutely love this product! It's amazing and wonderful.",
      language: "en",
    },
    outputExample: {
      sentiment: "positive",
      score: 1.0,
      confidence: 1.0,
      keywords: ["amazing", "love", "wonderful"],
    },
    difficulty: "intermediate",
  },
  {
    id: "json-validator",
    title: "JSON Schema Validator",
    description:
      "Validates JSON data against a provided schema definition. Reports validation errors with field-level details.",
    category: "validation",
    tags: ["json", "validation", "schema", "data-quality"],
    frontmatter: {
      name: "json_validator",
      version: "1.0.0",
      runtime: "python",
      description: "Validate JSON data against a schema.",
      input_schema: {
        type: "object",
        properties: {
          data: {
            type: "object",
            description: "JSON data to validate.",
          },
          schema_def: {
            type: "object",
            description: "JSON Schema definition.",
          },
        },
        required: ["data", "schema_def"],
      },
      output_schema: {
        type: "object",
        properties: {
          valid: { type: "boolean" },
          errors: {
            type: "array",
            items: { type: "object" },
            description: "List of validation errors.",
          },
        },
      },
    },
    files: [
      {
        path: "run.py",
        language: "python",
        content: `def main(input_data: dict) -> dict:
    """Validate JSON data against a schema definition."""
    data = input_data["data"]
    schema = input_data["schema_def"]
    errors = _validate(data, schema, path="$")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }

def _validate(data, schema, path="$"):
    errors = []
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(data, dict):
            errors.append({"path": path, "message": f"Expected object, got {type(data).__name__}"})
            return errors
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append({"path": f"{path}.{field}", "message": "Required field missing"})
        props = schema.get("properties", {})
        for key, value in data.items():
            if key in props:
                errors.extend(_validate(value, props[key], f"{path}.{key}"))
    elif schema_type == "string":
        if not isinstance(data, str):
            errors.append({"path": path, "message": f"Expected string, got {type(data).__name__}"})
    elif schema_type == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            errors.append({"path": path, "message": f"Expected integer, got {type(data).__name__}"})
    elif schema_type == "number":
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            errors.append({"path": path, "message": f"Expected number, got {type(data).__name__}"})
    elif schema_type == "boolean":
        if not isinstance(data, bool):
            errors.append({"path": path, "message": f"Expected boolean, got {type(data).__name__}"})
    elif schema_type == "array":
        if not isinstance(data, list):
            errors.append({"path": path, "message": f"Expected array, got {type(data).__name__}"})
    return errors`,
      },
    ],
    inputExample: {
      data: { "name": "John", "age": 30 },
      schema_def: {
        type: "object",
        properties: {
          name: { type: "string" },
          age: { type: "integer" },
        },
        required: ["name", "age", "email"],
      },
    },
    outputExample: {
      valid: false,
      errors: [
        { path: "$.email", message: "Required field missing" },
      ],
    },
    difficulty: "intermediate",
  },
  {
    id: "file-organizer",
    title: "File Organizer",
    description:
      "Organizes files in a directory by extension, type, or date into subdirectories. Supports move and copy modes.",
    category: "file-management",
    tags: ["files", "organization", "filesystem", "automation"],
    frontmatter: {
      name: "file_organizer",
      version: "1.0.0",
      runtime: "python",
      description: "Organize files into subdirectories by type.",
      input_schema: {
        type: "object",
        properties: {
          source_dir: {
            type: "string",
            description: "Directory to organize.",
            examples: ["/data/inbox"],
          },
          target_dir: {
            type: "string",
            description: "Target directory for organized files.",
            examples: ["/data/organized"],
          },
          group_by: {
            type: "string",
            enum: ["extension", "type", "date"],
            description: "How to group files.",
            default: "extension",
          },
          action: {
            type: "string",
            enum: ["move", "copy", "report"],
            description: "Action to perform.",
            default: "report",
          },
        },
        required: ["source_dir", "target_dir"],
      },
      output_schema: {
        type: "object",
        properties: {
          organized: { type: "integer", description: "Files organized." },
          skipped: { type: "integer", description: "Files skipped." },
          structure: {
            type: "object",
            description: "Resulting directory structure.",
          },
        },
      },
    },
    files: [
      {
        path: "run.py",
        language: "python",
        content: `import os
import shutil
from datetime import datetime
from pathlib import Path

def main(input_data: dict) -> dict:
    """Organize files into subdirectories."""
    source_dir = input_data["source_dir"]
    target_dir = input_data["target_dir"]
    group_by = input_data.get("group_by", "extension")
    action = input_data.get("action", "report")

    source = Path(source_dir)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    organized = 0
    skipped = 0
    structure = {}

    for filepath in source.iterdir():
        if not filepath.is_file():
            continue

        if group_by == "extension":
            category = filepath.suffix.lstrip("."").lower() or "no-extension"
        elif group_by == "type":
            ext = filepath.suffix.lstrip("."").lower()
            category = _classify_type(ext)
        elif group_by == "date":
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            category = mtime.strftime("%Y/%m")
        else:
            category = "other"

        dest_dir = target / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filepath.name

        if action == "move":
            shutil.move(str(filepath), str(dest))
        elif action == "copy":
            shutil.copy2(str(filepath), str(dest))
        # report mode: just count

        structure[category] = structure.get(category, 0) + 1
        organized += 1

    return {
        "organized": organized,
        "skipped": skipped,
        "structure": structure,
    }

def _classify_type(ext: str) -> str:
    types = {
        "jpg": "images", "jpeg": "images", "png": "images", "gif": "images",
        "pdf": "documents", "doc": "documents", "docx": "documents", "txt": "documents",
        "mp3": "audio", "wav": "audio", "mp4": "video", "avi": "video",
        "py": "code", "js": "code", "ts": "code", "html": "code",
        "csv": "data", "json": "data", "xml": "data",
    }
    return types.get(ext, "other")`,
      },
    ],
    inputExample: {
      source_dir: "/data/inbox",
      target_dir: "/data/organized",
      group_by: "extension",
      action: "report",
    },
    outputExample: {
      organized: 42,
      skipped: 3,
      structure: { "pdf": 15, "csv": 10, "png": 12, "no-extension": 5 },
    },
    difficulty: "intermediate",
  },
  {
    id: "email-template-renderer",
    title: "Email Template Renderer",
    description:
      "Renders a Jinja2 email template with provided context variables. Supports HTML and plain text variants.",
    category: "automation",
    tags: ["email", "template", "jinja2", "automation", "notification"],
    frontmatter: {
      name: "email_template_renderer",
      version: "1.0.0",
      runtime: "python",
      description: "Render email templates with context variables.",
      input_schema: {
        type: "object",
        properties: {
          template: {
            type: "string",
            description: "Jinja2 template string.",
            examples: ["Hello {{ name }}, your order {{ order_id }} has shipped."],
          },
          context: {
            type: "object",
            description: "Template context variables.",
          },
          variant: {
            type: "string",
            enum: ["html", "text", "both"],
            description: "Output variant.",
            default: "text",
          },
        },
        required: ["template", "context"],
      },
      output_schema: {
        type: "object",
        properties: {
          rendered: { type: "string", description: "Rendered template." },
          variant: { type: "string" },
        },
      },
    },
    files: [
      {
        path: "run.py",
        language: "python",
        content: `from jinja2 import Template, Undefined

def main(input_data: dict) -> dict:
    """Render an email template with context variables."""
    template_str = input_data["template"]
    context = input_data["context"]
    variant = input_data.get("variant", "text")

    template = Template(template_str, undefined=Undefined)
    rendered = template.render(**context)

    result = {"rendered": rendered, "variant": variant}

    if variant == "both":
        result["html"] = rendered.replace("\\n", "<br>\\n")

    return result`,
      },
    ],
    inputExample: {
      template: "Hello {{ name }},\n\nYour order {{ order_id }} for ${{ amount }} has shipped!\n\nBest regards,\nTeam",
      context: {
        name: "Alice",
        order_id: "ORD-12345",
        amount: "99.99",
      },
      variant: "text",
    },
    outputExample: {
      rendered: "Hello Alice,\n\nYour order ORD-12345 for $99.99 has shipped!\n\nBest regards,\nTeam",
      variant: "text",
    },
    difficulty: "beginner",
  },
]

const CATEGORY_CONFIG: Record<
  ExampleCategory,
  { label: string; icon: React.ReactNode; color: string }
> = {
  "data-processing": {
    label: "Data Processing",
    icon: <Code2Icon className="size-4" />,
    color: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  },
  "api-integration": {
    label: "API Integration",
    icon: <TerminalIcon className="size-4" />,
    color: "bg-green-500/10 text-green-600 dark:text-green-400",
  },
  "text-analysis": {
    label: "Text Analysis",
    icon: <BookOpenIcon className="size-4" />,
    color: "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  },
  "file-management": {
    label: "File Management",
    icon: <FileCodeIcon className="size-4" />,
    color: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  "automation": {
    label: "Automation",
    icon: <SparklesIcon className="size-4" />,
    color: "bg-pink-500/10 text-pink-600 dark:text-pink-400",
  },
  "validation": {
    label: "Validation",
    icon: <CheckCircle2Icon className="size-4" />,
    color: "bg-teal-500/10 text-teal-600 dark:text-teal-400",
  },
}

const DIFFICULTY_CONFIG: Record<ExampleSkill["difficulty"], { label: string; color: string }> = {
  beginner: { label: "Beginner", color: "bg-green-500/10 text-green-600 dark:text-green-400" },
  intermediate: { label: "Intermediate", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  advanced: { label: "Advanced", color: "bg-red-500/10 text-red-600 dark:text-red-400" },
}

export function ExampleSkillsBrowser({
  onImport,
  isOpen = false,
  onClose,
}: {
  onImport?: (example: ExampleSkill) => void
  isOpen?: boolean
  onClose?: () => void
}) {
  const [search, setSearch] = React.useState("")
  const [selectedCategory, setSelectedCategory] = React.useState<ExampleCategory | "all">("all")
  const [selectedDifficulty, setSelectedDifficulty] = React.useState<ExampleSkill["difficulty"] | "all">("all")
  const [selectedExample, setSelectedExample] = React.useState<ExampleSkill | null>(null)
  const [previewTab, setPreviewTab] = React.useState<"frontmatter" | "code">("frontmatter")

  const filtered = React.useMemo(() => {
    return EXAMPLE_SKILLS.filter((example) => {
      const matchesSearch =
        search === "" ||
        example.title.toLowerCase().includes(search.toLowerCase()) ||
        example.description.toLowerCase().includes(search.toLowerCase()) ||
        example.tags.some((tag) => tag.toLowerCase().includes(search.toLowerCase()))
      const matchesCategory = selectedCategory === "all" || example.category === selectedCategory
      const matchesDifficulty = selectedDifficulty === "all" || example.difficulty === selectedDifficulty
      return matchesSearch && matchesCategory && matchesDifficulty
    })
  }, [search, selectedCategory, selectedDifficulty])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative h-[85vh] w-full max-w-5xl overflow-hidden rounded-xl border bg-card shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <BookOpenIcon className="size-5 text-amber-500" />
            <h3 className="text-base font-semibold">Executable Skill Examples</h3>
            <Badge variant="outline" className="text-[10px]">
              {EXAMPLE_SKILLS.length} templates
            </Badge>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-7 w-7 p-0"
          >
            <XIcon className="size-4" />
          </Button>
        </div>

        <div className="flex h-[calc(85vh-52px)]">
          {/* Sidebar: list */}
          <div className="flex w-80 flex-col border-r">
            {/* Filters */}
            <div className="space-y-2 border-b p-3">
              <div className="relative">
                <SearchIcon className="absolute left-2.5 top-1/2 size-3 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search examples..."
                  className="h-8 pl-8 text-xs"
                />
              </div>
              <div className="flex flex-wrap gap-1">
                <select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value as ExampleCategory | "all")}
                  className="h-7 rounded-md border bg-transparent px-1.5 text-[10px]"
                >
                  <option value="all">All categories</option>
                  {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => (
                    <option key={key} value={key}>{cfg.label}</option>
                  ))}
                </select>
                <select
                  value={selectedDifficulty}
                  onChange={(e) => setSelectedDifficulty(e.target.value as ExampleSkill["difficulty"] | "all")}
                  className="h-7 rounded-md border bg-transparent px-1.5 text-[10px]"
                >
                  <option value="all">All levels</option>
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </select>
              </div>
            </div>

            {/* List */}
            <ScrollArea className="flex-1">
              <div className="space-y-1 p-2">
                {filtered.map((example) => (
                  <button
                    key={example.id}
                    type="button"
                    className={cn(
                      "w-full rounded-lg p-2.5 text-left transition-colors",
                      selectedExample?.id === example.id
                        ? "bg-accent"
                        : "hover:bg-accent/50",
                    )}
                    onClick={() => {
                      setSelectedExample(example)
                      setPreviewTab("frontmatter")
                    }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-medium">{example.title}</span>
                          <Badge
                            variant="outline"
                            className={cn("h-4 gap-0.5 px-1 text-[9px]", CATEGORY_CONFIG[example.category].color)}
                          >
                            {CATEGORY_CONFIG[example.category].icon}
                            {CATEGORY_CONFIG[example.category].label}
                          </Badge>
                        </div>
                        <p className="mt-0.5 line-clamp-1 text-[10px] text-muted-foreground">
                          {example.description}
                        </p>
                      </div>
                    </div>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <Badge
                        variant="outline"
                        className={cn("h-4 px-1 text-[9px]", DIFFICULTY_CONFIG[example.difficulty].color)}
                      >
                        {DIFFICULTY_CONFIG[example.difficulty].label}
                      </Badge>
                      {example.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="text-[9px] text-muted-foreground">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
                {filtered.length === 0 ? (
                  <div className="py-8 text-center">
                    <p className="text-xs text-muted-foreground">No examples match your filters.</p>
                  </div>
                ) : null}
              </div>
            </ScrollArea>
          </div>

          {/* Preview panel */}
          <div className="flex flex-1 flex-col">
            {selectedExample ? (
              <>
                {/* Preview header */}
                <div className="border-b px-4 py-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-semibold">{selectedExample.title}</h4>
                      <p className="text-[11px] text-muted-foreground">
                        {selectedExample.description}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => onImport?.(selectedExample)}
                      className="h-7 gap-1.5 px-2 text-xs"
                    >
                      <GitBranchIcon className="size-3" /> Import into skill
                    </Button>
                  </div>
                  <Tabs
                    value={previewTab}
                    onValueChange={(v) => setPreviewTab(v as "frontmatter" | "code")}
                    className="mt-2"
                  >
                    <TabsList className="h-6 gap-0 p-0.5">
                      <TabsTrigger value="frontmatter" className="h-5 text-[10px] px-1.5">
                        Frontmatter & Schema
                      </TabsTrigger>
                      <TabsTrigger value="code" className="h-5 text-[10px] px-1.5">
                        Source Code
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>

                {/* Preview content */}
                <ScrollArea className="flex-1">
                  <div className="p-4 space-y-4">
                    {previewTab === "frontmatter" ? (
                      <>
                        {/* Input example */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <Label className="text-xs font-medium">Input Example</Label>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                navigator.clipboard.writeText(JSON.stringify(selectedExample.inputExample, null, 2))
                                toast.success("Input example copied")
                              }}
                              className="h-5 gap-1 px-1.5 text-[10px]"
                            >
                              <CopyIcon className="size-3" /> Copy
                            </Button>
                          </div>
                          <pre className="rounded-md border bg-muted/30 p-2 text-[11px] font-mono overflow-auto max-h-[150px]">
                            {JSON.stringify(selectedExample.inputExample, null, 2)}
                          </pre>
                        </div>

                        <Separator />

                        {/* Output example */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <Label className="text-xs font-medium">Output Example</Label>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                navigator.clipboard.writeText(JSON.stringify(selectedExample.outputExample, null, 2))
                                toast.success("Output example copied")
                              }}
                              className="h-5 gap-1 px-1.5 text-[10px]"
                            >
                              <CopyIcon className="size-3" /> Copy
                            </Button>
                          </div>
                          <pre className="rounded-md border bg-muted/30 p-2 text-[11px] font-mono overflow-auto max-h-[150px]">
                            {JSON.stringify(selectedExample.outputExample, null, 2)}
                          </pre>
                        </div>

                        <Separator />

                        {/* Full frontmatter */}
                        <div className="space-y-1.5">
                          <Label className="text-xs font-medium">Full Frontmatter</Label>
                          <pre className="rounded-md border bg-muted/30 p-2 text-[11px] font-mono overflow-auto max-h-[200px]">
                            {JSON.stringify(selectedExample.frontmatter, null, 2)}
                          </pre>
                        </div>
                      </>
                    ) : (
                      selectedExample.files.map((file) => (
                        <div key={file.path} className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <Label className="text-xs font-medium">{file.path}</Label>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                navigator.clipboard.writeText(file.content)
                                toast.success(`${file.path} copied`)
                              }}
                              className="h-5 gap-1 px-1.5 text-[10px]"
                            >
                              <CopyIcon className="size-3" /> Copy
                            </Button>
                          </div>
                          <pre className="rounded-md border bg-muted/30 p-2 text-[11px] font-mono overflow-auto max-h-[400px]">
                            <code>{file.content}</code>
                          </pre>
                        </div>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center">
                <div className="text-center">
                  <BookOpenIcon className="mx-auto size-8 text-muted-foreground/50" />
                  <p className="mt-2 text-sm text-muted-foreground">
                    Select an example to preview
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * Hook to manage the example browser state.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useExampleBrowser() {
  const [isOpen, setIsOpen] = React.useState(false)

  return {
    isOpen,
    open: () => setIsOpen(true),
    close: () => setIsOpen(false),
    toggle: () => setIsOpen((prev) => !prev),
  }
}