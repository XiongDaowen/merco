"""指标收集"""

import time
from collections import defaultdict


class MetricsCollector:
    """收集与报告系统指标"""

    def __init__(self):
        self._counters: dict[str, int] = defaultdict(int)
        self._timings: dict[str, list[float]] = defaultdict(list)
        self._events: list[dict] = []

    def increment(self, name: str, value: int = 1):
        """增加计数器"""
        self._counters[name] += value

    def record_timing(self, name: str, duration: float):
        """记录耗时"""
        self._timings[name].append(duration)

    def record_event(self, event_type: str, **kwargs):
        """记录事件"""
        self._events.append(
            {
                "type": event_type,
                "timestamp": time.time(),
                **kwargs,
            }
        )

    def get_counter(self, name: str) -> int:
        """获取计数器值"""
        return self._counters.get(name, 0)

    def get_avg_timing(self, name: str) -> float:
        """获取平均耗时"""
        timings = self._timings.get(name, [])
        return sum(timings) / len(timings) if timings else 0.0

    def get_events(self, event_type: str = None, limit: int = 100) -> list[dict]:
        """获取事件列表"""
        events = self._events
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:]

    def get_counters(self) -> dict[str, int]:
        """获取所有计数器（只读）"""
        return dict(self._counters)

    def get_summary(self) -> dict:
        """获取指标摘要"""
        return {
            "counters": dict(self._counters),
            "avg_timings": {name: sum(vals) / len(vals) for name, vals in self._timings.items() if vals},
            "total_events": len(self._events),
        }
