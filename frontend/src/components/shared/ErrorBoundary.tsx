import * as React from "react"

import { Button } from "@/components/ui/button"

type ErrorBoundaryProps = {
  children: React.ReactNode
}

type ErrorBoundaryState = {
  error: Error | null
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (!this.state.error) {
      return this.props.children
    }

    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <h1 className="text-2xl font-bold">Something went wrong</h1>
        <pre className="max-w-xl overflow-auto rounded-lg border bg-muted p-4 text-left text-sm">
          {this.state.error.message}
        </pre>
        <Button onClick={() => window.location.reload()}>Reload page</Button>
      </div>
    )
  }
}
