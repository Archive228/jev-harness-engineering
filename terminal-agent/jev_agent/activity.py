"""A turn's real operational events, grouped without changing stored evidence."""
import asyncio
from textual.containers import Vertical
from textual.widgets import Collapsible


class ActivityGroup(Collapsible):
    def __init__(self):
        self.body = Vertical(classes="activity-body")
        self.pending = []
        self.discarded = set()
        self.settled = asyncio.Event()
        self.settled.set()
        self.flushing = False
        self.tool_count = 0
        self.jev_count = 0
        self.checks = None
        super().__init__(self.body, title="Activity", collapsed=False,
                         collapsed_symbol="▸", expanded_symbol="▾", classes="activity-group")

    def _watch_collapsed(self, collapsed):
        # The app owns chat scrolling. Textual's default deferred, animated
        # scroll_visible can pull restored history away from the final answer.
        self._update_collapsed(collapsed)
        self.post_message(self.Collapsed(self) if collapsed else self.Expanded(self))

    def add(self, widget):
        self.pending.append(widget)
        self.settled.clear()
        if self.is_mounted:
            self.call_later(self._flush)

    def discard(self, widget):
        self.discarded.add(widget)
        if widget in self.pending:
            self.pending.remove(widget)
        elif widget.is_mounted:
            widget.remove()

    def on_mount(self):
        self.call_later(self._flush)

    async def _flush(self):
        if not self.body.is_mounted or self.flushing:
            return
        self.flushing = True
        try:
            while self.pending:
                batch, self.pending = self.pending, []
                await self.body.mount(*batch)
                for widget in batch:
                    if widget in self.discarded:
                        await widget.remove()
        finally:
            self.flushing = False
            self.settled.set()

    def update_summary(self, finished=False, status=""):
        parts = []
        if self.tool_count:
            parts.append("actions: {}".format(self.tool_count))
        if self.jev_count:
            parts.append("Jev decisions: {}".format(self.jev_count))
        if self.checks is not None:
            parts.append("checks {}/{}".format(self.checks.get("passed", 0), self.checks.get("total", 0)))
        self.title = "Activity" + (" · " + " · ".join(parts) if parts else "")
        if finished:
            failed = status in ("error", "failed", "cancelled", "stopped", "needs_input", "blocked")
            self.title = ("× " if failed else "✓ ") + self.title
            self.collapsed = not failed
