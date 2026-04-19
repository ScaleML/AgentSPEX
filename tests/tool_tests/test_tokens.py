"""
Unit tests for llms/tokens.py

Tests the token counting and usage extraction functionality including:
- Token usage extraction from LLM responses
- Model context limit lookups
- Message token counting
"""

from unittest.mock import Mock

import pytest

from harness.llms.tokens import (count_message_tokens, extract_token_usage,
                                 get_model_context_limit)


class TestExtractTokenUsage:
    """Tests for the extract_token_usage function"""

    def test_none_usage(self):
        """Test with None usage returns zeros"""
        result = extract_token_usage(None)
        assert result == {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
        }

    def test_basic_usage_object(self):
        """Test with basic usage object"""
        usage = Mock()
        usage.total_tokens = 100
        usage.prompt_tokens = 60
        usage.completion_tokens = 40
        usage.reasoning_tokens = 10
        usage.completion_tokens_details = None
        usage.output_tokens_details = None

        result = extract_token_usage(usage)
        assert result["total_tokens"] == 100
        assert result["prompt_tokens"] == 60
        assert result["completion_tokens"] == 40
        assert result["reasoning_tokens"] == 10

    def test_reasoning_tokens_from_completion_details(self):
        """Test extracting reasoning tokens from completion_tokens_details"""
        usage = Mock()
        usage.total_tokens = 100
        usage.prompt_tokens = 60
        usage.completion_tokens = 40
        usage.reasoning_tokens = 0  # Zero here

        # Create completion_tokens_details with reasoning_tokens
        details = Mock()
        details.reasoning_tokens = 15
        usage.completion_tokens_details = details
        usage.output_tokens_details = None

        result = extract_token_usage(usage)
        assert result["reasoning_tokens"] == 15

    def test_reasoning_tokens_from_output_details(self):
        """Test extracting reasoning tokens from output_tokens_details"""
        usage = Mock()
        usage.total_tokens = 100
        usage.prompt_tokens = 60
        usage.completion_tokens = 40
        usage.reasoning_tokens = 0
        usage.completion_tokens_details = None

        # Create output_tokens_details with reasoning_tokens
        details = Mock()
        details.reasoning_tokens = 20
        usage.output_tokens_details = details

        result = extract_token_usage(usage)
        assert result["reasoning_tokens"] == 20

    def test_missing_attributes(self):
        """Test with object missing some attributes"""
        usage = Mock(spec=[])  # No attributes

        result = extract_token_usage(usage)
        assert result == {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
        }

    def test_none_values_in_usage(self):
        """Test with None values in usage object"""
        usage = Mock()
        usage.total_tokens = None
        usage.prompt_tokens = None
        usage.completion_tokens = None
        usage.reasoning_tokens = None
        usage.completion_tokens_details = None
        usage.output_tokens_details = None

        result = extract_token_usage(usage)
        assert result["total_tokens"] == 0
        assert result["prompt_tokens"] == 0
        assert result["completion_tokens"] == 0
        assert result["reasoning_tokens"] == 0


class TestGetModelContextLimit:
    """Tests for the get_model_context_limit function"""

    def test_known_models(self):
        """Test context limits for known models"""
        assert get_model_context_limit("gpt-4o") == 128_000
        assert get_model_context_limit("gpt-4o-mini") == 128_000
        assert get_model_context_limit("gpt-4-turbo") == 128_000
        assert get_model_context_limit("gpt-4") == 8_192
        assert get_model_context_limit("gpt-4-32k") == 32_768
        assert get_model_context_limit("gpt-3.5-turbo") == 16_385
        assert get_model_context_limit("gpt-5") == 272_000
        assert get_model_context_limit("gpt-5-mini") == 272_000

    def test_unknown_model_default(self):
        """Test that unknown models get default context limit"""
        assert get_model_context_limit("unknown-model") == 128_000
        assert get_model_context_limit("custom-model-v1") == 128_000
        assert get_model_context_limit("") == 128_000


class TestCountMessageTokens:
    """Tests for the count_message_tokens function"""

    def test_simple_message(self):
        """Test counting tokens in a simple message"""
        messages = [{"role": "user", "content": "Hello, how are you?"}]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 0

    def test_multiple_messages(self):
        """Test counting tokens in multiple messages"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there! How can I help?"},
        ]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 0

    def test_empty_messages(self):
        """Test counting tokens in empty message list"""
        messages = []
        count = count_message_tokens(messages, "gpt-4o")
        assert count == 0

    def test_message_with_tool_calls(self):
        """Test counting tokens in message with tool calls"""
        tool_call = Mock()
        tool_call.function = Mock()
        tool_call.function.name = "get_weather"
        tool_call.function.arguments = '{"location": "New York"}'

        messages = [{"role": "assistant", "content": "", "tool_calls": [tool_call]}]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 0

    def test_message_with_empty_tool_calls(self):
        """Test counting tokens in message with empty tool_calls"""
        messages = [{"role": "assistant", "content": "Some response", "tool_calls": []}]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 0

    def test_message_with_none_tool_calls(self):
        """Test counting tokens in message with None tool_calls"""
        messages = [
            {"role": "assistant", "content": "Some response", "tool_calls": None}
        ]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 0

    def test_fallback_tokenizer(self):
        """Test that unknown models use fallback tokenizer"""
        messages = [{"role": "user", "content": "Test message"}]
        # Should not raise and should return a count
        count = count_message_tokens(messages, "unknown-model-xyz")
        assert count > 0

    def test_non_string_values_skipped(self):
        """Test that non-string values are handled gracefully"""
        messages = [{"role": "user", "content": "Hello", "extra_data": 12345}]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 0

    def test_long_message(self):
        """Test counting tokens in a long message"""
        long_text = "This is a test. " * 1000
        messages = [{"role": "user", "content": long_text}]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 1000  # Should be roughly 4000+ tokens

    def test_unicode_content(self):
        """Test counting tokens with unicode content"""
        messages = [
            {"role": "user", "content": "Hello! \u4f60\u597d\u4e16\u754c! \ud83d\ude00"}
        ]
        count = count_message_tokens(messages, "gpt-4o")
        assert count > 0
