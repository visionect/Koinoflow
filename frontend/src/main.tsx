import React, { StrictMode } from "react"
import ReactDOM from "react-dom"
import { createRoot } from "react-dom/client"

import App from "./App"
import "./index.css"

if (import.meta.env.DEV) {
  void import("@axe-core/react").then(({ default: axe }) => {
    void axe(React, ReactDOM, 1000)
  })
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
