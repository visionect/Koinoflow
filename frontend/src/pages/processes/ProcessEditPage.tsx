import { Navigate, useParams } from "react-router-dom"

import { buildWorkspacePath } from "@/lib/format"

export function ProcessEditPage() {
  const { workspace, processSlug } = useParams<{ workspace: string; processSlug: string }>()

  return <Navigate to={buildWorkspacePath(workspace, `/processes/${processSlug}`)} replace />
}
