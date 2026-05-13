"""
Analytics middleware — Phase 5.
Tracks request timing, job counts, and usage stats in memory.
Exposes metrics via GET /api/analytics endpoint data.
"""

import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware


class AnalyticsCollector:
    def __init__(self):
        self._lock = Lock()
        self._request_counts: dict = defaultdict(int)
        self._request_total_ms: dict = defaultdict(float)
        self._jobs_started = 0
        self._jobs_complete = 0
        self._jobs_failed = 0
        self._claude_calls = 0
        self._videos_rendered = 0

    def record_request(self, endpoint: str, duration_ms: float):
        with self._lock:
            self._request_counts[endpoint] += 1
            self._request_total_ms[endpoint] += duration_ms

    def record_job(self, status: str):
        """status: 'started' | 'complete' | 'failed'"""
        with self._lock:
            if status == "started":
                self._jobs_started += 1
            elif status == "complete":
                self._jobs_complete += 1
                self._videos_rendered += 1
            elif status == "failed":
                self._jobs_failed += 1

    def record_claude_call(self):
        with self._lock:
            self._claude_calls += 1

    def get_stats(self) -> dict:
        with self._lock:
            avg_times = {}
            for endpoint, count in self._request_counts.items():
                total_ms = self._request_total_ms[endpoint]
                avg_times[endpoint] = round(total_ms / count, 2) if count > 0 else 0.0

            return {
                "requests": {
                    "by_endpoint": dict(self._request_counts),
                    "avg_response_ms": avg_times,
                },
                "jobs": {
                    "total_started": self._jobs_started,
                    "total_complete": self._jobs_complete,
                    "total_failed": self._jobs_failed,
                },
                "claude_api_calls": self._claude_calls,
                "videos_rendered": self._videos_rendered,
            }


analytics = AnalyticsCollector()


class AnalyticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000.0
        endpoint = request.url.path
        analytics.record_request(endpoint, duration_ms)
        return response
