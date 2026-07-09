"""
Progress Model: Thread-safe centralized progress tracker.

Provides a single source of truth for scan counts, processing counters,
phase timing, moving-average speed, and ETA calculation.
"""

import threading
import time
from collections import deque
from typing import Dict, Optional


class ProgressModel:
    """Thread-safe progress model with moving-average speed and ETA."""

    def __init__(self):
        self._lock = threading.Lock()

        # Counters
        self.total_scanned: int = 0
        self.total_processable: int = 0
        self.completed: int = 0
        self.failed: int = 0
        self.skipped: int = 0
        self.unmatched: int = 0

        # Phase tracking
        self.current_phase: str = ""
        self.phase_message: str = ""
        self.current_file: str = ""
        self.start_time: float = time.monotonic()
        self.phase_times: Dict[str, float] = {}
        self._phase_start: Dict[str, float] = {}

        # Output size tracking (bytes)
        self.output_bytes: int = 0

        # Speed window – stores monotonic timestamps of completed items
        self._speed_window: deque = deque(maxlen=200)

    # ------------------------------------------------------------------
    # Thread-safe counter increments
    # ------------------------------------------------------------------

    def increment_completed(self):
        with self._lock:
            self.completed += 1
            self._speed_window.append(time.monotonic())

    def increment_failed(self):
        with self._lock:
            self.failed += 1
            self._speed_window.append(time.monotonic())

    def increment_skipped(self):
        with self._lock:
            self.skipped += 1
            self._speed_window.append(time.monotonic())

    def add_output_bytes(self, nbytes: int):
        with self._lock:
            self.output_bytes += nbytes

    # ------------------------------------------------------------------
    # Phase timing
    # ------------------------------------------------------------------

    def set_phase(self, name: str, message: str = ""):
        with self._lock:
            self.current_phase = name
            self.phase_message = message or name.capitalize()
            self._phase_start[name] = time.monotonic()

    def end_phase(self, name: str):
        with self._lock:
            start = self._phase_start.pop(name, None)
            if start is not None:
                self.phase_times[name] = round(time.monotonic() - start, 3)

    def set_phase_message(self, message: str):
        with self._lock:
            self.phase_message = message

    # ------------------------------------------------------------------
    # Current file
    # ------------------------------------------------------------------

    def set_current_file(self, filename: str):
        with self._lock:
            self.current_file = filename

    # ------------------------------------------------------------------
    # Speed / ETA helpers
    # ------------------------------------------------------------------

    def get_speed(self) -> float:
        """Return files/sec based on timestamps in the speed window over the last 30 seconds."""
        with self._lock:
            if len(self._speed_window) < 2:
                return 0.0
            now = time.monotonic()
            cutoff = now - 30.0
            recent = [t for t in self._speed_window if t >= cutoff]
            if len(recent) < 2:
                return 0.0
            elapsed = recent[-1] - recent[0]
            if elapsed <= 0:
                return 0.0
            return (len(recent) - 1) / elapsed

    def get_eta_seconds(self) -> Optional[float]:
        """Estimated seconds remaining based on current speed."""
        speed = self.get_speed()
        if speed <= 0:
            return None
        with self._lock:
            remaining = self.total_processable - (self.completed + self.failed + self.skipped)
        if remaining <= 0:
            return 0.0
        return remaining / speed

    def get_elapsed(self) -> float:
        """Seconds since progress tracking started."""
        return time.monotonic() - self.start_time

    def get_progress_fraction(self) -> float:
        """Fraction of total_processable that has been handled."""
        with self._lock:
            if self.total_processable <= 0:
                return 0.0
            return min(1.0, (self.completed + self.failed + self.skipped) / self.total_processable)

    def get_processed_count(self) -> int:
        """Total items handled so far (completed + failed + skipped)."""
        with self._lock:
            return self.completed + self.failed + self.skipped

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict:
        """Return all state as a plain dict (thread-safe copy)."""
        with self._lock:
            total_proc = self.total_processable
            done = self.completed + self.failed + self.skipped
            frac = min(1.0, done / total_proc) if total_proc > 0 else 0.0
            return {
                "total_scanned": self.total_scanned,
                "total_processable": total_proc,
                "completed": self.completed,
                "failed": self.failed,
                "skipped": self.skipped,
                "unmatched": self.unmatched,
                "processed": done,
                "current_phase": self.current_phase,
                "phase_message": self.phase_message,
                "current_file": self.current_file,
                "start_time": self.start_time,
                "elapsed": time.monotonic() - self.start_time,
                "phase_times": dict(self.phase_times),
                "progress_fraction": frac,
                "output_bytes": self.output_bytes,
            }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self):
        """Clear all state for a fresh run."""
        with self._lock:
            self.total_scanned = 0
            self.total_processable = 0
            self.completed = 0
            self.failed = 0
            self.skipped = 0
            self.unmatched = 0
            self.current_phase = ""
            self.phase_message = ""
            self.current_file = ""
            self.start_time = time.monotonic()
            self.phase_times.clear()
            self._phase_start.clear()
            self._speed_window.clear()
            self.output_bytes = 0
