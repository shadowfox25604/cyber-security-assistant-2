import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, NotRequired

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.md"


@lru_cache(maxsize=1)
def _base_system_text() -> str:
    """Editable base instructions from `prompts/system_prompt.md`."""
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _prompt_body(filename: str, **replacements: str) -> str:
    text = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    for key, val in replacements.items():
        text = text.replace(f"@@{key.upper()}@@", val)
    return text.strip()


def _full_system(prompt_filename: str, **replacements: str) -> str:
    base = _base_system_text()
    body = _prompt_body(prompt_filename, **replacements)
    return f"{base}\n\n{body}" if base else body


class IntentResult(BaseModel):
    intent: Literal["relevant", "irrelevant"] = Field(
        description="relevant if the user asks about cybersecurity or closely related technical risk; "
        "irrelevant otherwise."
    )


class QueryDomainResult(BaseModel):
    domain: Literal[
        "network_security",
        "application_security",
        "other_cybersecurity",
    ] = Field(
        description="network_security: network security (firewalls, IDS/IPS, segmentation, VPN, DNS security, "
        "TLS at perimeter, cloud networking). application_security: application security (OWASP, APIs, "
        "auth/sessions, secure coding, app vulnerabilities, DevSecOps for apps). other_cybersecurity: other "
        "cybersecurity topics not primarily network-only or app-only."
    )


class QAResult(BaseModel):
    can_answer: bool = Field(
        description="True only if you can answer with reasonable confidence from general cybersecurity knowledge."
    )
    draft_answer: str = Field(
        description="Technical draft answer in plain language; empty if can_answer is false."
    )


class CyberState(TypedDict):
    """Full graph state (routing + QA). Use a narrow output_schema so AG-UI snapshots stay small."""

    messages: Annotated[list[AnyMessage], add_messages]
    question: NotRequired[str]
    intent: NotRequired[str]
    query_domain: NotRequired[str]
    category: NotRequired[str]
    qa_can_answer: NotRequired[bool]
    qa_draft: NotRequired[str]
    answer: NotRequired[str]
    prompt: NotRequired[str]
    validated: NotRequired[bool]
    format_template: NotRequired[str]


class CyberPublicOutput(TypedDict):
    """What clients should see after a run (no internal routing / draft fields)."""

    messages: list[AnyMessage]


def _last_human_question(state: CyberState) -> str:
    messages = state.get("messages") or []
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            c = m.content
            return c if isinstance(c, str) else str(c)
    return ""


def _conversation_context(state: CyberState) -> list[AnyMessage]:
    messages = state.get("messages") or []
    return [m for m in messages if isinstance(m, (HumanMessage, AIMessage))]


def _make_llm(*, streaming: bool) -> ChatOpenAI:
    llm_kwargs: dict = {
        "model": OPENAI_MODEL or "gpt-4o-mini",
        "streaming": streaming,
    }
    if OPENAI_API_KEY:
        llm_kwargs["api_key"] = OPENAI_API_KEY
    if OPENAI_BASE_URL:
        llm_kwargs["base_url"] = OPENAI_BASE_URL
    llm = ChatOpenAI(**llm_kwargs)
    if not streaming:
        llm = llm.with_config(metadata={"copilotkit:emit-messages": False})
    return llm


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


def intent_classifier(state: CyberState) -> dict:
    question = _last_human_question(state)
    context = _conversation_context(state)
    llm = _make_llm(streaming=False).with_structured_output(IntentResult, method="json_schema")
    system = _full_system("intent_classifier.md")
    prompt = ChatPromptTemplate.from_messages(
        [("system", "{system}"), MessagesPlaceholder("history")]
    )
    result = (prompt | llm).invoke({"system": system, "history": context})
    return {"intent": result.intent, "question": question}


def query_classifier(state: CyberState) -> dict:
    question = state.get("question") or _last_human_question(state)
    context = _conversation_context(state)
    llm = _make_llm(streaming=False).with_structured_output(QueryDomainResult, method="json_schema")
    system = _full_system("query_classifier.md")
    prompt = ChatPromptTemplate.from_messages(
        [("system", "{system}"), MessagesPlaceholder("history")]
    )
    result = (prompt | llm).invoke({"system": system, "history": context})
    domain = result.domain
    return {"query_domain": domain, "category": domain}


def _qa_from_prompt(state: CyberState, prompt_filename: str) -> dict:
    context = _conversation_context(state)
    llm = _make_llm(streaming=False).with_structured_output(QAResult, method="json_schema")
    system = _full_system(prompt_filename)
    prompt = ChatPromptTemplate.from_messages(
        [("system", "{system}"), MessagesPlaceholder("history")]
    )
    result = (prompt | llm).invoke({"system": system, "history": context})
    return {"qa_can_answer": result.can_answer, "qa_draft": result.draft_answer}


def network_security_qa(state: CyberState) -> dict:
    return _qa_from_prompt(state, "network_security_qa.md")


def application_security_qa(state: CyberState) -> dict:
    return _qa_from_prompt(state, "application_security_qa.md")


def other_cybersecurity_qa(state: CyberState) -> dict:
    return _qa_from_prompt(state, "other_cybersecurity_qa.md")


def format_generator_based_on_selected_state_node(state: CyberState) -> dict:
    """Generate a response markdown template from the user question (prompt: format_generator_based_on_selected_state.md)."""
    question = state.get("question") or _last_human_question(state)
    system = _full_system("format_generator_based_on_selected_state.md", QUESTION=question)
    llm = _make_llm(streaming=False)
    prompt = ChatPromptTemplate.from_messages(
        [("system", "{system}"), MessagesPlaceholder("history")]
    )
    out = (prompt | llm).invoke(
        {"system": system, "history": _conversation_context(state)}
    )
    template = _message_text(out.content).strip()
    return {"format_template": template}


def format_response_node(state: CyberState) -> dict:
    domain = state.get("query_domain") or "other_cybersecurity"
    template = (state.get("format_template") or "").strip()
    draft = (state.get("qa_draft") or "").strip()
    context = _conversation_context(state)
    llm = _make_llm(streaming=True)
    system = _full_system("format_response.md", TEMPLATE=template)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system}"),
            MessagesPlaceholder("history"),
            ("human", "Expert draft to align with the template:\n{draft}"),
        ]
    )
    response = (prompt | llm).invoke({"system": system, "history": context, "draft": draft})
    text = _message_text(response.content)
    return {"messages": [response], "answer": text, "category": domain}


def irrelevant_node(state: CyberState) -> dict:
    """Terminal path when intent is irrelevant (no query QA or format steps)."""
    question = state.get("question") or _last_human_question(state)
    context = _conversation_context(state)
    llm = _make_llm(streaming=True)
    system = _full_system("irrelevant.md")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system}"),
            MessagesPlaceholder("history"),
            ("human", "Latest user message:\n{question}"),
        ]
    )
    response = (prompt | llm).invoke(
        {"system": system, "history": context, "question": question}
    )
    text = _message_text(response.content)
    return {"messages": [response], "answer": text, "category": "irrelevant"}


def cannot_answer_node(state: CyberState) -> dict:
    """Terminal path when the domain QA module cannot answer with confidence."""
    question = state.get("question") or _last_human_question(state)
    context = _conversation_context(state)
    llm = _make_llm(streaming=True)
    system = _full_system("cannot_answer.md")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system}"),
            MessagesPlaceholder("history"),
            (
                "human",
                "Latest user question:\n{question}\n\nSpecialist could not answer confidently.",
            ),
        ]
    )
    response = (prompt | llm).invoke(
        {"system": system, "history": context, "question": question}
    )
    text = _message_text(response.content)
    return {"messages": [response], "answer": text, "category": "cannot_answer"}


def route_after_intent(state: CyberState) -> Literal["irrelevant", "relevant"]:
    return "irrelevant" if state.get("intent") == "irrelevant" else "relevant"


def route_after_query(
    state: CyberState,
) -> Literal["network_security", "application_security", "other_cybersecurity"]:
    d = state.get("query_domain")
    if d == "network_security":
        return "network_security"
    if d == "application_security":
        return "application_security"
    return "other_cybersecurity"


def route_after_qa(state: CyberState) -> Literal["answered", "cannot_answer"]:
    return "answered" if state.get("qa_can_answer") else "cannot_answer"


def build_graph():
    """Flow: START → Intent Classifier → (irrelevant → END | relevant → Query Classifier → QA → …)."""
    graph_builder = StateGraph(CyberState, output_schema=CyberPublicOutput)

    graph_builder.add_node("intent_classifier", intent_classifier)
    graph_builder.add_node("query_classifier", query_classifier)
    graph_builder.add_node("network_security_qa", network_security_qa)
    graph_builder.add_node("application_security_qa", application_security_qa)
    graph_builder.add_node("other_cybersecurity_qa", other_cybersecurity_qa)
    graph_builder.add_node("format_generator_based_on_selected_state", format_generator_based_on_selected_state_node)
    graph_builder.add_node("format_response", format_response_node)
    graph_builder.add_node("irrelevant", irrelevant_node)
    graph_builder.add_node("cannot_answer", cannot_answer_node)

    graph_builder.add_edge(START, "intent_classifier")
    graph_builder.add_conditional_edges(
        "intent_classifier",
        route_after_intent,
        {"irrelevant": "irrelevant", "relevant": "query_classifier"},
    )
    graph_builder.add_edge("irrelevant", END)

    graph_builder.add_conditional_edges(
        "query_classifier",
        route_after_query,
        {
            "network_security": "network_security_qa",
            "application_security": "application_security_qa",
            "other_cybersecurity": "other_cybersecurity_qa",
        },
    )

    for qa_name in (
        "network_security_qa",
        "application_security_qa",
        "other_cybersecurity_qa",
    ):
        graph_builder.add_conditional_edges(
            qa_name,
            route_after_qa,
            {
                "answered": "format_generator_based_on_selected_state",
                "cannot_answer": "cannot_answer",
            },
        )

    graph_builder.add_edge("format_generator_based_on_selected_state", "format_response")
    graph_builder.add_edge("format_response", END)
    graph_builder.add_edge("cannot_answer", END)

    return graph_builder.compile(checkpointer=MemorySaver())


def _last_assistant_text(messages: list[AnyMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return _message_text(m.content)
    return ""


def main():
    graph = build_graph()
    cfg = {"configurable": {"thread_id": "cli-demo"}}
    out = graph.invoke(
        {"messages": [HumanMessage(content="What is a firewall zone and when would I use one?")]},
        cfg,
    )
    msgs = out.get("messages") or []
    print(out.get("answer") or _last_assistant_text(msgs))


if __name__ == "__main__":
    main()
