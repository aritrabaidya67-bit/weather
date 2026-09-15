"""Chatbot schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system"]


class ChatTurn(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)
    device_id: str | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    include_raw_context: bool = False


class ChatCitation(BaseModel):
    label: str
    value: str
    source: str
    timestamp: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    model: str | None = None
    grounding: Literal["live_data", "historical_data", "analysis_only"] = "live_data"
    data_available: bool = True
    used_context: dict[str, Any] = Field(default_factory=dict)
    citations: list[ChatCitation] = Field(default_factory=list)
    latency_ms: int | None = None
    fallback_used: bool = False
    warning: str | None = None
    created_at: str


class ChatStreamChunk(BaseModel):
    type: Literal["meta", "token", "error", "done"]
    content: str = ""
    session_id: str | None = None
    model: str | None = None
    detail: str | None = None


class ChatStatusResponse(BaseModel):
    available: bool
    host: str
    model: str | None = None
    models_available: list[str] = Field(default_factory=list)
    installed: bool
    running: bool
    detail: str = ""
    context_chars: int | None = None
    generated_at: str | None = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    count: int = 0
    messages: list[dict[str, Any]] = Field(default_factory=list)


class SuggestedQuestionsResponse(BaseModel):
    questions: list[str] = Field(default_factory=list)
    generated_from: str = "template"
