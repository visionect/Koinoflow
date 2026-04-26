import * as React from "react"

import { toast } from "sonner"

import { parseSkillMd, serializeFrontmatter } from "@/lib/frontmatter"
import {
  EMPTY_KOINOFLOW_METADATA,
  type KoinoflowMetadata,
  type SkillFrontmatter,
  type RiskLevel,
  type VersionFileInput,
} from "@/types"

export interface SkillImportData {
  title: string
  description: string
  contentMd: string
  frontmatterYaml: string
  frontmatter: SkillFrontmatter
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
  json: "json",
  js: "javascript",
  ts: "typescript",
  sh: "shell",
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  webp: "image",
  svg: "image",
  pdf: "pdf",
}

const TEXT_FILE_TYPES = new Set([
  "python",
  "markdown",
  "html",
  "yaml",
  "json",
  "javascript",
  "typescript",
  "shell",
  "text",
])

function detectFileType(filename: string): string {
  const ext = filename.includes(".") ? (filename.split(".").pop()?.toLowerCase() ?? "") : ""
  return EXT_TO_FILE_TYPE[ext] ?? "binary"
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ""
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

function detectMimeType(filename: string, fileType: string): string {
  const ext = filename.includes(".") ? (filename.split(".").pop()?.toLowerCase() ?? "") : ""
  const byExt: Record<string, string> = {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    gif: "image/gif",
    webp: "image/webp",
    svg: "image/svg+xml",
    pdf: "application/pdf",
    json: "application/json",
    md: "text/markdown",
    html: "text/html",
    htm: "text/html",
    yaml: "application/yaml",
    yml: "application/yaml",
    sh: "text/x-shellscript",
  }
  return byExt[ext] ?? (TEXT_FILE_TYPES.has(fileType) ? "text/plain" : "application/octet-stream")
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
      let parsed: { frontmatter: SkillFrontmatter; content: string }
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
            const fileType = detectFileType(relPath)
            const buffer = await zipEntry.async("arraybuffer")
            const mimeType = detectMimeType(relPath, fileType)
            let isText = TEXT_FILE_TYPES.has(fileType)
            let content: string | null = null
            if (isText) {
              try {
                content = new TextDecoder("utf-8", { fatal: true }).decode(buffer)
              } catch {
                isText = false
              }
            }
            supportFiles.push({
              path: relPath,
              content,
              content_base64: isText ? null : arrayBufferToBase64(buffer),
              file_type: fileType,
              mime_type: mimeType,
              encoding: isText ? "utf-8" : "base64",
              size_bytes: buffer.byteLength,
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
