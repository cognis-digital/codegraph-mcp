"""Package-level smoke tests: version, public re-exports, __main__ entry."""
import subprocess
import sys

import codegraph
from codegraph.extractors import (
    CSharpExtractor,
    GoExtractor,
    JavaExtractor,
    JsExtractor,
    PythonExtractor,
    RustExtractor,
    extractor_for,
    language_for,
)


def test_version_string():
    assert isinstance(codegraph.__version__, str)
    parts = codegraph.__version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


def test_extractor_public_exports_instantiate():
    for cls in (PythonExtractor, JsExtractor, GoExtractor, RustExtractor,
                JavaExtractor, CSharpExtractor):
        assert hasattr(cls(), "extract")


def test_extractor_registry_round_trip():
    for lang in ("python", "javascript", "typescript", "go", "rust", "java", "csharp"):
        assert extractor_for(lang) is not None
    assert language_for("x.py") == "python"


def test_module_main_help_runs():
    # `python -m codegraph --help` should exit 0 and mention usage
    proc = subprocess.run([sys.executable, "-m", "codegraph", "--help"],
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert "usage" in proc.stdout.lower()
