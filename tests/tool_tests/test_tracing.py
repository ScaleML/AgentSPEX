"""
Unit tests for checkpoints/tracing.py and checkpoints/durable_execution.py

Tests the tracing and durable execution functionality including:
- JSONL file operations
- TraceReplayer class
- TraceWriter class
- TracingMixin class
"""

import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from harness.checkpoints.durable_execution import (ReplayFunction,
                                                   ReplayMessage,
                                                   ReplayToolCall,
                                                   TraceReplayer, TraceWriter,
                                                   append_jsonl, iter_jsonl)
from harness.checkpoints.tracing import TracingMixin


class TestAppendJsonl:
    """Tests for append_jsonl function"""

    def test_append_single_event(self, tmp_path):
        """Test appending a single event"""
        path = tmp_path / "trace.jsonl"
        event = {"type": "test", "data": "value"}

        append_jsonl(path, event)

        with open(path) as f:
            line = f.readline()
            loaded = json.loads(line)
            assert loaded == event

    def test_append_multiple_events(self, tmp_path):
        """Test appending multiple events"""
        path = tmp_path / "trace.jsonl"
        events = [
            {"type": "event1", "id": 1},
            {"type": "event2", "id": 2},
            {"type": "event3", "id": 3},
        ]

        for event in events:
            append_jsonl(path, event)

        with open(path) as f:
            lines = f.readlines()
            assert len(lines) == 3
            for i, line in enumerate(lines):
                assert json.loads(line) == events[i]

    def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created"""
        path = tmp_path / "nested" / "deep" / "trace.jsonl"
        event = {"type": "test"}

        append_jsonl(path, event)

        assert path.exists()

    def test_unicode_content(self, tmp_path):
        """Test handling of unicode content"""
        path = tmp_path / "trace.jsonl"
        event = {"type": "test", "content": "\u4f60\u597d\u4e16\u754c"}

        append_jsonl(path, event)

        with open(path, encoding="utf-8") as f:
            loaded = json.loads(f.readline())
            assert loaded["content"] == "\u4f60\u597d\u4e16\u754c"


class TestIterJsonl:
    """Tests for iter_jsonl function"""

    def test_read_events(self, tmp_path):
        """Test reading events from JSONL file"""
        path = tmp_path / "trace.jsonl"
        events = [{"id": 1}, {"id": 2}, {"id": 3}]

        with open(path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        result = list(iter_jsonl(path))
        assert result == events

    def test_skip_empty_lines(self, tmp_path):
        """Test that empty lines are skipped"""
        path = tmp_path / "trace.jsonl"

        with open(path, "w") as f:
            f.write('{"id": 1}\n')
            f.write("\n")  # Empty line
            f.write('{"id": 2}\n')
            f.write("   \n")  # Whitespace-only line
            f.write('{"id": 3}\n')

        result = list(iter_jsonl(path))
        assert len(result) == 3

    def test_empty_file(self, tmp_path):
        """Test reading empty file"""
        path = tmp_path / "trace.jsonl"
        path.touch()

        result = list(iter_jsonl(path))
        assert result == []


class TestReplayDataclasses:
    """Tests for replay-related dataclasses"""

    def test_replay_function(self):
        """Test ReplayFunction dataclass"""
        func = ReplayFunction(name="test_func", arguments='{"key": "value"}')
        assert func.name == "test_func"
        assert func.arguments == '{"key": "value"}'

    def test_replay_tool_call(self):
        """Test ReplayToolCall dataclass"""
        func = ReplayFunction(name="test_func", arguments="{}")
        call = ReplayToolCall(id="call_123", function=func)
        assert call.id == "call_123"
        assert call.function.name == "test_func"

    def test_replay_message(self):
        """Test ReplayMessage dataclass"""
        func = ReplayFunction(name="test_func", arguments="{}")
        call = ReplayToolCall(id="call_123", function=func)
        msg = ReplayMessage(content="Hello", tool_calls=[call])
        assert msg.content == "Hello"
        assert len(msg.tool_calls) == 1


class TestTraceReplayer:
    """Tests for TraceReplayer class"""

    def test_from_file(self, tmp_path):
        """Test creating replayer from file"""
        path = tmp_path / "trace.jsonl"
        events = [
            {
                "type": "llm_response",
                "step_id": "1",
                "iteration": 0,
                "content": "Hello",
            },
        ]

        with open(path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        replayer = TraceReplayer.from_file(path)
        assert replayer._events == events

    def test_next_llm_message(self, tmp_path):
        """Test getting next LLM message"""
        events = [
            {
                "type": "llm_response",
                "step_id": "step1",
                "iteration": 0,
                "content": "Response content",
                "tool_calls": [],
            }
        ]
        replayer = TraceReplayer(events)

        msg = replayer.next_llm_message(step_id="step1", iteration=0)
        assert msg.content == "Response content"
        assert msg.tool_calls == []

    def test_next_llm_message_with_tool_calls(self, tmp_path):
        """Test getting LLM message with tool calls"""
        events = [
            {
                "type": "llm_response",
                "step_id": "step1",
                "iteration": 0,
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {"name": "test_func", "arguments": '{"a": 1}'},
                    }
                ],
            }
        ]
        replayer = TraceReplayer(events)

        msg = replayer.next_llm_message(step_id="step1", iteration=0)
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "call_123"
        assert msg.tool_calls[0].function.name == "test_func"

    def test_next_llm_message_type_mismatch(self):
        """Test that type mismatch raises ValueError"""
        events = [{"type": "tool_result"}]
        replayer = TraceReplayer(events)

        with pytest.raises(ValueError, match="expected llm_response"):
            replayer.next_llm_message(step_id="step1", iteration=0)

    def test_next_llm_message_step_mismatch(self):
        """Test that step/iteration mismatch raises ValueError"""
        events = [
            {"type": "llm_response", "step_id": "step1", "iteration": 0, "content": ""}
        ]
        replayer = TraceReplayer(events)

        with pytest.raises(ValueError, match="trace mismatch"):
            replayer.next_llm_message(step_id="step2", iteration=0)

    def test_next_tool_result(self):
        """Test getting next tool result"""
        events = [
            {
                "type": "tool_result",
                "step_id": "step1",
                "iteration": 0,
                "call": 0,
                "name": "test_tool",
                "result": "success",
            }
        ]
        replayer = TraceReplayer(events)

        result = replayer.next_tool_result(
            step_id="step1", iteration=0, call=0, name="test_tool"
        )
        assert result["result"] == "success"

    def test_next_tool_result_mismatch(self):
        """Test tool result mismatches raise ValueError"""
        events = [
            {
                "type": "tool_result",
                "step_id": "step1",
                "iteration": 0,
                "call": 0,
                "name": "tool1",
            }
        ]
        replayer = TraceReplayer(events)

        with pytest.raises(ValueError, match="expected tool=tool2"):
            replayer.next_tool_result(
                step_id="step1", iteration=0, call=0, name="tool2"
            )

    def test_trace_exhausted(self):
        """Test that exhausted trace raises IndexError"""
        replayer = TraceReplayer([])

        with pytest.raises(IndexError, match="trace exhausted"):
            replayer.next_llm_message(step_id="step1", iteration=0)


class TestTraceWriter:
    """Tests for TraceWriter class"""

    def test_write_event(self, tmp_path):
        """Test writing an event"""
        path = tmp_path / "trace.jsonl"
        writer = TraceWriter(path)

        writer.write({"type": "test", "data": "value"})

        with open(path) as f:
            loaded = json.loads(f.readline())
            assert loaded["type"] == "test"
            assert loaded["data"] == "value"

    def test_write_multiple_events(self, tmp_path):
        """Test writing multiple events"""
        path = tmp_path / "trace.jsonl"
        writer = TraceWriter(path)

        writer.write({"id": 1})
        writer.write({"id": 2})
        writer.write({"id": 3})

        events = list(iter_jsonl(path))
        assert len(events) == 3


class TestTracingMixin:
    """Tests for TracingMixin class"""

    class TracingTestClass(TracingMixin):
        """Test class that uses TracingMixin"""

        def __init__(self):
            self._trace_lock = threading.Lock()
            self._trace_writer = None
            self._llm_replay_events = None
            self._replay_index = 0

    def test_trace_when_disabled(self):
        """Test that _trace does nothing when writer is None"""
        obj = self.TracingTestClass()
        # Should not raise
        obj._trace({"type": "test"})

    def test_trace_when_enabled(self, tmp_path):
        """Test that _trace writes when writer is set"""
        obj = self.TracingTestClass()
        obj._trace_writer = TraceWriter(tmp_path / "trace.jsonl")

        obj._trace({"type": "test", "data": "value"})

        events = list(iter_jsonl(tmp_path / "trace.jsonl"))
        assert len(events) == 1
        assert events[0]["type"] == "test"

    def test_load_replay(self, tmp_path):
        """Test loading replay events"""
        path = tmp_path / "trace.jsonl"
        events = [
            {"type": "llm_response", "step_id": "1", "iteration": 0},
            {"type": "tool_result", "step_id": "1"},  # Should be filtered
            {"type": "llm_response", "step_id": "2", "iteration": 0},
        ]
        with open(path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        obj = self.TracingTestClass()
        obj._load_replay(str(path))

        # Only llm_response events should be loaded
        assert len(obj._llm_replay_events) == 2
        assert obj._replay_index == 0

    def test_next_replay_event(self, tmp_path):
        """Test getting next replay event"""
        path = tmp_path / "trace.jsonl"
        events = [
            {
                "type": "llm_response",
                "step_id": "step1",
                "iteration": 0,
                "content": "Hello",
            },
        ]
        with open(path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        obj = self.TracingTestClass()
        obj._load_replay(str(path))

        event = obj._next_replay_event(step_id="step1", iteration=0)
        assert event["content"] == "Hello"
        assert obj._replay_index == 1

    def test_next_replay_event_not_enabled(self):
        """Test that next_replay_event raises when not enabled"""
        obj = self.TracingTestClass()

        with pytest.raises(RuntimeError, match="replay not enabled"):
            obj._next_replay_event(step_id="step1", iteration=0)

    def test_next_replay_event_exhausted(self, tmp_path):
        """Test that exhausted replay raises IndexError"""
        path = tmp_path / "trace.jsonl"
        # Write one event then consume it
        events = [
            {"type": "llm_response", "step_id": "step1", "iteration": 0},
        ]
        with open(path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        obj = self.TracingTestClass()
        obj._load_replay(str(path))

        # Consume the one event
        obj._next_replay_event(step_id="step1", iteration=0)

        # Now it should be exhausted
        with pytest.raises(IndexError, match="exhausted"):
            obj._next_replay_event(step_id="step2", iteration=0)

    def test_next_replay_event_mismatch(self, tmp_path):
        """Test that mismatched event raises ValueError"""
        path = tmp_path / "trace.jsonl"
        events = [
            {"type": "llm_response", "step_id": "step1", "iteration": 0},
        ]
        with open(path, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        obj = self.TracingTestClass()
        obj._load_replay(str(path))

        with pytest.raises(ValueError, match="mismatch"):
            obj._next_replay_event(step_id="step2", iteration=0)

    def test_trace_thread_safe(self, tmp_path):
        """Test that _trace is thread-safe"""
        obj = self.TracingTestClass()
        obj._trace_writer = TraceWriter(tmp_path / "trace.jsonl")

        results = []

        def write_events(prefix, count):
            for i in range(count):
                obj._trace({"prefix": prefix, "id": i})
            results.append(prefix)

        threads = [
            threading.Thread(target=write_events, args=("a", 10)),
            threading.Thread(target=write_events, args=("b", 10)),
            threading.Thread(target=write_events, args=("c", 10)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = list(iter_jsonl(tmp_path / "trace.jsonl"))
        assert len(events) == 30
