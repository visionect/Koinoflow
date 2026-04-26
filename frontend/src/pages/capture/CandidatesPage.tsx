import * as React from "react"

import {
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  ExternalLinkIcon,
  SparklesIcon,
  XCircleIcon,
} from "lucide-react"
import { useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import {
  useCandidates,
  useConnectors,
  useDismissCandidate,
  useDepartments,
  usePromoteCandidate,
  useWorkspaceMembers,
} from "@/api/client"
import { DeleteConfirmDialog } from "@/components/shared/DeleteConfirmDialog"
import { EmptyState } from "@/components/shared/EmptyState"
import { PageHeader } from "@/components/shared/PageHeader"
import { buildWorkspacePath, getDisplayName } from "@/lib/format"
import type { AutomationTier, CaptureCandidate, PromoteCandidateInput } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"

const TIER_TABS = [
  { value: "all", label: "All" },
  { value: "ready", label: "Ready to automate" },
  { value: "needs_integration", label: "Needs integration" },
  { value: "manual_only", label: "Manual only" },
] as const

export function CandidatesPage() {
  const { workspace } = useParams<{ workspace: string }>()
  const navigate = useNavigate()
  const { data: connectors = [], isLoading: connectorsLoading } = useConnectors()
  const dismiss = useDismissCandidate()

  const [activeTab, setActiveTab] = React.useState("all")
  const [expandedRows, setExpandedRows] = React.useState<Set<string>>(new Set())
  const [promoteTarget, setPromoteTarget] = React.useState<CaptureCandidate | null>(null)
  const [dismissTarget, setDismissTarget] = React.useState<CaptureCandidate | null>(null)

  const confluenceConnector = connectors.find((c) => c.provider === "confluence")

  const { data: candidateList, isLoading } = useCandidates(confluenceConnector?.id ?? "", {
    status: "pending",
    automation_tier: activeTab === "all" ? undefined : activeTab,
  })

  function toggleRow(id: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  function handleDismissConfirm() {
    if (!dismissTarget || !confluenceConnector) return
    dismiss.mutate(
      { credentialId: confluenceConnector.id, candidateId: dismissTarget.id },
      {
        onSuccess: () => {
          toast.success("Candidate dismissed")
          setDismissTarget(null)
        },
        onError: () => toast.error("Failed to dismiss candidate"),
      },
    )
  }

  if (!connectorsLoading && !confluenceConnector) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Candidates"
          description="AI-extracted skill candidates from your documentation sources."
        />
        <EmptyState
          title="No connectors yet"
          description="Connect a documentation source and run Extract Processes to discover automatable workflows."
        />
      </div>
    )
  }

  const candidates = candidateList?.items ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Candidates"
        description="Review AI-extracted skill candidates and promote them to your skill library."
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          {TIER_TABS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading candidates…</div>
      ) : candidates.length === 0 ? (
        <EmptyState
          title="No candidates"
          description={
            activeTab === "all"
              ? "Connect a documentation source and run Extract Processes to discover automatable workflows."
              : `No ${TIER_TABS.find((t) => t.value === activeTab)?.label.toLowerCase()} candidates found.`
          }
        />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Title</TableHead>
                <TableHead>Automation tier</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {candidates.map((candidate) => (
                <React.Fragment key={candidate.id}>
                  <TableRow>
                    <TableCell className="pr-0">
                      {(candidate.automation_tier === "needs_integration" ||
                        candidate.automation_tier === "manual_only") && (
                        <button
                          onClick={() => toggleRow(candidate.id)}
                          className="flex items-center justify-center rounded p-1 hover:bg-muted"
                          aria-label={expandedRows.has(candidate.id) ? "Collapse" : "Expand"}
                        >
                          {expandedRows.has(candidate.id) ? (
                            <ChevronDownIcon className="size-4 text-muted-foreground" />
                          ) : (
                            <ChevronRightIcon className="size-4 text-muted-foreground" />
                          )}
                        </button>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium">{candidate.title}</span>
                        <Badge variant="outline" className="text-xs tabular-nums shrink-0">
                          {Math.round(candidate.probability_score * 100)}%
                        </Badge>
                      </div>
                      {candidate.description && (
                        <p className="mt-0.5 max-w-sm text-sm text-muted-foreground line-clamp-1">
                          {candidate.description}
                        </p>
                      )}
                    </TableCell>
                    <TableCell>
                      <TierBadge tier={candidate.automation_tier} />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      <CandidateSource sources={candidate.sources} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1"
                          onClick={() => setPromoteTarget(candidate)}
                        >
                          <CheckCircle2Icon className="size-3" />
                          Promote
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="gap-1 text-muted-foreground hover:text-destructive"
                          onClick={() => setDismissTarget(candidate)}
                        >
                          <XCircleIcon className="size-3" />
                          Dismiss
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>

                  {expandedRows.has(candidate.id) && (
                    <TableRow className="bg-muted/30 hover:bg-muted/30">
                      <TableCell colSpan={5} className="py-3 pl-14">
                        {candidate.automation_tier === "needs_integration" &&
                        candidate.integration_needs.length > 0 ? (
                          <div className="space-y-2">
                            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                              Integration requirements
                            </p>
                            <div className="grid gap-2 sm:grid-cols-2">
                              {candidate.integration_needs.map((need, i) => (
                                <div
                                  key={i}
                                  className="rounded-lg border bg-background p-3 text-sm space-y-1.5"
                                >
                                  <div className="font-medium">{need.system}</div>
                                  <p className="text-muted-foreground text-xs leading-relaxed">
                                    {need.reason}
                                  </p>
                                  {need.steps_affected.length > 0 && (
                                    <p className="text-xs text-muted-foreground">
                                      Steps: {need.steps_affected.join(", ")}
                                    </p>
                                  )}
                                  <p className="text-xs text-amber-700 dark:text-amber-400">
                                    {need.access_required}
                                  </p>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <p className="text-sm text-muted-foreground">
                            <span className="font-medium text-foreground">Reasoning: </span>
                            {candidate.automation_reasoning}
                          </p>
                        )}
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {promoteTarget && confluenceConnector && (
        <PromoteDialog
          candidate={promoteTarget}
          credentialId={confluenceConnector.id}
          onClose={() => setPromoteTarget(null)}
          onSuccess={(skillSlug) => {
            setPromoteTarget(null)
            navigate(buildWorkspacePath(workspace, `/skills/${skillSlug}`))
          }}
        />
      )}

      <DeleteConfirmDialog
        open={dismissTarget !== null}
        onOpenChange={(open) => !open && setDismissTarget(null)}
        entityName={dismissTarget?.title ?? ""}
        title="Dismiss candidate?"
        description="This candidate will be hidden from the list. It can be re-discovered by running extraction again."
        confirmLabel="Dismiss"
        requireTyping={false}
        pending={dismiss.isPending}
        onConfirm={handleDismissConfirm}
      />
    </div>
  )
}

function PromoteDialog({
  candidate,
  credentialId,
  onClose,
  onSuccess,
}: {
  candidate: CaptureCandidate
  credentialId: string
  onClose: () => void
  onSuccess: (skillSlug: string) => void
}) {
  const { data: departments = [] } = useDepartments()
  const { data: members = [] } = useWorkspaceMembers()
  const promote = usePromoteCandidate()

  const [departmentId, setDepartmentId] = React.useState("")
  const [ownerId, setOwnerId] = React.useState("unassigned")
  const [title, setTitle] = React.useState(candidate.title)
  const [description, setDescription] = React.useState(candidate.description)

  async function handlePromote() {
    if (!departmentId) return
    const payload: PromoteCandidateInput = {
      department_id: departmentId,
      owner_id: ownerId === "unassigned" ? null : ownerId,
      title: title.trim() || null,
      description: description.trim() || null,
    }
    try {
      const result = await promote.mutateAsync({
        credentialId,
        candidateId: candidate.id,
        payload,
      })
      toast.success("Skill created")
      onSuccess(result.skill_slug)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to promote candidate")
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Promote to skill</DialogTitle>
          <DialogDescription>
            Creates a draft skill from the AI-extracted content. You can review and publish it
            from the skill view.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="promote-title">Title</Label>
            <Input id="promote-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="promote-description">Description</Label>
            <Textarea
              id="promote-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>

          <div className="space-y-2">
            <Label>Department</Label>
            <Select value={departmentId} onValueChange={setDepartmentId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a department" />
              </SelectTrigger>
              <SelectContent>
                {departments.map((dept) => (
                  <SelectItem key={dept.id} value={dept.id}>
                    {dept.team_name} / {dept.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Owner</Label>
            <Select value={ownerId} onValueChange={setOwnerId}>
              <SelectTrigger>
                <SelectValue placeholder="Select an owner" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="unassigned">Unassigned</SelectItem>
                {members.map((member) => (
                  <SelectItem key={member.id} value={member.id}>
                    {getDisplayName(member)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={promote.isPending}>
            Cancel
          </Button>
          <Button
            disabled={!departmentId || !title.trim() || promote.isPending}
            onClick={() => void handlePromote()}
          >
            {promote.isPending ? "Creating…" : "Create skill"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CandidateSource({
  sources,
}: {
  sources: import("@/types").CandidateSourceBrief[] | null
}) {
  const first = sources?.[0]
  if (!first) return <span>—</span>
  return (
    <a
      href={first.page_external_url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-1 hover:underline max-w-[200px]"
    >
      <span className="truncate">{first.page_title}</span>
      <ExternalLinkIcon className="size-3 shrink-0" />
    </a>
  )
}

function TierBadge({ tier }: { tier: AutomationTier }) {
  if (tier === "ready") {
    return (
      <Badge className="gap-1 bg-green-100 text-green-800 hover:bg-green-100 dark:bg-green-900/30 dark:text-green-400">
        <SparklesIcon className="size-3" />
        Ready
      </Badge>
    )
  }
  if (tier === "needs_integration") {
    return (
      <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-400">
        Needs integration
      </Badge>
    )
  }
  return <Badge variant="secondary">Manual only</Badge>
}
