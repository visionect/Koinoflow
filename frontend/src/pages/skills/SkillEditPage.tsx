import { Navigate, useParams } from "react-router-dom"

import { buildWorkspacePath } from "@/lib/format"

export function SkillEditPage() {
  const { workspace, skillSlug } = useParams<{ workspace: string; skillSlug: string }>()

  return <Navigate to={buildWorkspacePath(workspace, `/skills/${skillSlug}`)} replace />
}
