import * as React from "react"

import {
  ChevronDownIcon,
  ChevronRightIcon,
  FileCode as FileCodeIcon,
  FileCode2 as FileCode2Icon,
  FileIcon,
  FileText as FileTextIcon,
  FolderIcon,
  PlusIcon,
  TrashIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/utils"
import type { VersionFile, VersionFileInput } from "@/types"

type FileTreeBrowserProps =
  | {
      files: VersionFile[]
      selectedPath?: string | null
      onFileSelect?: (path: string) => void
      editMode?: false
    }
  | {
      files: VersionFile[]
      selectedPath?: string | null
      onFileSelect?: (path: string) => void
      editMode: true
      onFileAdd: (file: VersionFileInput) => void
      onFileDelete: (path: string) => void
    }

type TreeNode = {
  name: string
  path: string
  file?: VersionFile
  children: TreeNode[]
}

function fileIcon(fileType: string) {
  switch (fileType) {
    case "python":
    case "javascript":
    case "typescript":
      return <FileCodeIcon className="size-3.5 shrink-0 text-info" aria-hidden />
    case "html":
      return <FileCode2Icon className="size-3.5 shrink-0 text-warning" aria-hidden />
    case "markdown":
    case "text":
      return <FileTextIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
    default:
      return <FileIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

function buildTree(files: VersionFile[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: [] }
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path))

  for (const file of sorted) {
    const segments = file.path.split("/").filter(Boolean)
    let current = root
    for (let i = 0; i < segments.length; i++) {
      const segment = segments[i]
      if (!segment) continue
      const isLeaf = i === segments.length - 1
      const accumulatedPath = segments.slice(0, i + 1).join("/")

      let next: TreeNode | undefined = current.children.find((c) => c.name === segment)

      if (!next) {
        next = {
          name: segment,
          path: accumulatedPath,
          children: [],
        }
        current.children.push(next)
      }

      if (isLeaf) {
        next.file = file
      }

      current = next
    }
  }

  const sortChildren = (node: TreeNode) => {
    node.children.sort((a, b) => {
      const aIsDir = a.children.length > 0 && !a.file
      const bIsDir = b.children.length > 0 && !b.file
      if (aIsDir !== bIsDir) return aIsDir ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const child of node.children) sortChildren(child)
  }
  sortChildren(root)

  return root
}

type FileRowProps = {
  node: TreeNode
  depth: number
  selectedPath: string | null | undefined
  onFileSelect?: (path: string) => void
  editMode: boolean
  onFileDelete?: (path: string) => void
}

function FileRow({
  node,
  depth,
  selectedPath,
  onFileSelect,
  editMode,
  onFileDelete,
}: FileRowProps) {
  const file = node.file!
  return (
    <div
      className={cn(
        "group flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 focus-within:bg-muted/60",
        selectedPath === file.path
          ? "bg-primary/10 text-primary"
          : "hover:bg-muted/60 text-foreground",
      )}
      style={{ paddingLeft: `${depth * 12 + 4}px` }}
      onClick={() => onFileSelect?.(file.path)}
    >
      {fileIcon(file.file_type)}
      <span className="min-w-0 flex-1 truncate text-xs">{node.name}</span>
      <span className="shrink-0 text-[10px] text-muted-foreground">
        {formatSize(file.size_bytes)}
      </span>
      {editMode && onFileDelete ? (
        <button
          type="button"
          aria-label={`Delete ${file.path}`}
          className="ml-1 rounded p-0.5 text-destructive opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 focus:outline-none focus:ring-1 focus:ring-destructive motion-reduce:transition-none [@media(hover:none)]:opacity-100"
          onClick={(e) => {
            e.stopPropagation()
            onFileDelete(file.path)
          }}
        >
          <TrashIcon className="size-3" aria-hidden />
        </button>
      ) : null}
    </div>
  )
}

type FolderRowProps = FileRowProps & {
  expanded: Set<string>
  toggle: (path: string) => void
}

function FolderRow(props: FolderRowProps) {
  const { node, depth, expanded, toggle } = props
  const isOpen = expanded.has(node.path)

  return (
    <div>
      <button
        type="button"
        className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-xs font-medium text-muted-foreground hover:bg-muted/60 focus:bg-muted/60 focus:outline-none"
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
        onClick={() => toggle(node.path)}
        aria-expanded={isOpen}
      >
        {isOpen ? (
          <ChevronDownIcon className="size-3.5" aria-hidden />
        ) : (
          <ChevronRightIcon className="size-3.5" aria-hidden />
        )}
        <FolderIcon className="size-3.5 text-yellow-500" aria-hidden />
        <span>{node.name}/</span>
      </button>
      {isOpen ? (
        <div>
          {node.children.map((child) =>
            child.file ? (
              <FileRow
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={props.selectedPath}
                onFileSelect={props.onFileSelect}
                editMode={props.editMode}
                onFileDelete={props.onFileDelete}
              />
            ) : (
              <FolderRow
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={props.selectedPath}
                onFileSelect={props.onFileSelect}
                editMode={props.editMode}
                onFileDelete={props.onFileDelete}
                expanded={expanded}
                toggle={toggle}
              />
            ),
          )}
        </div>
      ) : null}
    </div>
  )
}

export function FileTreeBrowser(props: FileTreeBrowserProps) {
  const { files, selectedPath, onFileSelect } = props
  const editMode: boolean = "editMode" in props ? props.editMode === true : false
  const [expanded, setExpanded] = React.useState<Set<string>>(() => new Set())
  const [showAddDialog, setShowAddDialog] = React.useState(false)
  const [newPath, setNewPath] = React.useState("")
  const [newFileType, setNewFileType] = React.useState("text")

  React.useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev)
      for (const file of files) {
        const segments = file.path.split("/")
        for (let i = 1; i < segments.length; i++) {
          next.add(segments.slice(0, i).join("/"))
        }
      }
      return next
    })
  }, [files])

  const tree = React.useMemo(() => buildTree(files), [files])

  function toggle(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  function handleAddFile() {
    if (!newPath.trim()) return
    if ("onFileAdd" in props && props.onFileAdd) {
      props.onFileAdd({ path: newPath.trim(), content: "", file_type: newFileType })
    }
    setNewPath("")
    setNewFileType("text")
    setShowAddDialog(false)
  }

  const onFileDelete = editMode && "onFileDelete" in props ? props.onFileDelete : undefined

  if (files.length === 0 && !editMode) {
    return <p className="py-2 text-xs text-muted-foreground">No support files.</p>
  }

  return (
    <div className="space-y-1 text-sm">
      {tree.children.map((child) =>
        child.file ? (
          <FileRow
            key={child.path}
            node={child}
            depth={0}
            selectedPath={selectedPath}
            onFileSelect={onFileSelect}
            editMode={editMode}
            onFileDelete={onFileDelete}
          />
        ) : (
          <FolderRow
            key={child.path}
            node={child}
            depth={0}
            selectedPath={selectedPath}
            onFileSelect={onFileSelect}
            editMode={editMode}
            onFileDelete={onFileDelete}
            expanded={expanded}
            toggle={toggle}
          />
        ),
      )}

      {editMode ? (
        <div className="pt-1">
          {showAddDialog ? (
            <div className="space-y-2 rounded border p-2">
              <div className="space-y-1">
                <Label htmlFor="filetree-new-path" className="text-xs">
                  File path
                </Label>
                <Input
                  id="filetree-new-path"
                  placeholder="scripts/my_file.py"
                  value={newPath}
                  onChange={(e) => setNewPath(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAddFile()
                    if (e.key === "Escape") setShowAddDialog(false)
                  }}
                  className="h-7 text-xs"
                  autoFocus
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="filetree-new-type" className="text-xs">
                  File type
                </Label>
                <Select value={newFileType} onValueChange={setNewFileType}>
                  <SelectTrigger id="filetree-new-type" className="h-7 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="python">Python</SelectItem>
                    <SelectItem value="markdown">Markdown</SelectItem>
                    <SelectItem value="html">HTML</SelectItem>
                    <SelectItem value="yaml">YAML</SelectItem>
                    <SelectItem value="javascript">JavaScript</SelectItem>
                    <SelectItem value="typescript">TypeScript</SelectItem>
                    <SelectItem value="shell">Shell</SelectItem>
                    <SelectItem value="text">Text</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-1">
                <Button size="sm" className="h-6 text-xs" onClick={handleAddFile}>
                  Add
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 text-xs"
                  onClick={() => setShowAddDialog(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setShowAddDialog(true)}
            >
              <PlusIcon className="size-3.5" aria-hidden />
              Add file
            </button>
          )}
        </div>
      ) : null}
    </div>
  )
}
