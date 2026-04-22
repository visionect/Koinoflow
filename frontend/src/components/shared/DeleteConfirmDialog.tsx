import * as React from "react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Input } from "@/components/ui/input"

type DeleteConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  entityName: string
  title?: string
  description: string
  confirmLabel?: string
  requireTyping?: boolean
  pending?: boolean
  onConfirm: () => void | Promise<void>
}

export function DeleteConfirmDialog({
  open,
  onOpenChange,
  entityName,
  title,
  description,
  confirmLabel = "Delete",
  requireTyping = true,
  pending = false,
  onConfirm,
}: DeleteConfirmDialogProps) {
  const [typedValue, setTypedValue] = React.useState("")

  React.useEffect(() => {
    if (!open) {
      setTypedValue("")
    }
  }, [open])

  const isValid = !requireTyping || typedValue === entityName

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title ?? `Delete "${entityName}"?`}</AlertDialogTitle>
          <AlertDialogDescription className="space-y-3">
            <span className="block">{description}</span>
            {requireTyping ? (
              <span className="block">
                Type <strong>{entityName}</strong> to confirm.
              </span>
            ) : null}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {requireTyping ? (
          <Input
            autoFocus
            placeholder={entityName}
            value={typedValue}
            onChange={(event) => setTypedValue(event.target.value)}
          />
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            disabled={!isValid || pending}
            onClick={(event) => {
              event.preventDefault()
              void onConfirm()
            }}
          >
            {pending ? "Working..." : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
