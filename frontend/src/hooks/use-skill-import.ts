import * as React from "react"

import { toast } from "sonner"

import { parseSkillMd, serializeFrontmatter } from "@/lib/frontmatter"
import {
  EMPTY_KOINOFLOW_METADATA,
  type KoinoflowMetadata,
  type ProcessFrontmatter,
  type RiskLevel,
  type VersionFileInput,
} from "@/types"

export interface SkillImportData {
  title: string
  description: string
  contentMd: string
  frontmatterYaml: string
  frontmatter: ProcessFrontmatter
  supportFiles: VersionFileInput[]
  koinoflowMetadata: KoinoflowMetadata
}

const KOINOFLOW_METADATA_SIDECAR = "koinoflow-metadata.json"
const VALID_RISK_LEVELS: RiskLevel[] = ["low", "medium", "high", "critical"]

function parseKoinoflowMetadata(raw: string): KoinoflowMetadata {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>
    const stringArray = (value: unknown): string[] =>
      Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []

    const riskRaw = data.risk_level
    const risk =
      typeof riskRaw === "string" && VALID_RISK_LEVELS.includes(riskRaw as RiskLevel)
        ? (riskRaw as RiskLevel)
        : null

    return {
      retrieval_keywords: stringArray(data.retrieval_keywords),
      risk_level: risk,
      requires_human_approval: data.requires_human_approval === true,
      prerequisites: stringArray(data.prerequisites),
      audience: stringArray(data.audience),
    }
  } catch {
    return { ...EMPTY_KOINOFLOW_METADATA }
  }
}

const EXT_TO_FILE_TYPE: Record<string, string> = {
  py: "python",
  md: "markdown",
  html: "html",
  htm: "html",
  yaml: "yaml",
  yml: "yaml",
  js: "javascript",
  ts: "typescript",
  sh: "shell",
}

function detectFileType(filename: string): string {
  const ext = filename.includes(".") ? (filename.split(".").pop()?.toLowerCase() ?? "") : ""
  return EXT_TO_FILE_TYPE[ext] ?? "text"
}

export function useSkillImport(onImport: (data: SkillImportData) => void) {
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  function openFilePicker() {
    fileInputRef.current?.click()
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      let parsed: { frontmatter: ProcessFrontmatter; content: string }
      let supportFiles: VersionFileInput[] = []

      let koinoflowMetadata: KoinoflowMetadata = { ...EMPTY_KOINOFLOW_METADATA }

      if (file.name.endsWith(".skill") || file.name.endsWith(".zip")) {
        const JSZip = (await import("jszip")).default
        const zip = await JSZip.loadAsync(file)
        let skillMdContent: string | null = null

        for (const [path, zipEntry] of Object.entries(zip.files)) {
          if (zipEntry.dir) continue

          const parts = path.split("/")
          const relPath = parts.length > 1 ? parts.slice(1).join("/") : path

          if (path.endsWith("SKILL.md")) {
            skillMdContent = await zipEntry.async("text")
          } else if (relPath === KOINOFLOW_METADATA_SIDECAR) {
            const raw = await zipEntry.async("text")
            koinoflowMetadata = parseKoinoflowMetadata(raw)
          } else if (relPath) {
            const content = await zipEntry.async("text")
            supportFiles.push({
              path: relPath,
              content,
              file_type: detectFileType(relPath),
            })
          }
        }

        if (!skillMdContent) {
          toast.error("No SKILL.md found in the archive")
          return
        }

        parsed = parseSkillMd(skillMdContent)
      } else {
        const text = await file.text()
        parsed = parseSkillMd(text)
        supportFiles = []
      }

      onImport({
        title: parsed.frontmatter.name || "",
        description: parsed.frontmatter.description || "",
        contentMd: parsed.content,
        frontmatterYaml: serializeFrontmatter(parsed.frontmatter),
        frontmatter: parsed.frontmatter,
        supportFiles,
        koinoflowMetadata,
      })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to import file")
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const fileInput = React.createElement("input", {
    ref: fileInputRef,
    type: "file",
    accept: ".skill,.zip,.md",
    className: "hidden",
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => void handleFileChange(event),
  })

  return { fileInput, openFilePicker }
}
