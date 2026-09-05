"""json_structure_summary: Infer and summarize the structure of any JSON file, even malformed ones."""

from .core import summarize_json_structure, main

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "summarize_json_structure",
    "main",
]
