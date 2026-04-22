import { Badge } from "@/components/ui/badge"

import type { ProcessStatus } from "@/types"

export function StatusBadge({ status }: { status: ProcessStatus }) {
  return (
    <Badge
      variant={status === "published" ? "default" : "secondary"}
      className={status === "published" ? "bg-success text-success-foreground" : ""}
    >
      {status === "published" ? "Published" : "Draft"}
    </Badge>
  )
}
