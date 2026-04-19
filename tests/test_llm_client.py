"""Tests for LLM client reasoning_effort logic."""

from unittest.mock import MagicMock, patch

from harness.llms.client import LLMClient, LLMConfig


class TestReasoningEffort:
    """Verify that reasoning_effort is passed through without hardcoded defaults."""

    def _make_client(self):
        config = LLMConfig(api_key="test-key")
        return LLMClient(config)

    @patch("harness.llms.client.litellm")
    def test_no_default_reasoning_effort(self, mock_litellm):
        """LLM client should not inject reasoning_effort; respect provider defaults."""
        mock_litellm.completion.return_value = MagicMock()
        client = self._make_client()

        client.completion(
            model="claude-opus-4-6", messages=[{"role": "user", "content": "hi"}]
        )

        kwargs = mock_litellm.completion.call_args[1]
        assert "reasoning_effort" not in kwargs

    @patch("harness.llms.client.litellm")
    def test_non_opus_no_reasoning(self, mock_litellm):
        mock_litellm.completion.return_value = MagicMock()
        client = self._make_client()

        client.completion(
            model="claude-sonnet-4-6", messages=[{"role": "user", "content": "hi"}]
        )

        kwargs = mock_litellm.completion.call_args[1]
        assert "reasoning_effort" not in kwargs

    @patch("harness.llms.client.litellm")
    def test_explicit_reasoning_effort_passed_through(self, mock_litellm):
        """Explicit reasoning_effort from caller should be passed through."""
        mock_litellm.completion.return_value = MagicMock()
        client = self._make_client()

        client.completion(
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "hi"}],
            reasoning_effort="high",
        )

        kwargs = mock_litellm.completion.call_args[1]
        assert kwargs["reasoning_effort"] == "high"
