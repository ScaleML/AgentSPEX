"""
Unit tests for the vision/multimodal additions:

1. _trim_vision_history (llm_executor.py) — sliding window logic
2. _trim_som_elements (llm_executor.py) — AC tree truncation
3. get_yaml_system_prompt interaction_mode injection (yaml_prompts.py)
4. ContextKeys vision constants (context.py)
"""

import json

from harness.execution.llm_executor import (_trim_som_elements,
                                            _trim_vision_history)
from harness.prompts.yaml_prompts import (_SOM_ACTION_FORMAT,
                                          get_yaml_system_prompt)
from harness.types.context import ContextKeys

# ---------------------------------------------------------------------------
# _trim_vision_history
# ---------------------------------------------------------------------------


def _text_msg(text="hello"):
    return {"role": "user", "content": text}


def _image_msg(label="screenshot"):
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": f"[{label}]"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
        ],
    }


def _tool_msg():
    return {
        "role": "tool",
        "tool_call_id": "x",
        "name": "browser_navigate",
        "content": "{}",
    }


class TestTrimVisionHistory:
    def test_no_trimming_below_limit(self):
        msgs = [_image_msg("a"), _image_msg("b"), _image_msg("c")]
        _trim_vision_history(msgs, max_images=4)
        # All 3 should still have image content
        assert all(isinstance(m["content"], list) for m in msgs)

    def test_trims_oldest_when_over_limit(self):
        msgs = [_image_msg(f"shot{i}") for i in range(5)]
        _trim_vision_history(msgs, max_images=4)
        # First message should be stripped of its image
        assert isinstance(msgs[0]["content"], str)  # flattened to text string
        # Last 4 should still have image content
        for m in msgs[1:]:
            assert isinstance(m["content"], list)
            assert any(b["type"] == "image_url" for b in m["content"])

    def test_trims_multiple_oldest(self):
        msgs = [_image_msg(f"shot{i}") for i in range(7)]
        _trim_vision_history(msgs, max_images=4)
        stripped = [m for m in msgs if isinstance(m["content"], str)]
        kept = [m for m in msgs if isinstance(m["content"], list)]
        assert len(stripped) == 3
        assert len(kept) == 4

    def test_non_image_messages_untouched(self):
        msgs = [_text_msg(), _tool_msg(), _image_msg("shot")]
        _trim_vision_history(msgs, max_images=4)
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "tool"

    def test_max_images_zero_strips_all(self):
        msgs = [_image_msg("a"), _image_msg("b")]
        _trim_vision_history(msgs, max_images=0)
        assert all(isinstance(m["content"], str) for m in msgs)

    def test_stripped_message_keeps_text_label(self):
        msgs = [
            _image_msg("browser_navigate"),
            _image_msg("b"),
            _image_msg("c"),
            _image_msg("d"),
            _image_msg("e"),
        ]
        _trim_vision_history(msgs, max_images=4)
        # First message stripped; its text label should be preserved
        assert "[browser_navigate]" in msgs[0]["content"]

    def test_max_images_exactly_equal_count(self):
        msgs = [_image_msg(f"shot{i}") for i in range(4)]
        _trim_vision_history(msgs, max_images=4)
        # Exactly at limit — nothing should be stripped
        assert all(isinstance(m["content"], list) for m in msgs)

    def test_interleaved_non_image_messages(self):
        msgs = [
            _image_msg("a"),
            _text_msg(),
            _image_msg("b"),
            _tool_msg(),
            _image_msg("c"),
            _image_msg("d"),
            _image_msg("e"),
        ]
        _trim_vision_history(msgs, max_images=4)
        image_msgs = [
            m
            for m in msgs
            if isinstance(m.get("content"), list)
            and any(
                isinstance(b, dict) and b.get("type") == "image_url"
                for b in m["content"]
            )
        ]
        assert len(image_msgs) == 4


# ---------------------------------------------------------------------------
# System prompt interaction_mode injection
# ---------------------------------------------------------------------------


class _FakeArgs:
    pass


class TestSystemPromptInjection:
    def test_no_mode_no_injection(self):
        prompt = get_yaml_system_prompt("task", "goal", _FakeArgs(), context={})
        assert "INTERACTION MODE" not in prompt

    def test_som_mode_injects_som_format(self):
        ctx = {"interaction_mode": "set_of_marks"}
        prompt = get_yaml_system_prompt("task", "goal", _FakeArgs(), context=ctx)
        assert "Set-of-Marks" in prompt
        assert "Click [N]" in prompt
        assert "Type [N] [text]" in prompt

    def test_unknown_mode_no_injection(self):
        ctx = {"interaction_mode": "something_else"}
        prompt = get_yaml_system_prompt("task", "goal", _FakeArgs(), context=ctx)
        assert "INTERACTION MODE" not in prompt

    def test_som_format_does_not_contain_coords_syntax(self):
        assert "Click [x, y]" not in _SOM_ACTION_FORMAT

    def test_custom_system_prompt_with_mode(self):
        """Custom system_prompt + interaction_mode should append the format."""
        ctx = {"system_prompt": "You are an agent.", "interaction_mode": "set_of_marks"}
        prompt = get_yaml_system_prompt("task", "goal", _FakeArgs(), context=ctx)
        assert "You are an agent." in prompt
        assert "Set-of-Marks" in prompt

    def test_none_context(self):
        prompt = get_yaml_system_prompt("task", "goal", _FakeArgs(), context=None)
        assert "INTERACTION MODE" not in prompt


# ---------------------------------------------------------------------------
# ContextKeys vision constants
# ---------------------------------------------------------------------------


class TestContextKeysVision:
    def test_vision_auto_screenshot_key(self):
        assert ContextKeys.VISION_AUTO_SCREENSHOT == "vision_auto_screenshot"

    def test_vision_max_history_key(self):
        assert ContextKeys.VISION_MAX_HISTORY == "vision_max_history"


# ---------------------------------------------------------------------------
# _trim_som_elements
# ---------------------------------------------------------------------------


def _som_tool_msg(n_elements: int, url: str = "https://example.com"):
    """Tool message whose content JSON contains som_elements."""
    content = json.dumps(
        {
            "url": url,
            "som_filename": "/shots/shot.png",
            "som_elements": [
                f"id: {i}, text: elem{i}, tag: button" for i in range(1, n_elements + 1)
            ],
        }
    )
    return {
        "role": "tool",
        "tool_call_id": "x",
        "name": "browser_navigate",
        "content": content,
    }


def _plain_tool_msg():
    """Tool message with no som_elements (e.g. a non-browser tool)."""
    return {
        "role": "tool",
        "tool_call_id": "y",
        "name": "fs_read",
        "content": json.dumps({"text": "hello"}),
    }


class TestTrimSomElements:
    def test_no_trimming_below_limit(self):
        msgs = [_som_tool_msg(5), _som_tool_msg(3)]
        _trim_som_elements(msgs, max_keep=4)
        for m in msgs:
            parsed = json.loads(m["content"])
            assert isinstance(parsed["som_elements"], list)

    def test_trims_oldest_when_over_limit(self):
        msgs = [_som_tool_msg(10) for _ in range(5)]
        _trim_som_elements(msgs, max_keep=4)
        first = json.loads(msgs[0]["content"])
        assert isinstance(first["som_elements"], str)
        assert "truncated" in first["som_elements"]
        assert "10" in first["som_elements"]
        for m in msgs[1:]:
            assert isinstance(json.loads(m["content"])["som_elements"], list)

    def test_trims_multiple_oldest(self):
        msgs = [_som_tool_msg(8) for _ in range(7)]
        _trim_som_elements(msgs, max_keep=4)
        truncated = [
            m for m in msgs if "truncated" in json.loads(m["content"])["som_elements"]
        ]
        kept = [
            m
            for m in msgs
            if isinstance(json.loads(m["content"])["som_elements"], list)
        ]
        assert len(truncated) == 3
        assert len(kept) == 4

    def test_non_som_messages_untouched(self):
        plain = _plain_tool_msg()
        som = _som_tool_msg(5)
        msgs = [plain, som]
        _trim_som_elements(msgs, max_keep=4)
        assert json.loads(plain["content"]) == {"text": "hello"}

    def test_max_keep_zero_strips_all(self):
        msgs = [_som_tool_msg(5), _som_tool_msg(3)]
        _trim_som_elements(msgs, max_keep=0)
        for m in msgs:
            assert "truncated" in json.loads(m["content"])["som_elements"]

    def test_other_fields_preserved_after_truncation(self):
        msgs = [
            _som_tool_msg(6, url="https://amazon.com"),
            _som_tool_msg(4),
            _som_tool_msg(4),
            _som_tool_msg(4),
            _som_tool_msg(4),
        ]
        _trim_som_elements(msgs, max_keep=4)
        first = json.loads(msgs[0]["content"])
        assert first["url"] == "https://amazon.com"
        assert first["som_filename"] == "/shots/shot.png"
        assert "truncated" in first["som_elements"]

    def test_exactly_at_limit_no_trim(self):
        msgs = [_som_tool_msg(5) for _ in range(4)]
        _trim_som_elements(msgs, max_keep=4)
        for m in msgs:
            assert isinstance(json.loads(m["content"])["som_elements"], list)

    def test_interleaved_non_som_messages(self):
        msgs = [
            _som_tool_msg(5),
            _plain_tool_msg(),
            _som_tool_msg(3),
            _plain_tool_msg(),
            _som_tool_msg(4),
            _som_tool_msg(2),
            _som_tool_msg(7),
        ]
        _trim_som_elements(msgs, max_keep=4)
        som_msgs = [m for m in msgs if "som_elements" in m["content"]]
        truncated = [
            m
            for m in som_msgs
            if "truncated" in json.loads(m["content"])["som_elements"]
        ]
        kept = [
            m
            for m in som_msgs
            if isinstance(json.loads(m["content"])["som_elements"], list)
        ]
        assert len(truncated) == 1
        assert len(kept) == 4


# ---------------------------------------------------------------------------
# SoM action format — Thought instruction
# ---------------------------------------------------------------------------


class TestSomActionFormatThought:
    def test_thought_instruction_present(self):
        assert "Thought:" in _SOM_ACTION_FORMAT

    def test_thought_precedes_action_in_format(self):
        thought_pos = _SOM_ACTION_FORMAT.index("Thought:")
        click_pos = _SOM_ACTION_FORMAT.index("Click [N]")
        assert thought_pos < click_pos

    def test_example_included(self):
        assert "Example:" in _SOM_ACTION_FORMAT

    def test_som_format_injected_with_thought(self):
        ctx = {"interaction_mode": "set_of_marks"}
        prompt = get_yaml_system_prompt("task", "goal", _FakeArgs(), context=ctx)
        assert "Thought:" in prompt
        assert "observe" in prompt.lower()
