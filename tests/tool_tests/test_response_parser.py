"""
Unit tests for execution/response_parser.py

Tests the LLM response parsing functionality including:
- ParsedResponse dataclass
- ResponseParser class
- Tool call extraction
- Inline call parsing
- Raw bash block detection
"""

from unittest.mock import Mock

import pytest

from harness.execution.response_parser import (SHELL_BLOCK_LANGS,
                                               ParsedResponse, ResponseParser)


class TestParsedResponse:
    """Tests for the ParsedResponse dataclass"""

    def test_empty_response(self):
        """Test empty parsed response"""
        response = ParsedResponse(content="")
        assert response.content == ""
        assert response.tool_calls == []
        assert response.inline_calls == []
        assert response.raw_bash_block is None
        assert response.parse_error is None

    def test_has_tool_calls_with_tool_calls(self):
        """Test has_tool_calls with standard tool calls"""
        response = ParsedResponse(content="", tool_calls=[Mock()])
        assert response.has_tool_calls is True

    def test_has_tool_calls_with_inline_calls(self):
        """Test has_tool_calls with inline calls"""
        response = ParsedResponse(content="", inline_calls=[Mock()])
        assert response.has_tool_calls is True

    def test_has_tool_calls_with_raw_bash(self):
        """Test has_tool_calls with raw bash block"""
        response = ParsedResponse(content="", raw_bash_block="echo hello")
        assert response.has_tool_calls is True

    def test_has_tool_calls_false(self):
        """Test has_tool_calls when no calls present"""
        response = ParsedResponse(content="Just text content")
        assert response.has_tool_calls is False

    def test_has_error_true(self):
        """Test has_error when parse_error is set"""
        response = ParsedResponse(content="", parse_error="Malformed code block")
        assert response.has_error is True

    def test_has_error_false(self):
        """Test has_error when no error"""
        response = ParsedResponse(content="")
        assert response.has_error is False


class TestResponseParserInit:
    """Tests for ResponseParser initialization"""

    def test_default_init(self):
        """Test default initialization"""
        parser = ResponseParser()
        assert parser.enable_inline is False
        assert parser.allowed_tool_names == set()
        assert parser.submodule_names == set()

    def test_init_with_options(self):
        """Test initialization with options"""
        parser = ResponseParser(
            enable_inline=True,
            allowed_tool_names={"tool1", "tool2"},
            submodule_names={"module1"},
        )
        assert parser.enable_inline is True
        assert parser.allowed_tool_names == {"tool1", "tool2"}
        assert parser.submodule_names == {"module1"}


class TestResponseParserParse:
    """Tests for ResponseParser.parse() method"""

    def test_parse_content_only(self):
        """Test parsing message with only content"""
        parser = ResponseParser()
        message = Mock()
        message.content = "Hello, world!"
        message.tool_calls = None

        result = parser.parse(message)
        assert result.content == "Hello, world!"
        assert result.tool_calls == []
        assert result.inline_calls == []
        assert result.raw_bash_block is None

    def test_parse_with_tool_calls(self):
        """Test parsing message with tool calls"""
        parser = ResponseParser()
        tool_call = Mock()
        message = Mock()
        message.content = ""
        message.tool_calls = [tool_call]

        result = parser.parse(message)
        assert result.tool_calls == [tool_call]

    def test_parse_with_none_content(self):
        """Test parsing message with None content"""
        parser = ResponseParser()
        message = Mock()
        message.content = None
        message.tool_calls = None

        result = parser.parse(message)
        assert result.content == ""

    def test_parse_with_inline_disabled(self):
        """Test parsing with inline disabled doesn't extract inline calls"""
        parser = ResponseParser(enable_inline=False)
        message = Mock()
        message.content = """Here's the code:
```
shell_run({"command": "ls"})
```
"""
        message.tool_calls = None

        result = parser.parse(message)
        assert result.inline_calls == []
        assert result.raw_bash_block is None

    def test_parse_detects_malformed_code_blocks(self):
        """Test that malformed code blocks are detected when inline is enabled"""
        parser = ResponseParser(enable_inline=True)
        message = Mock()
        # Unclosed code fence
        message.content = """Some text
```
unclosed block"""
        message.tool_calls = None

        result = parser.parse(message)
        assert result.has_error is True
        assert result.parse_error is not None


class TestResponseParserInlineExtraction:
    """Tests for inline call extraction"""

    def test_extract_raw_bash_block(self):
        """Test extracting raw bash command from shell block"""
        parser = ResponseParser(enable_inline=True, allowed_tool_names={"shell_run"})
        message = Mock()
        message.content = """Let me run this:
```bash
ls -la /tmp
```
"""
        message.tool_calls = None

        result = parser.parse(message)
        assert result.raw_bash_block == "ls -la /tmp"
        assert result.inline_calls == []

    def test_extract_inline_tool_call(self):
        """Test extracting inline tool call"""
        parser = ResponseParser(enable_inline=True, allowed_tool_names={"shell_run"})
        message = Mock()
        message.content = """Let me call this:
```
shell_run({"command": "ls"})
```
"""
        message.tool_calls = None

        result = parser.parse(message)
        # shell_run is a known tool, so it's detected as inline call
        assert result.raw_bash_block is None
        assert len(result.inline_calls) > 0

    def test_shell_block_with_known_function(self):
        """Test shell block that contains a known function call"""
        parser = ResponseParser(enable_inline=True, allowed_tool_names={"shell_run"})
        message = Mock()
        message.content = """```bash
shell_run({"command": "ls"})
```
"""
        message.tool_calls = None

        result = parser.parse(message)
        # Known function in shell block = inline call, not raw bash
        assert result.raw_bash_block is None

    def test_unknown_function_in_shell_block(self):
        """Test unknown function in shell block is treated as raw bash"""
        parser = ResponseParser(enable_inline=True, allowed_tool_names={"other_tool"})
        message = Mock()
        message.content = """```bash
some_unknown_command arg1 arg2
```
"""
        message.tool_calls = None

        result = parser.parse(message)
        assert result.raw_bash_block == "some_unknown_command arg1 arg2"


class TestShellBlockLangs:
    """Tests for SHELL_BLOCK_LANGS constant"""

    def test_contains_expected_langs(self):
        """Test that expected shell languages are in the set"""
        assert "bash" in SHELL_BLOCK_LANGS
        assert "sh" in SHELL_BLOCK_LANGS
        assert "shell" in SHELL_BLOCK_LANGS
        assert "zsh" in SHELL_BLOCK_LANGS
        assert "fish" in SHELL_BLOCK_LANGS
        assert "" in SHELL_BLOCK_LANGS  # Empty/unspecified

    def test_is_frozen_set(self):
        """Test that SHELL_BLOCK_LANGS is a frozenset"""
        assert isinstance(SHELL_BLOCK_LANGS, frozenset)


class TestIsShellBlock:
    """Tests for ResponseParser._is_shell_block() method"""

    def test_shell_languages(self):
        """Test detection of shell-like languages"""
        parser = ResponseParser()
        assert parser._is_shell_block("bash") is True
        assert parser._is_shell_block("sh") is True
        assert parser._is_shell_block("shell") is True
        assert parser._is_shell_block("zsh") is True
        assert parser._is_shell_block("") is True
        assert parser._is_shell_block(None) is True

    def test_non_shell_languages(self):
        """Test detection of non-shell languages"""
        parser = ResponseParser()
        assert parser._is_shell_block("python") is False
        assert parser._is_shell_block("javascript") is False
        assert parser._is_shell_block("json") is False

    def test_case_insensitive(self):
        """Test that detection is case insensitive"""
        parser = ResponseParser()
        assert parser._is_shell_block("BASH") is True
        assert parser._is_shell_block("Bash") is True
        assert parser._is_shell_block("SHELL") is True


class TestLooksLikeToolCall:
    """Tests for ResponseParser._looks_like_tool_call() method"""

    def test_known_tool_name(self):
        """Test detection of known tool name"""
        parser = ResponseParser(allowed_tool_names={"shell_run", "fs_write"})
        assert parser._looks_like_tool_call("shell_run({})") is True
        assert parser._looks_like_tool_call("fs_write({})") is True

    def test_known_submodule_name(self):
        """Test detection of known submodule name"""
        parser = ResponseParser(submodule_names={"analyze_code"})
        assert parser._looks_like_tool_call("analyze_code({})") is True

    def test_unknown_function(self):
        """Test that unknown functions are not detected"""
        parser = ResponseParser(allowed_tool_names={"shell_run"})
        assert parser._looks_like_tool_call("unknown_func({})") is False

    def test_non_function_content(self):
        """Test that non-function content is not detected"""
        parser = ResponseParser(allowed_tool_names={"shell_run"})
        assert parser._looks_like_tool_call("ls -la") is False
        assert parser._looks_like_tool_call("echo hello") is False
        assert parser._looks_like_tool_call("") is False

    def test_whitespace_handling(self):
        """Test handling of leading whitespace"""
        parser = ResponseParser(allowed_tool_names={"shell_run"})
        assert parser._looks_like_tool_call("  shell_run({})") is True
        assert parser._looks_like_tool_call("\tshell_run({})") is True
