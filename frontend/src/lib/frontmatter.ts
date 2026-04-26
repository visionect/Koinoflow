import yaml from "js-yaml"

import type { SkillFrontmatter } from "@/types"

/**
 * Parse YAML frontmatter into the SkillFrontmatter shape.
 *
 * All unknown top-level keys (including Claude-compat fields like
 * `allowed-tools`, `model`, `effort`, `paths`, `disable-model-invocation`,
 * `user-invocable`, `argument-hint`) are preserved verbatim on the returned
 * object so they can round-trip through a save cycle unchanged.
 */
export function parseFrontmatter(
  yamlString: string,
  defaults?: Partial<SkillFrontmatter>,
): SkillFrontmatter {
  const fallback: SkillFrontmatter = {
    name: defaults?.name ?? "",
    description: defaults?.description ?? "",
    tags: defaults?.tags ?? [],
  }

  try {
    const parsed = (yaml.load(yamlString) as Record<string, unknown> | null) ?? {}

    return {
      ...parsed,
      name: typeof parsed.name === "string" ? parsed.name : fallback.name,
      description:
        typeof parsed.description === "string" ? parsed.description : fallback.description,
      tags: Array.isArray(parsed.tags)
        ? parsed.tags.filter((value): value is string => typeof value === "string")
        : fallback.tags,
    }
  } catch {
    return fallback
  }
}

/**
 * Serialize a SkillFrontmatter back to YAML.
 *
 * Preserves every key present on the input (including Claude-compat fields and
 * any other unknown keys carried over from import). This is essential for
 * lossless `.skill` round-trip.
 */
export function serializeFrontmatter(frontmatter: SkillFrontmatter) {
  const clean: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(frontmatter)) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value) && value.length === 0) continue
    if (typeof value === "string" && value.length === 0) continue
    clean[key] = value
  }

  return yaml.dump(clean, { lineWidth: -1 }).trim()
}

export function parseSkillMd(fileContent: string): {
  frontmatter: SkillFrontmatter
  content: string
} {
  const fmRegex = /^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/
  const match = fileContent.match(fmRegex)

  if (match?.[1] != null && match[2] != null) {
    return {
      frontmatter: parseFrontmatter(match[1]),
      content: match[2].trim(),
    }
  }

  return {
    frontmatter: parseFrontmatter(""),
    content: fileContent.trim(),
  }
}

export function toSkillMd(frontmatter: SkillFrontmatter, content: string): string {
  const fm = serializeFrontmatter(frontmatter)
  return `---\n${fm}\n---\n\n${content}\n`
}
