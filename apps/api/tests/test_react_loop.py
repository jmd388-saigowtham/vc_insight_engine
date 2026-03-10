"""Tests for the ReAct execution loop in node_helpers.

Proves:
- react_execute succeeds on first try with correct trace events
- react_execute retries on action failure then succeeds
- react_execute retries on validation failure then succeeds
- react_execute escalates (returns None) after max retries exhausted
- Trace events contain correct phases (think, observe, reflect, escalate)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.agent.nodes.node_helpers import react_execute


def _make_state():
    """Create a minimal AgentState for testing."""
    return {
        "session_id": "test-session",
        "trace_events": [],
    }


@pytest.mark.asyncio
async def test_react_execute_success_first_try():
    """Should return result immediately on first success."""
    state = _make_state()

    async def action_fn(s):
        return {"value": 42}

    def validate_fn(result):
        return (True, "Looks good")

    result = await react_execute(state, "test_step", action_fn, validate_fn)
    assert result is not None
    assert result["value"] == 42

    # Should have think + observe + reflect trace events
    events = state["trace_events"]
    phases = [e["payload"]["phase"] for e in events if e["event_type"] == "AI_REASONING"]
    assert "think" in phases
    assert "observe" in phases
    assert "reflect" in phases


@pytest.mark.asyncio
async def test_react_execute_retry_then_success():
    """Should retry on failure then succeed."""
    state = _make_state()
    call_count = 0

    async def action_fn(s):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Not ready yet")
        return {"value": "success"}

    def validate_fn(result):
        return (True, "OK")

    result = await react_execute(state, "test_step", action_fn, validate_fn, max_retries=3)
    assert result is not None
    assert result["value"] == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_react_execute_validation_failure_then_success():
    """Should retry on validation failure then succeed."""
    state = _make_state()
    call_count = 0

    async def action_fn(s):
        nonlocal call_count
        call_count += 1
        return {"attempt": call_count}

    def validate_fn(result):
        if result["attempt"] < 2:
            return (False, "Metrics too low")
        return (True, "Metrics acceptable")

    result = await react_execute(state, "test_step", action_fn, validate_fn, max_retries=3)
    assert result is not None
    assert result["attempt"] == 2


@pytest.mark.asyncio
async def test_react_execute_escalation():
    """Should return None after max retries exhausted."""
    state = _make_state()

    async def action_fn(s):
        raise ValueError("Always fails")

    def validate_fn(result):
        return (False, "Never validates")

    result = await react_execute(state, "test_step", action_fn, validate_fn, max_retries=2)
    assert result is None

    # Should have escalate trace event
    events = state["trace_events"]
    phases = [e["payload"]["phase"] for e in events if e["event_type"] == "AI_REASONING"]
    assert "escalate" in phases


@pytest.mark.asyncio
async def test_react_execute_single_retry_limit():
    """With max_retries=1, should fail immediately on first error."""
    state = _make_state()

    async def action_fn(s):
        raise RuntimeError("Kaboom")

    def validate_fn(result):
        return (True, "OK")

    result = await react_execute(state, "test_step", action_fn, validate_fn, max_retries=1)
    assert result is None

    events = state["trace_events"]
    phases = [e["payload"]["phase"] for e in events if e["event_type"] == "AI_REASONING"]
    assert "think" in phases
    assert "observe" in phases
    assert "escalate" in phases


@pytest.mark.asyncio
async def test_react_execute_validation_always_fails():
    """Validation always failing should escalate after max retries."""
    state = _make_state()

    async def action_fn(s):
        return {"metrics": {"f1": 0.1}}

    def validate_fn(result):
        return (False, "F1 score below threshold")

    result = await react_execute(state, "test_step", action_fn, validate_fn, max_retries=2)
    assert result is None

    events = state["trace_events"]
    phases = [e["payload"]["phase"] for e in events if e["event_type"] == "AI_REASONING"]
    assert "escalate" in phases
    # Should have 2 think phases (one per attempt)
    think_count = sum(1 for p in phases if p == "think")
    assert think_count == 2


@pytest.mark.asyncio
async def test_react_execute_trace_event_attempt_numbers():
    """Trace events should have correct attempt numbers."""
    state = _make_state()
    call_count = 0

    async def action_fn(s):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Retry needed")
        return {"done": True}

    def validate_fn(result):
        return (True, "Success")

    await react_execute(state, "test_step", action_fn, validate_fn, max_retries=3)

    events = state["trace_events"]
    think_events = [
        e for e in events
        if e["event_type"] == "AI_REASONING" and e["payload"]["phase"] == "think"
    ]
    assert len(think_events) == 2
    assert think_events[0]["payload"]["attempt"] == 1
    assert think_events[1]["payload"]["attempt"] == 2


@pytest.mark.asyncio
async def test_react_execute_all_events_have_correct_step():
    """All emitted trace events should reference the correct step name."""
    state = _make_state()

    async def action_fn(s):
        return {"ok": True}

    def validate_fn(result):
        return (True, "Valid")

    await react_execute(state, "my_custom_step", action_fn, validate_fn)

    events = state["trace_events"]
    assert len(events) > 0
    for event in events:
        assert event["step"] == "my_custom_step"
