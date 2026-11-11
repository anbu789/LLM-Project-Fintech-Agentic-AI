"""
FinTech Agent — Dedicated Execution Monitor Package
Provides isolated terminal tailing and real-time Rich/plain-text dashboard rendering.
"""

from backend.app.monitor.cli import (
    JsonlEventTailer,
    format_provider_event_line,
    render_plain_dashboard,
    render_rich_dashboard,
    run_monitor,
)

__all__ = [
    "JsonlEventTailer",
    "format_provider_event_line",
    "render_plain_dashboard",
    "render_rich_dashboard",
    "run_monitor",
]
