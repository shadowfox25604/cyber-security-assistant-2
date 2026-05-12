import {
  CopilotRuntime,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { LangGraphHttpAgent } from "@copilotkit/runtime/langgraph";

// Proxies to the Python AG-UI server. "fetch failed" in the UI usually means this URL is unreachable (agent not running).
const agentUrl =
  process.env.AGENT_AGUI_URL ?? "http://127.0.0.1:8000/agui";

const runtime = new CopilotRuntime({
  agents: {
    default: new LangGraphHttpAgent({
      url: agentUrl,
    }),
  },
});

const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
  runtime,
  endpoint: "/api/copilotkit",
});

export async function POST(req: Request): Promise<Response> {
  return handleRequest(req);
}
