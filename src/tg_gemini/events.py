from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventType(StrEnum):
    INIT = "init"
    MESSAGE = "message"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    RESULT = "result"


class BaseEvent(BaseModel):
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.now)


class InitEvent(BaseEvent):
    type: Literal[EventType.INIT] = EventType.INIT
    session_id: str
    model: str


class MessageEvent(BaseEvent):
    type: Literal[EventType.MESSAGE] = EventType.MESSAGE
    role: Literal["user", "assistant"]
    content: str
    delta: bool | None = None


class ToolUseEvent(BaseEvent):
    type: Literal[EventType.TOOL_USE] = EventType.TOOL_USE
    tool_name: str
    tool_id: str
    parameters: dict[str, Any]


class ToolResultError(BaseModel):
    type: str
    message: str


class ToolResultEvent(BaseEvent):
    type: Literal[EventType.TOOL_RESULT] = EventType.TOOL_RESULT
    tool_id: str
    status: Literal["success", "error"]
    output: str | None = None
    error: ToolResultError | None = None


class ErrorEvent(BaseEvent):
    type: Literal[EventType.ERROR] = EventType.ERROR
    severity: Literal["warning", "error"]
    message: str


class ModelStats(BaseModel):
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cached: int
    input: int


class StreamStats(BaseModel):
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cached: int
    input: int
    duration_ms: int
    tool_calls: int
    models: dict[str, ModelStats]


class ResultEvent(BaseEvent):
    type: Literal[EventType.RESULT] = EventType.RESULT
    status: Literal["success", "error"]
    error: dict[str, Any] | None = None
    stats: StreamStats | None = None


GeminiEvent = InitEvent | MessageEvent | ToolUseEvent | ToolResultEvent | ErrorEvent | ResultEvent


def parse_event(data: dict[str, Any]) -> GeminiEvent:
    event_type = data.get("type")
    if event_type == EventType.INIT:
        return InitEvent.model_validate(data)
    if event_type == EventType.MESSAGE:
        return MessageEvent.model_validate(data)
    if event_type == EventType.TOOL_USE:
        return ToolUseEvent.model_validate(data)
    if event_type == EventType.TOOL_RESULT:
        return ToolResultEvent.model_validate(data)
    if event_type == EventType.ERROR:
        return ErrorEvent.model_validate(data)
    if event_type == EventType.RESULT:
        return ResultEvent.model_validate(data)
    msg = f"Unknown event type: {event_type}"
    raise ValueError(msg)
