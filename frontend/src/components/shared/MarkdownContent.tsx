import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"

export function MarkdownContent({ content, className }: { content: string; className?: string }) {
  return (
    <div
      className={cn(
        "prose prose-slate max-w-none dark:prose-invert prose-headings:font-semibold prose-pre:overflow-x-auto prose-pre:rounded-xl prose-pre:border prose-pre:bg-slate-100 dark:prose-pre:bg-slate-800/70 prose-pre:text-slate-800 dark:prose-pre:text-slate-100 prose-code:rounded prose-code:bg-slate-100 dark:prose-code:bg-slate-800 prose-code:text-slate-800 dark:prose-code:text-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:font-medium prose-code:before:content-none prose-code:after:content-none prose-table:overflow-hidden prose-table:rounded-lg prose-table:border",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
