"""File watcher for auto-recompilation."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from texguardian.core.session import SessionState


class LatexWatcher:
    """Watches LaTeX files and triggers recompilation."""

    def __init__(self, session: SessionState):
        self.session = session
        self.observer: Observer | None = None
        self._debounce_timer: threading.Timer | None = None
        self._debounce_delay = 1.0  # seconds

    def start(self) -> None:
        """Start watching for file changes."""
        if self.observer:
            return

        handler = LatexFileHandler(self._on_change)
        self.observer = Observer()
        self.observer.schedule(
            handler,
            str(self.session.project_root),
            recursive=True,
        )
        self.observer.start()

    def stop(self) -> None:
        """Stop watching."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def _on_change(self, path: str) -> None:
        """Handle file change with debouncing."""
        # Cancel existing timer
        if self._debounce_timer:
            self._debounce_timer.cancel()

        # Start new timer
        self._debounce_timer = threading.Timer(
            self._debounce_delay,
            self._trigger_recompile,
            args=[path],
        )
        self._debounce_timer.start()

    def _trigger_recompile(self, changed_path: str) -> None:
        """Trigger recompilation."""
        from texguardian.latex.compiler import LatexCompiler

        async def recompile():
            compiler = LatexCompiler(self.session.config)
            result = await compiler.compile(
                self.session.main_tex_path,
                self.session.output_dir,
            )
            self.session.last_compilation = result

            # Print notification (simplified - in real impl would use callback)
            if result.success:
                page_info = f": {result.page_count} pages" if result.page_count is not None else ""
                print(f"\n[Watch] Recompiled{page_info}")
            else:
                print("\n[Watch] Compilation failed")

        # Run async compile
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(recompile())
            else:
                asyncio.run(recompile())
        except RuntimeError:
            asyncio.run(recompile())


class LatexFileHandler(PatternMatchingEventHandler):
    """Handler for LaTeX file changes."""

    def __init__(self, callback):
        super().__init__(
            patterns=["*.tex", "*.bib", "*.sty", "*.cls"],
            ignore_patterns=["*~", "*.aux", "*.log", "*.out"],
            ignore_directories=True,
        )
        self.callback = callback

    def on_modified(self, event):
        """Handle file modification."""
        self.callback(event.src_path)

    def on_created(self, event):
        """Handle file creation."""
        self.callback(event.src_path)
