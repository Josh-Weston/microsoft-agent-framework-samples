from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class SpanContext(BaseModel):
    trace_id: str
    span_id: str
    trace_state: str


class SpanStatus(BaseModel):
    status_code: str


class SpanEvent(BaseModel):
    name: str
    timestamp: datetime  # Pydantic automatically parses the ISO 8601 string!
    attributes: Dict[str, Any]


class SpanResource(BaseModel):
    attributes: Dict[str, Any]
    schema_url: str


class OpenTelemetrySpan(BaseModel):
    name: str
    context: SpanContext
    kind: str
    parent_id: Optional[str] = None  # Handles the null value perfectly
    start_time: datetime
    end_time: datetime
    status: SpanStatus
    attributes: Dict[str, Any]
    events: List[SpanEvent]
    links: list
    resource: SpanResource
