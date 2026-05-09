"""FastAPI app exposing the LangGraph agent via the AG-UI protocol (CopilotKit-compatible)."""

import os
from typing import Any, AsyncGenerator

from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from ag_ui_langgraph.types import LangGraphEventTypes
from copilotkit import LangGraphAGUIAgent
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langchain_core.messages import BaseMessage

from main import build_graph

load_dotenv()

# Nodes whose LLM outputs are internal (structured JSON / routing) and must not be merged
# into the user-visible CopilotKit transcript (see ag_ui_langgraph streamed_messages logic).
_INTERNAL_LLM_NODES = frozenset(
    {
        "intent_classifier",
        "query_classifier",
        "network_security_qa",
        "application_security_qa",
        "other_cybersecurity_qa",
        # Template is consumed only by format_response; must not appear as its own assistant message.
        "format_generator_based_on_query",
    }
)


class CyberAGUIAgent(LangGraphAGUIAgent):
    async def _handle_single_event(self, event: Any, state: dict) -> AsyncGenerator[str, None]:
        if event.get("event") == LangGraphEventTypes.OnChatModelEnd.value:
            md = event.get("metadata") or {}
            node = md.get("langgraph_node")
            if node in _INTERNAL_LLM_NODES:
                data = event.get("data")
                if isinstance(data, dict):
                    out = data.get("output")
                    if isinstance(out, BaseMessage):
                        event = {**event, "data": {**data, "output": None}}
        async for chunk in super()._handle_single_event(event, state):
            yield chunk


app = FastAPI(title="Cyber agent (AG-UI)")

_origins = os.environ.get("CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cyber_graph = build_graph()
agui_agent = CyberAGUIAgent(
    name="default",
    description="Cyber assistant powered by LangGraph + AG-UI",
    graph=_cyber_graph,
)

add_langgraph_fastapi_endpoint(app, agui_agent, path="/agui")
