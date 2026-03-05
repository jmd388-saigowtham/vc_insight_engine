"""Sandbox executor — runs Python code in a subprocess with safety restrictions.

Security model:
1. AST-based static analysis to detect dangerous patterns before execution
2. Import allow-listing
3. Subprocess isolation with timeout
4. Stdout/stderr capture
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from shared.python.schemas import CodeExecutionResult

# ---------------------------------------------------------------------------
# Default allowed imports
# ---------------------------------------------------------------------------

DEFAULT_ALLOWED_IMPORTS: list[str] = [
    "pandas",
    "numpy",
    "scipy",
    "sklearn",
    "scikit-learn",
    "matplotlib",
    "plotly",
    "seaborn",
    "shap",
    "math",
    "statistics",
    "collections",
    "itertools",
    "functools",
    "datetime",
    "json",
    "csv",
    "re",
    "pathlib",
    "typing",
    "dataclasses",
    "textwrap",
    "io",
    "decimal",
    "fractions",
    "copy",
    "operator",
    "string",
    "enum",
    "abc",
    "warnings",
    "pydantic",
    "openpyxl",
    "joblib",
    "pickle",
]

# Patterns / functions considered dangerous
_DANGEROUS_CALLS: set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "breakpoint",
    "exit",
    "quit",
}

_DANGEROUS_ATTR_CHAINS: list[list[str]] = [
    ["os", "system"],
    ["os", "popen"],
    ["os", "exec"],
    ["os", "execvp"],
    ["os", "execvpe"],
    ["os", "remove"],
    ["os", "unlink"],
    ["os", "rmdir"],
    ["os", "removedirs"],
    ["subprocess", "call"],
    ["subprocess", "run"],
    ["subprocess", "Popen"],
    ["subprocess", "check_output"],
    ["shutil", "rmtree"],
    ["shutil", "move"],
]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExecutionInput(BaseModel):
    code: str
    timeout: int = 60
    allowed_imports: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_IMPORTS))
    working_dir: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AST-based static analysis
# ---------------------------------------------------------------------------


class _SafetyVisitor(ast.NodeVisitor):
    """Walk the AST looking for dangerous patterns."""

    def __init__(self, allowed_imports: list[str]) -> None:
        self.allowed_imports = {m.split(".")[0] for m in allowed_imports}
        self.issues: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top_level = alias.name.split(".")[0]
            if top_level not in self.allowed_imports:
                self.issues.append(f"Import not allowed: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top_level = node.module.split(".")[0]
            if top_level not in self.allowed_imports:
                self.issues.append(f"Import not allowed: {node.module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Direct dangerous calls: eval(...), exec(...)
        if isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS_CALLS:
            self.issues.append(f"Dangerous call: {node.func.id}()")

        # Attribute chain calls: os.system(...)
        if isinstance(node.func, ast.Attribute):
            chain = _get_attr_chain(node.func)
            if chain is not None:
                for dangerous in _DANGEROUS_ATTR_CHAINS:
                    if len(chain) >= len(dangerous) and chain[: len(dangerous)] == dangerous:
                        self.issues.append(f"Dangerous call: {'.'.join(dangerous)}()")

        self.generic_visit(node)


def _get_attr_chain(node: ast.expr) -> list[str] | None:
    """Resolve ``a.b.c`` to ``['a', 'b', 'c']``."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_code(code: str, allowed_imports: list[str] | None = None) -> ValidationResult:
    """Static analysis — check for dangerous operations before execution."""
    if allowed_imports is None:
        allowed_imports = DEFAULT_ALLOWED_IMPORTS

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return ValidationResult(valid=False, issues=[f"Syntax error: {exc}"])

    visitor = _SafetyVisitor(allowed_imports)
    visitor.visit(tree)

    return ValidationResult(valid=len(visitor.issues) == 0, issues=visitor.issues)


def run(input: ExecutionInput) -> CodeExecutionResult:
    """Execute Python code in a subprocess with timeout and safety restrictions."""

    # 1. Validate code first
    validation = validate_code(input.code, input.allowed_imports)
    if not validation.valid:
        return CodeExecutionResult(
            stdout="",
            stderr="Code validation failed:\n" + "\n".join(f"  - {i}" for i in validation.issues),
            exit_code=1,
            execution_time=0.0,
        )

    # 2. Determine working directory
    if input.working_dir:
        work_dir = Path(input.working_dir).resolve()
        if not work_dir.is_dir():
            return CodeExecutionResult(
                stdout="",
                stderr=f"Working directory does not exist: {work_dir}",
                exit_code=1,
                execution_time=0.0,
            )
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="vc_sandbox_"))

    # 3. Write code to temp file
    code_file = work_dir / "_sandbox_exec.py"
    code_file.write_text(input.code, encoding="utf-8")

    # 4. Snapshot files before execution (to detect created files)
    files_before = set()
    try:
        files_before = {str(p) for p in work_dir.rglob("*") if p.is_file()}
    except Exception:
        pass

    # 5. Run in subprocess
    start = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, str(code_file)],
            capture_output=True,
            text=True,
            timeout=input.timeout,
            cwd=str(work_dir),
        )
        elapsed = time.perf_counter() - start

        # 6. Detect newly created files
        files_after = set()
        try:
            files_after = {str(p) for p in work_dir.rglob("*") if p.is_file()}
        except Exception:
            pass
        new_files = sorted(files_after - files_before - {str(code_file)})

        return CodeExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            execution_time=round(elapsed, 3),
            files_created=new_files,
        )

    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return CodeExecutionResult(
            stdout="",
            stderr=f"Execution timed out after {input.timeout} seconds",
            exit_code=124,
            execution_time=round(elapsed, 3),
        )
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return CodeExecutionResult(
            stdout="",
            stderr=f"Execution error: {exc}",
            exit_code=1,
            execution_time=round(elapsed, 3),
        )
    finally:
        # Clean up the temp script
        try:
            code_file.unlink(missing_ok=True)
        except Exception:
            pass
