import { format, formatDistanceToNow } from "date-fns"

import type { User } from "@/types"

export function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

export function startCase(value: string) {
  return value
    .split(/[-_/]/g)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ")
}

export function formatDateTime(value: string | null, fallback = "—") {
  if (!value) {
    return fallback
  }

  return format(new Date(value), "MMM d, yyyy 'at' h:mm a")
}

export function formatDateOnly(value: string | null, fallback = "—") {
  if (!value) {
    return fallback
  }

  return format(new Date(value), "MMM d, yyyy")
}

export function formatRelativeDate(value: string | null, fallback = "Never") {
  if (!value) {
    return fallback
  }

  return formatDistanceToNow(new Date(value), { addSuffix: true })
}

export function isOlderThanDays(value: string | null, days: number) {
  if (!value) {
    return true
  }

  const threshold = Date.now() - days * 24 * 60 * 60 * 1000
  return new Date(value).getTime() < threshold
}

export function getDisplayName(user: User | null) {
  if (!user) {
    return "Unassigned"
  }

  const fullName = `${user.first_name} ${user.last_name}`.trim()
  return fullName.length > 0 ? fullName : user.email
}

export function getInitials(user: User | null) {
  if (!user) {
    return "KF"
  }

  const initials = `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.trim()

  if (initials.length > 0) {
    return initials.toUpperCase()
  }

  return user.email.slice(0, 2).toUpperCase()
}

export function buildWorkspacePath(workspace: string | undefined, path = "") {
  if (!workspace) {
    return path || "/"
  }

  if (!path) {
    return `/${workspace}`
  }

  return `/${workspace}${path.startsWith("/") ? path : `/${path}`}`
}
