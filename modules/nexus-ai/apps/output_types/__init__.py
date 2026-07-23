"""
Output type registry + built-in types for M7.

Import this module to trigger auto-registration of all built-in output types.
"""
from . import types as _types  # noqa: F401 — side-effect: registers built-in types
from .registry import OutputTypeRegistry  # noqa: F401

__all__ = ["OutputTypeRegistry"]
