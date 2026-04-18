"""
jupyter_layer — thin Panel > Object layer over Jupyter kernels.

Public API:
  KernelSession   — manages one kernel process (start/stop/run)
  JupyterScope    — L0 view of kernel namespace (IDs + lazy fetch)
  Panel           — named container with child JupyterObjects
  JupyterObject   — single named value with lazy materialization
  LocalStore      — JSON file store scoped to a panel name
"""

from .kernel import KernelSession
from .scope import JupyterScope
from .panel import Panel, JupyterObject
from .store import LocalStore

__all__ = [
    "KernelSession",
    "JupyterScope",
    "Panel",
    "JupyterObject",
    "LocalStore",
]
