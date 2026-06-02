"""Idle Detector — Monitors system CPU usage to determine if the computer is idle.

Runs in a background thread and polls `psutil.cpu_percent()` every 2 seconds.
Maintains a sliding window (deque) of CPU readings. The system is considered
"idle" only if *all* readings in the window are below the threshold.
"""

from __future__ import annotations

import collections
import threading
import time

import psutil
import structlog

logger = structlog.get_logger()


class IdleDetector:
    """Detects system idleness based on sustained low CPU usage."""

    def __init__(self, check_interval_seconds: float = 2.0):
        self.check_interval = check_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._history: collections.deque[float] = collections.deque(maxlen=15) # Default 30s at 2s interval
        self._threshold_cpu: float = 10.0
        
        # We prime it with 100% so it doesn't immediately return idle on startup
        self._history.append(100.0)

    def start(self, threshold_cpu: float = 10.0, idle_window_seconds: float = 30.0) -> None:
        """Start the background monitoring thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("idle_detector.already_running")
            return

        self._threshold_cpu = threshold_cpu
        history_size = max(1, int(idle_window_seconds / self.check_interval))
        self._history = collections.deque(maxlen=history_size)
        self._history.append(100.0)
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="IdleDetector")
        self._thread.start()
        logger.info(
            "idle_detector.started", 
            threshold_cpu=self._threshold_cpu, 
            window_seconds=idle_window_seconds
        )

    def stop(self) -> None:
        """Gracefully stop the monitoring thread."""
        if not self._thread or not self._thread.is_alive():
            return

        logger.info("idle_detector.stopping")
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        logger.info("idle_detector.stopped")

    def _monitor_loop(self) -> None:
        """Background thread loop collecting CPU stats."""
        # Initial call primes psutil (returns 0.0 often)
        psutil.cpu_percent()
        
        while not self._stop_event.is_set():
            cpu_usage = psutil.cpu_percent(interval=None)
            self._history.append(cpu_usage)
            self._stop_event.wait(self.check_interval)

    def is_idle(self) -> bool:
        """Return True if all CPU readings in the window are below the threshold."""
        if not self._history:
            return False
        
        # If the history buffer isn't full yet, we wait before declaring idle
        if len(self._history) < self._history.maxlen:
            return False

        # All readings must be below threshold
        return all(reading < self._threshold_cpu for reading in self._history)

    def update_config(self, threshold_cpu: float, idle_window_seconds: float) -> None:
        """Update detection parameters dynamically without restarting the thread."""
        self._threshold_cpu = threshold_cpu
        new_size = max(1, int(idle_window_seconds / self.check_interval))
        if new_size != self._history.maxlen:
            old_history = list(self._history)
            self._history = collections.deque(old_history[-new_size:], maxlen=new_size)

# Global singleton
idle_detector = IdleDetector()
