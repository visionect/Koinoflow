import { createHash, createHmac } from "node:crypto";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { KoinoflowAPIClient, KoinoflowMetadata } from "./api-client.js";

const approvalTokenSecret =
  process.env.KOINOFLOW_MCP_APPROVAL_TOKEN_SECRET ??
  "dev-approval-token-secret";
const approvalTokenTtlSeconds = Number.parseInt(
  process.env.KOINOFLOW_MCP_APPROVAL_TOKEN_TTL_SECONDS ?? "900",
  10,
);
const frontmatterRegex = /^---\r?\n(.*?)\r?\n---\r?\n?(.*)$/s;

function extractVersionData(data: Record<string, unknown>): {
  content_md: string;
  frontmatter_yaml: string;
  version_number?: number;
  files: Array<{ path: string; file_type: string; size_bytes: number }>;
  koinoflow_metadata: KoinoflowMetadata;
} | null {
  const current = (data.current_version ?? data) as Record<
    string,
    unknown
  > | null;
  if (!current) {
    return null;
  }
  const content = current.content_md;
  const frontmatter = current.frontmatter_yaml;
  if (typeof content !== "string" || typeof frontmatter !== "string") {
    return null;
  }
  const files = Array.isArray(current.files)
    ? current.files.flatMap((file) => {
        if (!file || typeof file !== "object") {
          return [];
        }
        const candidate = file as Record<string, unknown>;
        if (
          typeof candidate.path !== "string" ||
          typeof candidate.size_bytes !== "number"
        ) {
          return [];
        }
        return [
          {
            path: candidate.path,
            file_type:
              typeof candidate.file_type === "string"
                ? candidate.file_type
                : "text",
            size_bytes: candidate.size_bytes,
          },
        ];
      })
    : [];
  const versionNumber =
    typeof current.version_number === "number"
      ? current.version_number
      : undefined;
  const metadata = normalizeMetadata(current.koinoflow_metadata);
  return {
    content_md: content,
    frontmatter_yaml: frontmatter,
    version_number: versionNumber,
    files,
    koinoflow_metadata: metadata,
  };
}

const RISK_LEVEL_GUIDANCE: Record<string, string> = {
  low: "Low risk — normal caution.",
  medium: "Medium risk — confirm destructive actions before executing.",
  high: "**High risk** — confirm each destructive step with the user before executing.",
  critical:
    "**Critical risk** — do not execute any step without explicit per-step user confirmation. Escalate on ambiguity.",
};

function normalizeMetadata(raw: unknown): KoinoflowMetadata {
  const empty: KoinoflowMetadata = {
    retrieval_keywords: [],
    risk_level: null,
    requires_human_approval: false,
    prerequisites: [],
    audience: [],
  };
  if (!raw || typeof raw !== "object") {
    return empty;
  }
  const source = raw as Record<string, unknown>;
  const result: KoinoflowMetadata = { ...empty };
  if (Array.isArray(source.retrieval_keywords)) {
    result.retrieval_keywords = source.retrieval_keywords.filter(
      (s): s is string => typeof s === "string" && s.length > 0,
    );
  }
  if (
    source.risk_level === "low" ||
    source.risk_level === "medium" ||
    source.risk_level === "high" ||
    source.risk_level === "critical"
  ) {
    result.risk_level = source.risk_level;
  }
  if (typeof source.requires_human_approval === "boolean") {
    result.requires_human_approval = source.requires_human_approval;
  }
  if (Array.isArray(source.prerequisites)) {
    result.prerequisites = source.prerequisites.filter(
      (s): s is string => typeof s === "string" && s.length > 0,
    );
  }
  if (Array.isArray(source.audience)) {
    result.audience = source.audience.filter(
      (s): s is string => typeof s === "string" && s.length > 0,
    );
  }
  return result;
}

function buildKoinoflowContextBlock(metadata: KoinoflowMetadata): string {
  const keywords = metadata.retrieval_keywords ?? [];
  const risk = metadata.risk_level ?? null;
  const approval = metadata.requires_human_approval ?? false;
  const prereqs = metadata.prerequisites ?? [];
  const audience = metadata.audience ?? [];

  if (
    keywords.length === 0 &&
    !risk &&
    !approval &&
    prereqs.length === 0 &&
    audience.length === 0
  ) {
    return "";
  }

  const lines: string[] = ["> **Koinoflow Context**"];
  if (risk) {
    const guidance = RISK_LEVEL_GUIDANCE[risk] ?? "";
    lines.push(
      `> - Risk level: **${risk}**${guidance ? ` — ${guidance}` : ""}`,
    );
  }
  if (approval) {
    lines.push(
      "> - **Requires human approval** before execution — confirm the plan with the user before taking any step.",
    );
  }
  if (prereqs.length > 0) {
    const joined = prereqs.map((p) => `\`${p}\``).join(", ");
    lines.push(`> - Prerequisites: read ${joined} first`);
  }
  if (audience.length > 0) {
    lines.push(`> - Audience: ${audience.join(", ")}`);
  }
  if (keywords.length > 0) {
    lines.push(`> - Retrieval keywords: ${keywords.join(", ")}`);
  }
  return lines.join("\n");
}

function formatSupportFiles(
  files: Array<{ path: string; file_type: string; size_bytes: number }>,
): string {
  const lines = [`\n\n---\n## Support Files (${files.length} files)`];
  for (const file of files) {
    const sizeKb = Math.round((file.size_bytes / 1024) * 10) / 10;
    lines.push(`- ${file.path} (${file.file_type}, ${sizeKb} KB)`);
  }
  return lines.join("\n");
}

function toRawMarkdown(frontmatter: string, content: string): string {
  if (frontmatter) {
    return `---\n${frontmatter}\n---\n\n${content}`;
  }
  return content;
}

function parseRawMarkdown(rawMarkdown: string): {
  frontmatter_yaml: string;
  content_md: string;
} {
  const trimmed = rawMarkdown.trim();
  const match = frontmatterRegex.exec(trimmed);
  if (!match) {
    return { frontmatter_yaml: "", content_md: trimmed };
  }
  return {
    frontmatter_yaml: match[1].trim(),
    content_md: match[2].trim(),
  };
}

function contentHash(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function encodeBase64Url(input: string): string {
  return Buffer.from(input, "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function decodeBase64Url(input: string): string {
  const padded = input + "=".repeat((4 - (input.length % 4)) % 4);
  const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  return Buffer.from(base64, "base64").toString("utf8");
}

function issueApprovalToken(
  slug: string,
  proposedMarkdown: string,
  changeSummary: string,
): { token: string; expiresAtEpoch: number } {
  const now = Math.floor(Date.now() / 1000);
  const expiresAtEpoch = now + approvalTokenTtlSeconds;
  const payload = {
    slug,
    proposed_hash: contentHash(proposedMarkdown),
    change_summary_hash: contentHash(changeSummary),
    iat: now,
    exp: expiresAtEpoch,
  };
  const payloadEncoded = encodeBase64Url(JSON.stringify(payload));
  const signature = createHmac("sha256", approvalTokenSecret)
    .update(payloadEncoded)
    .digest("hex");
  return { token: `${payloadEncoded}.${signature}`, expiresAtEpoch };
}

function validateApprovalToken(
  token: string,
  slug: string,
  proposedMarkdown: string,
  changeSummary: string,
): string | null {
  const parts = token.split(".");
  if (parts.length !== 2) {
    return "Invalid approval token format.";
  }
  const payloadEncoded = parts[0];
  const signature = parts[1];
  const expected = createHmac("sha256", approvalTokenSecret)
    .update(payloadEncoded)
    .digest("hex");
  if (expected !== signature) {
    return "Approval token signature is invalid.";
  }

  let payload: {
    slug: string;
    proposed_hash: string;
    change_summary_hash: string;
    exp: number;
  };
  try {
    payload = JSON.parse(decodeBase64Url(payloadEncoded)) as {
      slug: string;
      proposed_hash: string;
      change_summary_hash: string;
      exp: number;
    };
  } catch {
    return "Approval token payload is invalid.";
  }

  if (Math.floor(Date.now() / 1000) > payload.exp) {
    return "Approval token expired. Request approval again.";
  }
  if (payload.slug !== slug) {
    return "Approval token does not match the process slug.";
  }
  if (payload.proposed_hash !== contentHash(proposedMarkdown)) {
    return "Approval token does not match the proposed markdown.";
  }
  if (payload.change_summary_hash !== contentHash(changeSummary)) {
    return "Approval token does not match the change summary.";
  }
  return null;
}

function refinementSuggestions(markdown: string): string[] {
  const suggestions: string[] = [];
  const content = markdown.trim();
  const lowered = content.toLowerCase();
  if (!content.includes("## ")) {
    suggestions.push(
      "Add section headings so the process is easier to navigate.",
    );
  }
  if (!/^\s*(?:\d+\.|-)\s+\S+/m.test(content)) {
    suggestions.push(
      "Use numbered or bulleted action steps for execution clarity.",
    );
  }
  if (!lowered.includes("prerequisite") && !lowered.includes("requirements")) {
    suggestions.push(
      "Include prerequisites (access, tools, dependencies) before execution.",
    );
  }
  if (!lowered.includes("owner") && !lowered.includes("responsible")) {
    suggestions.push("Specify ownership for critical steps and approvals.");
  }
  if (
    !lowered.includes("rollback") &&
    !lowered.includes("failure") &&
    !lowered.includes("incident")
  ) {
    suggestions.push(
      "Add rollback or failure handling guidance to reduce operational risk.",
    );
  }
  if (suggestions.length === 0) {
    suggestions.push(
      "Looks structured. Consider adding measurable success criteria.",
    );
  }
  return suggestions;
}

export function registerTools(
  server: McpServer,
  client: KoinoflowAPIClient,
): void {
  server.tool(
    "read_process",
    "Load the full approved Koinoflow instructions for a specific process. Use after list_processes, or immediately if the exact slug is already known, before giving organization-specific guidance.",
    {
      slug: z
        .string()
        .describe(
          'Exact process slug to load, for example "deploy-to-production"',
        ),
      version: z
        .number()
        .optional()
        .describe(
          "Optional specific version number; defaults to latest published version",
        ),
      include_files: z
        .boolean()
        .optional()
        .default(true)
        .describe(
          "Whether to append a listing of support files to the response",
        ),
    },
    async ({ slug, version, include_files }) => {
      try {
        const data = (await client.getProcess(
          slug,
          version,
        )) as unknown as Record<string, unknown>;
        const ver = extractVersionData(data);
        if (!ver) {
          return {
            content: [
              {
                type: "text" as const,
                text: "Process has no published version.",
              },
            ],
          };
        }

        if (
          typeof data.id === "string" &&
          typeof ver.version_number === "number"
        ) {
          client
            .logUsage(data.id, ver.version_number, "npx-mcp", "MCP (local)")
            .catch(() => {});
        }

        const contextBlock = buildKoinoflowContextBlock(ver.koinoflow_metadata);
        let body = ver.content_md;
        if (contextBlock) {
          body = `${contextBlock}\n\n${body}`;
        }
        let text = body;
        if (ver.frontmatter_yaml) {
          text = `---\n${ver.frontmatter_yaml}\n---\n\n${body}`;
        }
        if (include_files) {
          text += formatSupportFiles(ver.files);
        }

        return { content: [{ type: "text" as const, text }] };
      } catch (e) {
        return {
          content: [{ type: "text" as const, text: `Error: ${e}` }],
          isError: true,
        };
      }
    },
  );

  server.tool(
    "list_processes",
    "Discover the relevant Koinoflow process before answering organization-specific questions. Use this first when the exact process slug is unknown, then call read_process for the best match.",
    {
      department: z
        .string()
        .optional()
        .describe("Optional department slug to narrow process discovery"),
      team: z
        .string()
        .optional()
        .describe("Optional team slug to narrow process discovery"),
      search: z
        .string()
        .optional()
        .describe(
          "Optional keyword search across process titles and descriptions",
        ),
      limit: z
        .number()
        .int()
        .min(1)
        .max(100)
        .optional()
        .describe("Max results to return (1–100, default 100)"),
      offset: z
        .number()
        .int()
        .min(0)
        .optional()
        .describe(
          "Pagination offset for fetching subsequent pages (default 0)",
        ),
    },
    async ({ department, team, search, limit = 100, offset = 0 }) => {
      try {
        const data = await client.listProcesses(
          department,
          team,
          search,
          limit,
          offset,
        );
        if (data.items.length === 0) {
          return {
            content: [{ type: "text" as const, text: "No processes found." }],
          };
        }

        const lines = data.items.map((p) => {
          let line = `- **${p.title}** (\`${p.slug}\`)`;
          if (p.description) line += ` — ${p.description}`;
          if (p.current_version_number)
            line += ` [v${p.current_version_number}]`;
          if (p.risk_level) line += ` [risk: ${p.risk_level}]`;
          if (p.requires_human_approval) line += " [needs approval]";
          const keywords = p.retrieval_keywords ?? [];
          if (keywords.length > 0)
            line += ` (keywords: ${keywords.join(", ")})`;
          return line;
        });

        const end = offset + data.items.length;
        const total = data.count;
        let header = `Showing ${offset + 1}–${end} of ${total} processes`;
        if (end < total) header += ` (use offset=${end} to fetch more)`;
        const text = `${header}:\n\n${lines.join("\n")}`;
        return { content: [{ type: "text" as const, text }] };
      } catch (e) {
        return {
          content: [{ type: "text" as const, text: `Error: ${e}` }],
          isError: true,
        };
      }
    },
  );

  server.tool(
    "propose_process_update",
    "Preview a proposed update to a Koinoflow process without publishing it. Requires the 'Allow agent process updates' setting to be enabled in Koinoflow Settings. Use when you have made changes to a standard process and want to evolve it — returns current and proposed markdown, refinement suggestions, and a short-lived approval token required by apply_process_update. No change is persisted by this tool.",
    {
      slug: z
        .string()
        .describe('The process slug (e.g., "deploy-to-production")'),
      proposed_markdown: z
        .string()
        .min(1)
        .describe(
          "Full proposed raw markdown, optionally including YAML frontmatter.",
        ),
      change_summary: z
        .string()
        .min(1)
        .describe("Short summary of why this update is being made."),
      version: z
        .number()
        .optional()
        .describe("Optional source version to compare against."),
    },
    async ({ slug, proposed_markdown, change_summary, version }) => {
      try {
        const data = (await client.getProcess(
          slug,
          version,
        )) as unknown as Record<string, unknown>;
        const ver = extractVersionData(data);
        if (!ver) {
          return {
            content: [
              {
                type: "text" as const,
                text: "Process has no available version to refine.",
              },
            ],
            isError: true,
          };
        }

        const { token, expiresAtEpoch } = issueApprovalToken(
          slug,
          proposed_markdown,
          change_summary,
        );
        const payload = {
          process_slug: slug,
          current_markdown: toRawMarkdown(ver.frontmatter_yaml, ver.content_md),
          proposed_markdown,
          change_summary,
          refinement_suggestions: refinementSuggestions(proposed_markdown),
          approval_token: token,
          approval_expires_at_epoch: expiresAtEpoch,
          requires_user_approval: true,
          approval_instruction:
            "Ask the user to approve these exact changes before calling apply_process_update.",
        };

        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(payload, null, 2),
            },
          ],
        };
      } catch (e) {
        return {
          content: [{ type: "text" as const, text: `Error: ${e}` }],
          isError: true,
        };
      }
    },
  );

  server.tool(
    "apply_process_update",
    "Publish a new version of a Koinoflow process. Requires the 'Allow agent process updates' setting to be enabled in Koinoflow Settings. Call only after the user has reviewed and approved the output of propose_process_update. Creates a new draft process version from the approved markdown and change summary.",
    {
      slug: z
        .string()
        .describe('The process slug (e.g., "deploy-to-production")'),
      proposed_markdown: z
        .string()
        .min(1)
        .describe("The exact raw markdown approved by the user."),
      change_summary: z
        .string()
        .min(1)
        .describe("Change summary for the new process version."),
      approval_token: z
        .string()
        .min(1)
        .describe("Approval token returned by propose_process_update."),
    },
    async ({ slug, proposed_markdown, change_summary, approval_token }) => {
      try {
        const tokenError = validateApprovalToken(
          approval_token,
          slug,
          proposed_markdown,
          change_summary,
        );
        if (tokenError) {
          return {
            content: [{ type: "text" as const, text: `Error: ${tokenError}` }],
            isError: true,
          };
        }

        const parsed = parseRawMarkdown(proposed_markdown);
        const version = await client.createProcessVersion(slug, {
          content_md: parsed.content_md,
          frontmatter_yaml: parsed.frontmatter_yaml,
          change_summary,
        });
        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(
                {
                  status: "updated",
                  process_slug: slug,
                  new_version_id: version.id ?? null,
                  new_version_number: version.version_number,
                },
                null,
                2,
              ),
            },
          ],
        };
      } catch (e) {
        return {
          content: [{ type: "text" as const, text: `Error: ${e}` }],
          isError: true,
        };
      }
    },
  );
}
