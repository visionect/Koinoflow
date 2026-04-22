import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const CLIENT_STYLES: Record<string, string> = {
  "Claude Code": "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  "Claude.ai": "bg-purple-500/10 text-purple-700 dark:text-purple-300",
  Cursor: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
  "Windsurf Editor": "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  "Zed Editor": "bg-orange-500/10 text-orange-700 dark:text-orange-300",
  "GitHub Copilot CLI": "bg-green-500/10 text-green-700 dark:text-green-300",
  Cline: "bg-amber-500/15 text-amber-800 dark:bg-amber-500/10 dark:text-amber-200",
  ChatGPT: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  "Gemini CLI": "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  "OpenAI Codex": "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  "Visual Studio Code": "bg-blue-600/10 text-blue-800 dark:text-blue-200",
  "REST API": "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  MCP: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  "MCP (local)": "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  Web: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  Unknown: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
}

export function ClientBadge({ clientType }: { clientType: string }) {
  return (
    <Badge
      variant="secondary"
      className={cn("border-transparent", CLIENT_STYLES[clientType] ?? CLIENT_STYLES["Unknown"])}
    >
      {clientType}
    </Badge>
  )
}
