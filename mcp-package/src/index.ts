#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { KoinoflowAPIClient } from "./api-client.js";
import { registerTools } from "./tools.js";

const apiUrl = process.env.KOINOFLOW_API_URL;
const apiKey = process.env.KOINOFLOW_API_KEY;

if (!apiUrl) {
  console.error(
    "KOINOFLOW_API_URL environment variable is required " +
      "(e.g. https://koinoflow.example.com/api/v1 or http://localhost:8000/api/v1)"
  );
  process.exit(1);
}

if (!apiKey) {
  console.error("KOINOFLOW_API_KEY environment variable is required");
  process.exit(1);
}

const server = new McpServer({
  name: "Koinoflow",
  version: "0.1.0",
});

const client = new KoinoflowAPIClient(apiUrl, apiKey);
registerTools(server, client);

const transport = new StdioServerTransport();
await server.connect(transport);
