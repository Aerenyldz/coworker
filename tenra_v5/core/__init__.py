"""Core package exports with lazy imports.

Avoid importing heavy modules (torch/transformers) at package import time.
"""

__all__ = [
    "FunctionGemmaRouter",
    "route_query",
    "execute_function",
    "should_bypass_router",
    "preload_models",
    "http_session",
]


def __getattr__(name):
    if name == "FunctionGemmaRouter":
        from core.router import FunctionGemmaRouter

        return FunctionGemmaRouter

    if name in {"route_query", "execute_function", "should_bypass_router", "preload_models", "http_session"}:
        from core import llm

        return getattr(llm, name)

    raise AttributeError(f"module 'core' has no attribute {name!r}")
