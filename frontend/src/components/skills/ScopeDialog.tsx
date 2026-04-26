import * as React from "react"

import { toast } from "sonner"

import { useDepartments, useUpdateSkill } from "@/api/client"
import { VisibilityScopeSelector } from "@/components/skills/VisibilityScopeSelector"
import type { SkillDetail, SkillVisibility } from "@/types"
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
  skill: SkillDetail
  isAdmin: boolean
}

export function ScopeDialog({ open, onOpenChange, skill, isAdmin }: ScopeDialogProps) {
  const [visibility, setVisibility] = React.useState<SkillVisibility>(skill.visibility)
  const [sharedWithIds, setSharedWithIds] = React.useState<Set<string>>(
    new Set(skill.shared_with_ids),
  )

  const departmentsQuery = useDepartments()
  const updateSkill = useUpdateSkill(skill.slug)

  React.useEffect(() => {
    if (open) {
      setVisibility(skill.visibility)
      setSharedWithIds(new Set(skill.shared_with_ids))
    }
  }, [open, skill.visibility, skill.shared_with_ids])

  const ownerDept = departmentsQuery.data?.find(
    (d) => d.slug === skill.department_slug && d.team_slug === skill.team_slug,
  )

  const isDirty =
    visibility !== skill.visibility ||
    [...sharedWithIds].sort().join() !== [...skill.shared_with_ids].sort().join()

  async function handleSave() {
    try {
      await updateSkill.mutateAsync({
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
            Control who can see this skill across the workspace.
          </DialogDescription>
        </DialogHeader>

        <VisibilityScopeSelector
          ownerDepartmentId={ownerDept?.id ?? ""}
          ownerTeamSlug={skill.team_slug}
          ownerTeamName={skill.team_name}
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
          <Button disabled={!isDirty || updateSkill.isPending} onClick={() => void handleSave()}>
            {updateSkill.isPending ? "Saving..." : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
