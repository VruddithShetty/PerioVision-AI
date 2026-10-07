"""One lock for every model call.

The YOLO models are not thread-safe: two threads running the same model at once (for example the start-up self-check
in app/ml/canary.py and the first analysis request, or two analyses on the threaded development server) can corrupt
its cached anchor grid and fail with "The size of tensor a (...) must match the size of tensor b (...)". Everything
that runs a model holds this lock, so model calls happen one at a time. Re-entrant, so a locked function may call
another locked function.
"""
from __future__ import annotations

import functools
import threading

MODEL_LOCK = threading.RLock()


def with_model_lock(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with MODEL_LOCK:
            return fn(*args, **kwargs)
    return wrapper
