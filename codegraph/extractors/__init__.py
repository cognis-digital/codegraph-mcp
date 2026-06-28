"""Language extractors: turn source text into symbols, refs, and endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Extractor, RawEndpoint, RawRef, RawSymbol
from .python_ext import PythonExtractor
from .regex_ext import (
    CSharpExtractor,
    GoExtractor,
    JavaExtractor,
    JsExtractor,
    RustExtractor,
)

_BY_LANG: dict[str, Extractor] = {
    "python": PythonExtractor(),
    "javascript": JsExtractor("javascript"),
    "typescript": JsExtractor("typescript"),
    "go": GoExtractor(),
    "rust": RustExtractor(),
    "java": JavaExtractor(),
    "csharp": CSharpExtractor(),
}

_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
}


def language_for(path: str | Path) -> Optional[str]:
    return _BY_SUFFIX.get(Path(path).suffix.lower())


def extractor_for(lang: str) -> Optional[Extractor]:
    return _BY_LANG.get(lang)


__all__ = [
    "Extractor",
    "RawSymbol",
    "RawRef",
    "RawEndpoint",
    "PythonExtractor",
    "JsExtractor",
    "GoExtractor",
    "RustExtractor",
    "JavaExtractor",
    "CSharpExtractor",
    "language_for",
    "extractor_for",
]
