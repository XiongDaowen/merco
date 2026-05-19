"""链路追踪"""

import time
import uuid
from contextvars import ContextVar

# 当前追踪 ID
current_trace: ContextVar[str] = ContextVar("trace_id", default="")


class TraceSpan:
    """追踪跨度"""

    def __init__(self, operation: str, parent_id: str = None):
        self.operation = operation
        self.trace_id = current_trace.get() or str(uuid.uuid4())[:8]
        self.span_id = str(uuid.uuid4())[:8]
        self.parent_id = parent_id
        self.start_time = time.time()
        self.end_time = None
        self.attributes: dict = {}

    def set_attribute(self, key: str, value):
        """设置属性"""
        self.attributes[key] = value

    def end(self):
        """结束跨度"""
        self.end_time = time.time()

    @property
    def duration(self) -> float:
        """获取耗时（秒）"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "operation": self.operation,
            "duration": self.duration,
            "attributes": self.attributes,
        }


class Tracer:
    """链路追踪器"""

    def __init__(self):
        self._spans: list[TraceSpan] = []

    def start_span(self, operation: str, parent_id: str = None) -> TraceSpan:
        """开始新的跨度"""
        span = TraceSpan(operation, parent_id)
        current_trace.set(span.trace_id)
        self._spans.append(span)
        return span

    def get_spans(self, trace_id: str = None) -> list[dict]:
        """获取跨度列表"""
        spans = self._spans
        if trace_id:
            spans = [s for s in spans if s.trace_id == trace_id]
        return [s.to_dict() for s in spans]
