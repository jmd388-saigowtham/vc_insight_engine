"""Tests for invoke_llm_json retry and parse logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestInvokeLlmJson:
    @pytest.mark.asyncio
    @patch("app.agent.llm.invoke_llm")
    async def test_valid_json_response(self, mock_invoke):
        from app.agent.llm import invoke_llm_json

        mock_invoke.return_value = '{"next_action": "profiling", "reasoning": "start"}'
        result = await invoke_llm_json([{"role": "user", "content": "test"}])
        assert result == {"next_action": "profiling", "reasoning": "start"}
        mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.agent.llm.invoke_llm")
    async def test_strips_markdown_fences(self, mock_invoke):
        from app.agent.llm import invoke_llm_json

        mock_invoke.return_value = '```json\n{"key": "value"}\n```'
        result = await invoke_llm_json([{"role": "user", "content": "test"}])
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    @patch("app.agent.llm.invoke_llm")
    async def test_retries_on_invalid_json(self, mock_invoke):
        from app.agent.llm import invoke_llm_json

        mock_invoke.side_effect = [
            "not json at all",
            '{"valid": "json"}',
        ]
        result = await invoke_llm_json(
            [{"role": "user", "content": "test"}],
            max_retries=2,
        )
        assert result == {"valid": "json"}
        assert mock_invoke.call_count == 2

    @pytest.mark.asyncio
    @patch("app.agent.llm.invoke_llm")
    async def test_raises_after_max_retries(self, mock_invoke):
        from app.agent.llm import invoke_llm_json

        mock_invoke.return_value = "always invalid"
        with pytest.raises(ValueError, match="Failed to get valid JSON"):
            await invoke_llm_json(
                [{"role": "user", "content": "test"}],
                max_retries=2,
            )
        assert mock_invoke.call_count == 2

    @pytest.mark.asyncio
    @patch("app.agent.llm.invoke_llm")
    async def test_retry_appends_error_feedback(self, mock_invoke):
        from app.agent.llm import invoke_llm_json

        mock_invoke.side_effect = [
            "invalid json",
            '{"ok": true}',
        ]
        result = await invoke_llm_json(
            [{"role": "user", "content": "test"}],
            schema_hint='{"key": "value"}',
            max_retries=3,
        )
        assert result == {"ok": True}
        # The second call should have error feedback appended
        second_call_messages = mock_invoke.call_args_list[1][0][0]
        assert any("not valid JSON" in msg.get("content", "") for msg in second_call_messages)

    @pytest.mark.asyncio
    @patch("app.agent.llm.invoke_llm")
    async def test_rejects_non_dict_json(self, mock_invoke):
        from app.agent.llm import invoke_llm_json

        mock_invoke.side_effect = [
            '[1, 2, 3]',  # valid JSON but not a dict
            '{"actual": "dict"}',
        ]
        result = await invoke_llm_json(
            [{"role": "user", "content": "test"}],
            max_retries=2,
        )
        assert result == {"actual": "dict"}


class TestStripJsonFences:
    def test_no_fences(self):
        from app.agent.llm import _strip_json_fences

        assert _strip_json_fences('{"key": "value"}') == '{"key": "value"}'

    def test_json_fences(self):
        from app.agent.llm import _strip_json_fences

        assert _strip_json_fences('```json\n{"key": "value"}\n```') == '{"key": "value"}'

    def test_plain_fences(self):
        from app.agent.llm import _strip_json_fences

        assert _strip_json_fences('```\n{"key": "value"}\n```') == '{"key": "value"}'

    def test_whitespace(self):
        from app.agent.llm import _strip_json_fences

        result = _strip_json_fences('  \n```json\n{"key": "value"}\n```\n  ')
        assert result == '{"key": "value"}'
