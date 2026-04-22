import * as React from "react"

import { toast } from "sonner"

import { useDepartments, useUpdateProcess } from "@/api/client"
import { VisibilityScopeSelector } from "@/components/processes/VisibilityScopeSelector"
import type { ProcessDetail, ProcessVisibility } from "@/types"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type ScopeDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  process: ProcessDetail
  isAdmin: boolean
}

export function ScopeDialog({ open, onOpenChange, process, isAdmin }: ScopeDialogProps) {
  const [visibility, setVisibility] = React.useState<ProcessVisibility>(process.visibility)
  const [sharedWithIds, setSharedWithIds] = React.useState<Set<string>>(
    new Set(process.shared_with_ids),
  )

  const departmentsQuery = useDepartments()
  const updateProcess = useUpdateProcess(process.slug)

  React.useEffect(() => {
    if (open) {
      setVisibility(process.visibility)
      setSharedWithIds(new Set(process.shared_with_ids))
    }
  }, [open, process.visibility, process.shared_with_ids])

  const ownerDept = departmentsQuery.data?.find(
    (d) => d.slug === process.department_slug && d.team_slug === process.team_slug,
  )

  const isDirty =
    visibility !== process.visibility ||
    [...sharedWithIds].sort().join() !== [...process.shared_with_ids].sort().join()

  async function handleSave() {
    try {
      await updateProcess.mutateAsync({
        visibility,
        shared_with_ids: [...sharedWithIds],
      })
      toast.success("Scope updated")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update scope")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Change scope &amp; sharing</DialogTitle>
          <DialogDescription>
            Control who can see this process across the workspace.
          </DialogDescription>
        </DialogHeader>

        <VisibilityScopeSelector
          ownerDepartmentId={ownerDept?.id ?? ""}
          ownerTeamSlug={process.team_slug}
          ownerTeamName={process.team_name}
          visibility={visibility}
          onVisibilityChange={setVisibility}
          sharedWithIds={sharedWithIds}
          onSharedWithIdsChange={setSharedWithIds}
          allDepartments={departmentsQuery.data ?? []}
          disableWorkspace={!isAdmin}
        />

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!isDirty || updateProcess.isPending} onClick={() => void handleSave()}>
            {updateProcess.isPending ? "Saving..." : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
