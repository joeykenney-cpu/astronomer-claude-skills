#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const API_TOKEN = process.env.LEADFEEDER_API_TOKEN;
const BASE_URL = "https://api.leadfeeder.com";

async function lfFetch(path, params = {}) {
  const url = new URL(BASE_URL + path);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  }
  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Token token=${API_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "leadfeeder-mcp-server/1.0",
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Leadfeeder API error ${res.status}: ${text}`);
  }
  return res.json();
}

const server = new Server(
  { name: "leadfeeder", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "list_accounts",
      description: "List all Leadfeeder accounts accessible with the API token",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "get_leads",
      description: "Get leads (companies that visited your site) for an account",
      inputSchema: {
        type: "object",
        required: ["account_id", "start_date", "end_date"],
        properties: {
          account_id: { type: "string", description: "Leadfeeder account ID" },
          start_date: { type: "string", description: "Start date (YYYY-MM-DD)" },
          end_date: { type: "string", description: "End date (YYYY-MM-DD)" },
          page_size: { type: "number", description: "Results per page (default 100)" },
          page: { type: "number", description: "Page number" },
        },
      },
    },
    {
      name: "get_lead",
      description: "Get details for a specific lead",
      inputSchema: {
        type: "object",
        required: ["account_id", "lead_id"],
        properties: {
          account_id: { type: "string" },
          lead_id: { type: "string" },
        },
      },
    },
    {
      name: "get_lead_visits",
      description: "Get page visits for a specific lead",
      inputSchema: {
        type: "object",
        required: ["account_id", "lead_id", "start_date", "end_date"],
        properties: {
          account_id: { type: "string" },
          lead_id: { type: "string" },
          start_date: { type: "string", description: "Start date (YYYY-MM-DD)" },
          end_date: { type: "string", description: "End date (YYYY-MM-DD)" },
        },
      },
    },
    {
      name: "list_custom_feeds",
      description: "List all custom feeds for an account",
      inputSchema: {
        type: "object",
        required: ["account_id"],
        properties: {
          account_id: { type: "string" },
        },
      },
    },
    {
      name: "get_feed_leads",
      description: "Get leads from a specific custom feed",
      inputSchema: {
        type: "object",
        required: ["account_id", "feed_id", "start_date", "end_date"],
        properties: {
          account_id: { type: "string" },
          feed_id: { type: "string" },
          start_date: { type: "string", description: "Start date (YYYY-MM-DD)" },
          end_date: { type: "string", description: "End date (YYYY-MM-DD)" },
          page_size: { type: "number" },
          page: { type: "number" },
        },
      },
    },
    {
      name: "get_all_visits",
      description: "Get all visits across an account within a date range",
      inputSchema: {
        type: "object",
        required: ["account_id", "start_date", "end_date"],
        properties: {
          account_id: { type: "string" },
          start_date: { type: "string", description: "Start date (YYYY-MM-DD)" },
          end_date: { type: "string", description: "End date (YYYY-MM-DD)" },
        },
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  try {
    let data;
    switch (name) {
      case "list_accounts":
        data = await lfFetch("/accounts");
        break;
      case "get_leads":
        data = await lfFetch(`/accounts/${args.account_id}/leads`, {
          start_date: args.start_date,
          end_date: args.end_date,
          "page[size]": args.page_size,
          "page[number]": args.page,
        });
        break;
      case "get_lead":
        data = await lfFetch(`/accounts/${args.account_id}/leads/${args.lead_id}`);
        break;
      case "get_lead_visits":
        data = await lfFetch(
          `/accounts/${args.account_id}/leads/${args.lead_id}/visits`,
          { start_date: args.start_date, end_date: args.end_date }
        );
        break;
      case "list_custom_feeds":
        data = await lfFetch(`/accounts/${args.account_id}/custom-feeds`);
        break;
      case "get_feed_leads":
        data = await lfFetch(
          `/accounts/${args.account_id}/custom-feeds/${args.feed_id}/leads`,
          {
            start_date: args.start_date,
            end_date: args.end_date,
            "page[size]": args.page_size,
            "page[number]": args.page,
          }
        );
        break;
      case "get_all_visits":
        data = await lfFetch(`/accounts/${args.account_id}/visits`, {
          start_date: args.start_date,
          end_date: args.end_date,
        });
        break;
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
    return {
      content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
    };
  } catch (err) {
    return {
      content: [{ type: "text", text: `Error: ${err.message}` }],
      isError: true,
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
