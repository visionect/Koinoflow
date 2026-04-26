import * as React from "react"

import { zodResolver } from "@hookform/resolvers/zod"
import { useForm, useWatch } from "react-hook-form"
import { Navigate, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { z } from "zod"

import { useCreateWorkspace } from "@/api/client"
import { useAuth } from "@/hooks/useAuth"
import { slugify } from "@/lib/format"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingScreen } from "@/components/shared/LoadingScreen"

const schema = z.object({
  name: z.string().min(1, "Workspace name is required").max(255),
  slug: z
    .string()
    .min(3, "Use at least 3 characters")
    .max(100)
    .regex(/^[a-z0-9-]+$/, "Use lowercase letters, numbers, and hyphens only"),
})

type FormValues = z.infer<typeof schema>

export function OnboardingPage() {
  const navigate = useNavigate()
  const createWorkspace = useCreateWorkspace()
  const { isAuthenticated, isLoading, hasWorkspace, workspaceSlug } = useAuth()
  const [slugTouched, setSlugTouched] = React.useState(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      slug: "",
    },
  })

  const nameField = form.register("name")
  const watchedName = useWatch({
    control: form.control,
    name: "name",
    defaultValue: "",
  })
  const watchedSlug = useWatch({
    control: form.control,
    name: "slug",
    defaultValue: "",
  })

  React.useEffect(() => {
    if (!slugTouched) {
      form.setValue("slug", slugify(watchedName), {
        shouldDirty: true,
      })
    }
  }, [form, slugTouched, watchedName])

  if (isLoading) {
    return <LoadingScreen label="Checking your session…" />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (hasWorkspace && workspaceSlug) {
    return <Navigate to={`/${workspaceSlug}`} replace />
  }

  async function onSubmit(values: FormValues) {
    try {
      const workspace = await createWorkspace.mutateAsync(values)
      toast.success("Workspace created")
      navigate(`/${workspace.slug}`, { replace: true })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to create workspace")
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/20 px-4">
      <Card className="w-full max-w-lg shadow-lg">
        <CardHeader>
          <CardTitle>Create your workspace</CardTitle>
          <CardDescription>
            Set up the shared home for your teams, skills, and API integrations.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
            <div className="space-y-2">
              <Label htmlFor="name">Workspace name</Label>
              <Input id="name" placeholder="Acme Corp" {...nameField} />
              {form.formState.errors.name ? (
                <p className="text-sm text-destructive">{form.formState.errors.name.message}</p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="slug">Workspace URL</Label>
              <Input
                id="slug"
                placeholder="acme-corp"
                {...form.register("slug")}
                value={watchedSlug}
                onChange={(event) => {
                  setSlugTouched(true)
                  form.setValue("slug", slugify(event.target.value), {
                    shouldDirty: true,
                    shouldValidate: true,
                  })
                }}
              />
              <p className="text-xs text-muted-foreground">
                A short ID used in links and API paths. Lowercase letters, numbers, and hyphens
                only. Your workspace will live at{" "}
                <span className="font-medium text-foreground">
                  /{watchedSlug || "your-workspace"}
                </span>
                .
              </p>
              {form.formState.errors.slug ? (
                <p className="text-sm text-destructive">{form.formState.errors.slug.message}</p>
              ) : null}
            </div>

            <Button className="w-full" disabled={createWorkspace.isPending} type="submit">
              {createWorkspace.isPending ? "Creating workspace..." : "Create workspace"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
