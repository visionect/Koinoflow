import * as React from "react"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { MarkdownContent } from "@/components/shared/MarkdownContent"

type EditorView = "edit" | "split" | "preview"

type MarkdownEditorProps = {
  value: string
  onChange: (value: string) => void
  minHeight?: string
}

export function MarkdownEditor({
  value,
  onChange,
  minHeight = "min-h-[50vh] xl:min-h-[60vh]",
}: MarkdownEditorProps) {
  const [view, setView] = React.useState<EditorView>("split")

  const textarea = (
    <Textarea
      className={`${minHeight} resize-y font-mono text-sm leading-6`}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-label="Markdown source"
    />
  )

  const preview = (
    <div className={`${minHeight} overflow-auto rounded-xl border bg-card p-4`}>
      <MarkdownContent content={value} />
    </div>
  )

  return (
    <Tabs
      value={view}
      onValueChange={(nextValue) => setView(nextValue as EditorView)}
      className="space-y-4"
    >
      <TabsList>
        <TabsTrigger value="edit">Edit</TabsTrigger>
        <TabsTrigger value="split">Split</TabsTrigger>
        <TabsTrigger value="preview">Preview</TabsTrigger>
      </TabsList>

      <TabsContent value="edit" className="m-0">
        {textarea}
      </TabsContent>

      <TabsContent value="split" className="m-0">
        <div className="grid gap-4 xl:grid-cols-2">
          {textarea}
          {preview}
        </div>
      </TabsContent>

      <TabsContent value="preview" className="m-0">
        {preview}
      </TabsContent>
    </Tabs>
  )
}
