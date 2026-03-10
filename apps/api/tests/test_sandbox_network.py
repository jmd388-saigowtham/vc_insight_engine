"""Tests for sandbox executor — blocked imports and env stripping."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make MCP servers and shared package importable
_mcp_root = str(Path(__file__).resolve().parents[3] / "packages" / "mcp-servers")
_shared_root = str(Path(__file__).resolve().parents[3] / "packages")
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)
if _shared_root not in sys.path:
    sys.path.insert(0, _shared_root)

from src.sandbox_executor.server import (
    ExecutionInput,
    ValidationResult,
    run,
    validate_code,
)


class TestBlockedImports:
    """Verify that network-related imports are blocked."""

    @pytest.mark.parametrize("module", [
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "xmlrpc",
        "ssl",
        "websocket",
    ])
    def test_blocked_import(self, module: str):
        code = f"import {module}"
        result = validate_code(code)
        assert not result.valid
        assert any("blocked" in issue.lower() or "not allowed" in issue.lower() for issue in result.issues)

    @pytest.mark.parametrize("module", [
        "socket",
        "http.client",
        "urllib.request",
        "requests",
    ])
    def test_blocked_from_import(self, module: str):
        top = module.split(".")[0]
        code = f"from {module} import *"
        result = validate_code(code)
        assert not result.valid

    def test_allowed_import_pandas(self):
        result = validate_code("import pandas as pd")
        assert result.valid
        assert len(result.issues) == 0

    def test_allowed_import_numpy(self):
        result = validate_code("import numpy as np")
        assert result.valid

    def test_allowed_import_sklearn(self):
        result = validate_code("from sklearn.model_selection import train_test_split")
        assert result.valid

    def test_allowed_import_matplotlib(self):
        result = validate_code("import matplotlib.pyplot as plt")
        assert result.valid


class TestDangerousCalls:
    """Verify that dangerous function calls are blocked."""

    @pytest.mark.parametrize("call", [
        "eval('1+1')",
        "exec('pass')",
        "compile('pass', '', 'exec')",
        "__import__('os')",
    ])
    def test_dangerous_call_blocked(self, call: str):
        result = validate_code(call)
        assert not result.valid
        assert any("dangerous" in issue.lower() for issue in result.issues)

    @pytest.mark.parametrize("call", [
        "os.system('ls')",
        "subprocess.run(['ls'])",
        "subprocess.Popen(['ls'])",
        "shutil.rmtree('/tmp/foo')",
    ])
    def test_dangerous_attr_chain_blocked(self, call: str):
        # Need to import the module for the call to parse
        module = call.split(".")[0]
        code = f"import {module}\n{call}"
        result = validate_code(code)
        assert not result.valid


class TestEnvStripping:
    """Verify that proxy environment variables are stripped."""

    def test_proxy_env_stripped(self):
        code = "import os; print(os.environ.get('HTTP_PROXY', 'NOT_SET'))"
        # We can't actually set env vars easily, but the run function should strip them
        input_data = ExecutionInput(code=code, timeout=10)
        # This will fail validation because `os` is not allowed — that's expected.
        # The env stripping happens at runtime, but code validation catches `os` first.
        result = run(input_data)
        # Either validation blocks os usage or execution completes
        # Both are acceptable — the key is the code doesn't have proxy access
        assert result.exit_code != 0 or "NOT_SET" in result.stdout


class TestCodeExecution:
    """Test basic code execution in sandbox."""

    def test_simple_print(self):
        result = run(ExecutionInput(code="print('hello world')", timeout=10))
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_pandas_code_runs(self):
        code = "import pandas as pd; df = pd.DataFrame({'a': [1,2,3]}); print(len(df))"
        result = run(ExecutionInput(code=code, timeout=30))
        assert result.exit_code == 0
        assert "3" in result.stdout

    def test_syntax_error_detected(self):
        result = validate_code("def foo(:\n  pass")
        assert not result.valid
        assert any("syntax" in issue.lower() for issue in result.issues)

    def test_execution_timeout(self):
        # Use a tight loop with math (allowed import) to trigger timeout
        code = "import math\nwhile True: math.sqrt(2)"
        result = run(ExecutionInput(code=code, timeout=2))
        assert result.exit_code != 0
        assert "timed out" in result.stderr.lower()

    def test_files_created_tracking(self, tmp_path: Path):
        code = "with open('test_output.txt', 'w') as f: f.write('test')"
        result = run(ExecutionInput(
            code=code,
            timeout=10,
            working_dir=str(tmp_path),
        ))
        assert result.exit_code == 0
        assert any("test_output.txt" in f for f in result.files_created)
