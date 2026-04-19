from harness.parsing.inline_tools import (SHELL_BLOCK_LANGS,
                                          detect_malformed_code_blocks,
                                          parse_inline_tool_calls)


class TestParseInlineToolCalls:
    """Tests for parse_inline_tool_calls function"""

    def test_parse_multiple_calls_from_single_block(self):
        """Test parsing multiple tool calls from a single code block"""
        text = """
```
math_add(a=1, b=2)
fs_read({"path": "/tmp/file.txt"})
```
"""
        calls = parse_inline_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].name == "math_add"
        assert calls[0].args == {"a": 1, "b": 2}
        assert calls[1].name == "fs_read"
        assert calls[1].args == {"path": "/tmp/file.txt"}

    def test_ignores_text_outside_code_blocks(self):
        """Test that tool call syntax outside code blocks is ignored"""
        text = "math_add(a=1, b=2)"
        calls = parse_inline_tool_calls(text)
        assert calls == []

    def test_yaml_style_tool_call_with_lang_as_tool_name(self):
        """Test YAML-style where code block language is the tool name"""
        text = """
```fs_write
path: /tmp/test.txt
content: hello world
```
"""
        calls = parse_inline_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "fs_write"
        assert calls[0].args == {"path": "/tmp/test.txt", "content": "hello world"}

    def test_shell_block_languages_not_treated_as_tool_names(self):
        """Test that shell languages (bash, sh, etc) are not treated as tool names"""
        for lang in SHELL_BLOCK_LANGS:
            text = f"""
```{lang}
echo "hello"
```
"""
            calls = parse_inline_tool_calls(text)
            # Should not parse 'bash', 'sh', etc. as tool names
            assert all(c.name != lang for c in calls)

    def test_bash_block_with_tool_call_syntax(self):
        """Test that bash blocks containing tool call syntax are parsed"""
        text = """
```bash
shell_run({"text": "ls -la"})
```
"""
        calls = parse_inline_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "shell_run"

    def test_multiple_separate_code_blocks(self):
        """Test parsing tool calls from multiple code blocks"""
        text = """
First block:
```
tool1({"a": 1})
```

Second block:
```
tool2({"b": 2})
```
"""
        calls = parse_inline_tool_calls(text)
        assert len(calls) == 2
        assert calls[0].name == "tool1"
        assert calls[1].name == "tool2"


class TestDetectMalformedCodeBlocks:
    """Tests for detect_malformed_code_blocks function"""

    def test_unclosed_fence_detected(self):
        """Test detection of unclosed code fence"""
        text = """
```bash
echo hello
"""
        error = detect_malformed_code_blocks(text)
        assert "missing a closing ```" in error

    def test_multiple_blocks_no_longer_rejected(self):
        """Test that multiple code blocks are not rejected (truncation handles them)"""
        text = """
```bash
echo hello
```

```bash
echo world
```
"""
        error = detect_malformed_code_blocks(text)
        assert (
            error == ""
        ), "Multiple blocks should not be an error; truncation handles them"

    def test_truncate_to_first_code_block(self):
        """Test that truncation keeps only the first code block"""
        from harness.parsing.inline_tools import truncate_to_first_code_block

        text = """THOUGHT: doing stuff

```bash
echo hello
```

```bash
echo world
```
"""
        result = truncate_to_first_code_block(text)
        assert "echo hello" in result
        assert "echo world" not in result

    def test_truncate_single_block_unchanged(self):
        """Test that truncation is a no-op for single block"""
        from harness.parsing.inline_tools import truncate_to_first_code_block

        text = """THOUGHT: doing stuff

```bash
echo hello
```
"""
        assert truncate_to_first_code_block(text) == text

    def test_valid_single_block_accepted(self):
        """Test that valid single block returns empty string (no error)"""
        text = """
```bash
echo hello
```
"""
        assert detect_malformed_code_blocks(text) == ""


class TestMalformedBlockTruncation:
    """Test that malformed inline tool call responses get truncated in messages."""

    def _make_llm_response(self, content, tool_calls=None):
        from unittest.mock import Mock

        usage = Mock()
        usage.total_tokens = 10
        usage.prompt_tokens = 5
        usage.completion_tokens = 5
        usage.reasoning_tokens = 0
        usage.completion_tokens_details = None
        usage.output_tokens_details = None

        msg = Mock()
        msg.content = content
        msg.tool_calls = tool_calls

        choice = Mock()
        choice.message = msg

        resp = Mock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    def _make_executor(self):
        from unittest.mock import Mock

        from harness.execution.llm_executor import LLMExecutor

        mcp_client = Mock()
        llm_client = Mock()
        usage_tracker = {
            "prompt_tokens_total": 0,
            "completion_tokens_total": 0,
            "reasoning_tokens_total": 0,
            "cost_total": 0.0,
        }
        executor = LLMExecutor(mcp_client, [], llm_client, usage_tracker)
        return executor, llm_client

    def _make_args(self, **overrides):
        from harness.types.config import EffectiveArgs

        defaults = {
            "model": "test-model",
            "max_tool_calls_per_step": 10,
            "max_tokens_per_step": 100000,
            "temperature": 0.2,
            "api_base": None,
        }
        defaults.update(overrides)
        return EffectiveArgs(**defaults)

    def test_multiple_blocks_truncated_to_first(self):
        """When the LLM returns multiple code blocks, the assistant message
        should be truncated to include only the first code block, and that
        block should be executed (not rejected)."""
        from unittest.mock import MagicMock

        executor, llm_client = self._make_executor()
        executor.mcp_client.invoke.return_value = "hello output"
        logger = MagicMock()
        logger.log_event = MagicMock()
        logger.print_messages = MagicMock()
        args = self._make_args(max_tool_calls_per_step=10)

        multi_block = (
            "THOUGHT: Let me run two commands\n\n"
            "```bash\necho hello\n```\n\n"
            "```bash\necho world\n```"
        )
        # First response: multiple blocks -> truncated to first, first block executed
        # Second response: valid plain text -> ends the loop
        llm_client.completion.side_effect = [
            self._make_llm_response(multi_block),
            self._make_llm_response("Done."),
        ]

        context = {"enable_inline_tool_calls": True}
        messages = [{"role": "user", "content": "Do something"}]

        output, tokens = executor.multi_step_tool_call_loop(
            step_id=1,
            messages=messages,
            args=args,
            logger=logger,
            tools=[],
            context=context,
        )

        # The assistant message should be truncated to the first code block only
        assistant_msgs = [
            m
            for m in messages
            if m.get("role") == "assistant" and "echo hello" in m.get("content", "")
        ]
        assert len(assistant_msgs) == 1
        assert "echo world" not in assistant_msgs[0]["content"]

    def test_multiple_blocks_truncated_in_history(self):
        """The truncated message should also appear in history_messages."""
        from unittest.mock import MagicMock

        executor, llm_client = self._make_executor()
        executor.mcp_client.invoke.return_value = "hello output"
        logger = MagicMock()
        logger.log_event = MagicMock()
        logger.print_messages = MagicMock()
        args = self._make_args(max_tool_calls_per_step=10)

        multi_block = (
            "THOUGHT: Let me run two commands\n\n"
            "```bash\necho hello\n```\n\n"
            "```bash\necho world\n```"
        )
        llm_client.completion.side_effect = [
            self._make_llm_response(multi_block),
            self._make_llm_response("Done."),
        ]

        context = {"enable_inline_tool_calls": True}
        messages = [{"role": "user", "content": "Do something"}]
        history = list(messages)

        output, tokens = executor.multi_step_tool_call_loop(
            step_id=1,
            messages=messages,
            args=args,
            logger=logger,
            tools=[],
            context=context,
            history_messages=history,
        )

        # History should have the truncated assistant message (first block only)
        assistant_in_history = [
            m
            for m in history
            if m.get("role") == "assistant" and "echo hello" in m.get("content", "")
        ]
        assert len(assistant_in_history) == 1
        assert "echo world" not in assistant_in_history[0]["content"]
