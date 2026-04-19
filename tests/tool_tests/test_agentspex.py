"""
Unit tests for AgentSPEX

Tests the YAML agent workflow execution including:
- Step execution (basic, for_each, if/else, while, switch, etc.)
- Template variable expansion in context
- Condition evaluation
- Tool calling integration
- Multi-step workflows
"""

import os
from unittest.mock import Mock, patch

import pytest
import yaml

from harness.agent import AgentSPEX
from harness.submodules import load_submodule_tools_for_yaml
from harness.tools.filtering import EffectiveToolConfig


class MockArgs:
    """Mock arguments for agent execution"""

    def __init__(self, output_dir=None):
        self.model = "gpt-4"
        self.api_base = None
        self.temperature = 0.7
        self.max_tool_calls_per_step = 5
        self.max_tokens_per_step = 4000
        self.context_threshold = 0.6
        self.workflow_file = None
        self.output_dir = output_dir


class TestAgentSPEX:
    """Test cases for AgentSPEX class"""

    @pytest.fixture
    def mock_mcp_client(self):
        """Create a mock MCP client"""
        client = Mock()
        client.list_tools.return_value = [
            {"function": Mock(name="fs_read", description="Read file")},
            {"function": Mock(name="shell_run", description="Run a shell command")},
            {"function": Mock(name="fs_write", description="Write file")},
        ]
        client.make_mcp_tool_function.return_value = Mock()
        client.process_tool_calls.return_value = ([], [])
        return client

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client"""
        client = Mock()
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "Test output"
        choice.message.tool_calls = None
        response.choices = [choice]
        client.completion.return_value = response
        client.completion.return_value = response
        return client

    @pytest.fixture
    def agent(self, mock_mcp_client):
        """Create a AgentSPEX instance with mocked dependencies"""
        with patch("harness.agent.LLMClient"):
            with patch("harness.agent.MCPClient", return_value=mock_mcp_client):
                agent = AgentSPEX(mcp_url="http://localhost:7002/mcp")
                return agent

    def test_agent_initialization(self, agent):
        """Test AgentSPEX initializes correctly"""
        assert agent.mcp_client is not None
        assert agent.llm_client is not None
        assert agent.mcp_fs_write is not None
        assert agent.mcp_fs_read is not None
        assert agent.tools is not None

    def test_expand_template_variables(self, agent):
        """Test template variable expansion"""
        context = {"topic": "AI", "counter": 5, "name": "test"}

        text = "Research {{topic}} iteration {{counter}} for {{name}}"
        result = agent.expand_template_variables(text, context)

        assert result == "Research AI iteration 5 for test"

    def test_expand_template_variables_missing(self, agent):
        """Test template expansion with missing variable"""
        context = {"existing": "value"}

        text = "Has {{existing}} but {{missing}}"
        result = agent.expand_template_variables(text, context)

        # Should keep missing variable as placeholder
        assert "value" in result
        assert "{{missing}}" in result

    def test_evaluate_condition_equality(self, agent):
        """Test condition evaluation with equality"""
        context = {"status": "complete"}

        assert agent.evaluate_condition("status == 'complete'", context)
        assert not agent.evaluate_condition("status == 'pending'", context)

    def test_evaluate_condition_numeric_comparison(self, agent):
        """Test condition evaluation with numeric comparisons"""
        context = {"counter": 5, "threshold": 10.5}

        assert agent.evaluate_condition("counter < 10", context)
        assert not agent.evaluate_condition("counter > 10", context)
        assert agent.evaluate_condition("counter <= 5", context)
        assert agent.evaluate_condition("counter >= 5", context)
        assert agent.evaluate_condition("threshold > 10", context)

    def test_evaluate_condition_truthiness(self, agent):
        """Test condition evaluation with truthiness"""
        context = {"enabled": True, "disabled": False, "exists": "yes"}

        assert agent.evaluate_condition("enabled", context)
        assert not agent.evaluate_condition("disabled", context)
        assert agent.evaluate_condition("exists", context)

    def test_execute_basic_step(self, agent, mock_llm_client):
        """Test executing a basic step"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        step_data = {"step": {"name": "test_step", "instruction": "Do something"}}

        output, tokens = agent.execute_basic_step(
            step_data, context, 1, args, mock_logger
        )

        assert output == "Test output"
        assert tokens == 100
        mock_logger.assert_called()

    def test_execute_basic_step_no_prev_output_injection(self, agent, mock_llm_client):
        """Test that basic step doesn't auto-inject prev_output into prompt"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test", "prev_output": "Previous data"}

        step_data = {"step": {"name": "test_step", "instruction": "Do something"}}

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        messages = mock_llm_client.completion.call_args.kwargs["messages"]
        user_message = [m for m in messages if m["role"] == "user"][-1]
        assert user_message["content"] == "Do something"

    def test_execute_basic_step_conversation_history(self, agent, mock_llm_client):
        """Test basic step appends to workflow-level conversation history"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        response1 = Mock()
        response1.usage.total_tokens = 100
        response1.usage.prompt_tokens = 50
        response1.usage.completion_tokens = 50
        response1.usage.reasoning_tokens = 0
        response1.usage.completion_tokens_details = None
        response1.usage.output_tokens_details = None
        response1_choice = Mock()
        response1_choice.message.content = "First reply"
        response1_choice.message.tool_calls = None
        response1.choices = [response1_choice]

        response2 = Mock()
        response2.usage.total_tokens = 100
        response2.usage.prompt_tokens = 50
        response2.usage.completion_tokens = 50
        response2.usage.reasoning_tokens = 0
        response2.usage.completion_tokens_details = None
        response2.usage.output_tokens_details = None
        response2_choice = Mock()
        response2_choice.message.content = "Second reply"
        response2_choice.message.tool_calls = None
        response2.choices = [response2_choice]

        mock_llm_client.completion.side_effect = [response1, response2]

        step1 = {"step": {"name": "s1", "instruction": "First step"}}
        step2 = {"step": {"name": "s2", "instruction": "Second step"}}

        agent.execute_basic_step(step1, context, 1, args, mock_logger)
        history = context["conversation_history"]
        assert len(history) == 3
        assert history[0]["role"] == "system"
        assert history[1]["role"] == "user"
        assert history[1]["content"] == "First step"
        assert history[2]["role"] == "assistant"
        assert history[2]["content"] == "First reply"

        agent.execute_basic_step(step2, context, 2, args, mock_logger)
        history = context["conversation_history"]
        assert len(history) == 5
        assert history[3]["role"] == "user"
        assert history[3]["content"] == "Second step"
        assert history[4]["role"] == "assistant"
        assert history[4]["content"] == "Second reply"

        second_call_messages = mock_llm_client.completion.call_args_list[1].kwargs[
            "messages"
        ]
        assert any(
            m.get("role") == "assistant" and m.get("content") == "First reply"
            for m in second_call_messages
        )

    def test_basic_step_submodule_tool_result_persisted(self, agent, mock_llm_client):
        """Test submodule tool result is stored as tool message in conversation history"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {
            "task_output_dir": "/tmp/test",
            "submodule_registry": {"math_add": Mock()},
            "submodule_tools": [{"function": {"name": "math_add"}}],
        }

        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        tool_call = Mock()
        tool_call.id = "call_1"
        tool_call.function = Mock()
        tool_call.function.name = "math_add"
        tool_call.function.arguments = '{"a": 2, "b": 3}'
        choice = Mock()
        choice.message.content = ""
        choice.message.tool_calls = [tool_call]
        response.choices = [choice]
        mock_llm_client.completion.return_value = response

        agent.agent_interpreter.llm_executor._invoke_submodule_tool = Mock(
            return_value={"result": 5, "tokens": 10}
        )

        step_data = {"step": {"name": "s1", "instruction": "Add numbers"}}

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        history = context["conversation_history"]
        tool_call_msgs = [
            m for m in history if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        assert tool_call_msgs
        assert tool_call_msgs[-1]["tool_calls"][0]["function"]["name"] == "math_add"

        tool_result_msgs = [
            m
            for m in history
            if m.get("role") == "tool" and m.get("name") == "math_add"
        ]
        assert tool_result_msgs
        assert tool_result_msgs[-1]["content"] == "5"

    def test_basic_step_mixed_tool_calls_persisted(self, agent, mock_llm_client):
        """Test mixed normal tool and submodule tool calls are persisted correctly"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {
            "task_output_dir": "/tmp/test",
            "submodule_registry": {"math_add": Mock()},
            "submodule_tools": [{"function": {"name": "math_add"}}],
        }

        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        tool_call_sub = Mock()
        tool_call_sub.id = "call_sub"
        tool_call_sub.function = Mock()
        tool_call_sub.function.name = "math_add"
        tool_call_sub.function.arguments = '{"a": 1, "b": 2}'
        tool_call_norm = Mock()
        tool_call_norm.id = "call_norm"
        tool_call_norm.function = Mock()
        tool_call_norm.function.name = "fs_read"
        tool_call_norm.function.arguments = '{"path": "foo.txt"}'
        choice = Mock()
        choice.message.content = ""
        choice.message.tool_calls = [tool_call_sub, tool_call_norm]
        response.choices = [choice]
        mock_llm_client.completion.return_value = response

        agent.agent_interpreter.llm_executor._invoke_submodule_tool = Mock(
            return_value={"result": 3, "tokens": 10}
        )
        agent.mcp_client.invoke = Mock(return_value={"content": "file contents"})

        step_data = {"step": {"name": "s1", "instruction": "Do tools"}}

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        history = context["conversation_history"]
        tool_call_msgs = [
            m for m in history if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        assert tool_call_msgs
        names = [tc["function"]["name"] for tc in tool_call_msgs[-1]["tool_calls"]]
        assert "math_add" in names
        assert "fs_read" in names

        tool_results = [m for m in history if m.get("role") == "tool"]
        assert any(
            m.get("name") == "math_add" and m.get("content") == "3"
            for m in tool_results
        )
        assert any(
            m.get("name") == "fs_read"
            and m.get("content") == '{"content": "file contents"}'
            for m in tool_results
        )

    def test_basic_step_submodule_tool_result_serializes_dict(
        self, agent, mock_llm_client
    ):
        """Test submodule tool result serializes dict payload"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {
            "task_output_dir": "/tmp/test",
            "submodule_registry": {"echo": Mock()},
            "submodule_tools": [{"function": {"name": "echo"}}],
        }

        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        tool_call = Mock()
        tool_call.id = "call_1"
        tool_call.function = Mock()
        tool_call.function.name = "echo"
        tool_call.function.arguments = "{}"
        choice = Mock()
        choice.message.content = ""
        choice.message.tool_calls = [tool_call]
        response.choices = [choice]
        mock_llm_client.completion.return_value = response

        agent.agent_interpreter.llm_executor._invoke_submodule_tool = Mock(
            return_value={"result": {"ok": True, "value": 7}}
        )

        step_data = {"step": {"name": "s1", "instruction": "Echo"}}

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        history = context["conversation_history"]
        tool_results = [
            m for m in history if m.get("role") == "tool" and m.get("name") == "echo"
        ]
        assert tool_results
        assert tool_results[-1]["content"] == '{"ok": true, "value": 7}'

    def test_basic_step_inline_shell_run_tool_call(self, agent, mock_llm_client):
        """Test inline shell_run tool calls in code blocks are executed and appended"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test", "enable_inline_tool_calls": True}

        response1 = Mock()
        response1.usage.total_tokens = 100
        response1.usage.prompt_tokens = 50
        response1.usage.completion_tokens = 50
        response1.usage.reasoning_tokens = 0
        response1.usage.completion_tokens_details = None
        response1.usage.output_tokens_details = None
        choice1 = Mock()
        choice1.message.content = 'THOUGHT: I need to run a command\n\n```shell\nshell_run({"text": "echo hi"})\n```'
        choice1.message.tool_calls = None
        response1.choices = [choice1]

        response2 = Mock()
        response2.usage.total_tokens = 100
        response2.usage.prompt_tokens = 50
        response2.usage.completion_tokens = 50
        response2.usage.reasoning_tokens = 0
        response2.usage.completion_tokens_details = None
        response2.usage.output_tokens_details = None
        choice2 = Mock()
        choice2.message.content = "Done"
        choice2.message.tool_calls = None
        response2.choices = [choice2]

        mock_llm_client.completion.side_effect = [response1, response2]
        agent.mcp_client.invoke = Mock(return_value={"returncode": 0, "output": "hi"})

        step_data = {"step": {"name": "s1", "instruction": "Run inline tool"}}

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        history = context["conversation_history"]
        inline_msgs = [
            m
            for m in history
            if m.get("role") == "user" and "Return code:" in m.get("content", "")
        ]
        assert inline_msgs
        assert "Output:" in inline_msgs[-1]["content"]

    def test_system_prompt_override_task_level(self, agent, mock_llm_client):
        """Test task-level system prompt override with template expansion"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {
            "task_output_dir": "/tmp/test",
            "style": "bullet points",
            "system_prompt": "Respond in {{style}} only.",
        }

        step_data = {"step": {"name": "task_level_prompt", "instruction": "Say hello"}}

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        messages = mock_llm_client.completion.call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Respond in bullet points only."

    def test_system_prompt_override_per_task(self, agent, mock_llm_client):
        """Test per-task system prompt override with template expansion"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {
            "task_output_dir": "/tmp/test",
            "style": "bullet points",
            "answer": "42",
            "system_prompt": "Respond in {{style}} only.",
        }

        step_data = {
            "task": {
                "name": "per_task_prompt",
                "system_prompt": "Return JSON with answer {{answer}}.",
                "instruction": "Return JSON",
            }
        }

        agent.execute_task_step(step_data, context, 1, args, mock_logger)

        messages = mock_llm_client.completion.call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Return JSON with answer 42."

    def test_execute_for_each_step(self, agent, mock_llm_client):
        """Test executing a for_each loop"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        step_data = {
            "for_each": {
                "variable": "item",
                "in": ["a", "b", "c"],
                "limit": 2,
                "steps": [
                    {"task": {"name": "process", "instruction": "Process {{item}}"}}
                ],
            }
        }

        output, tokens = agent.execute_for_each_step(
            step_data, context, 1, args, mock_logger
        )

        # Should execute 2 iterations (limit=2)
        assert tokens == 200  # 100 tokens per iteration * 2
        assert "Iteration 1" in output
        assert "Iteration 2" in output

    def test_execute_conditional_step_then_branch(self, agent, mock_llm_client):
        """Test executing conditional step - then branch"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"status": "ready", "task_output_dir": "/tmp/test"}

        step_data = {
            "if": {
                "condition": "status == 'ready'",
                "then": [{"task": {"name": "proceed", "instruction": "Proceed"}}],
                "else": [{"task": {"name": "wait", "instruction": "Wait"}}],
            }
        }

        output, tokens = agent.execute_conditional_step(
            step_data, context, 1, args, mock_logger
        )

        assert tokens == 100
        assert output == "Test output"

    def test_execute_conditional_step_else_branch(self, agent, mock_llm_client):
        """Test executing conditional step - else branch"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"status": "pending", "task_output_dir": "/tmp/test"}

        step_data = {
            "if": {
                "condition": "status == 'ready'",
                "then": [{"task": {"name": "proceed", "instruction": "Proceed"}}],
                "else": [{"task": {"name": "wait", "instruction": "Wait"}}],
            }
        }

        output, tokens = agent.execute_conditional_step(
            step_data, context, 1, args, mock_logger
        )

        assert tokens == 100
        assert output == "Test output"

    def test_execute_while_step(self, agent, mock_llm_client):
        """Test executing a while loop"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"counter": 0, "task_output_dir": "/tmp/test"}

        step_data = {
            "while": {
                "condition": "counter < 3",
                "max_iterations": 5,
                "steps": [
                    {"task": {"name": "work", "instruction": "Do work"}},
                    {"increment": "counter"},
                ],
            }
        }

        output, tokens = agent.execute_while_step(
            step_data, context, 1, args, mock_logger
        )

        # Should execute 3 iterations (counter: 0, 1, 2)
        assert context["counter"] == 3
        assert tokens > 0

    def test_execute_switch_step_matching_case(self, agent, mock_llm_client):
        """Test executing switch step with matching case"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"format": "json", "task_output_dir": "/tmp/test"}

        step_data = {
            "switch": {
                "variable": "format",
                "cases": {
                    "json": [
                        {
                            "task": {
                                "name": "json_format",
                                "instruction": "Format as JSON",
                            }
                        }
                    ],
                    "yaml": [
                        {
                            "task": {
                                "name": "yaml_format",
                                "instruction": "Format as YAML",
                            }
                        }
                    ],
                },
                "default": [
                    {"task": {"name": "text_format", "instruction": "Format as text"}}
                ],
            }
        }

        output, tokens = agent.execute_switch_step(
            step_data, context, 1, args, mock_logger
        )

        assert tokens == 100
        assert output == "Test output"

    def test_execute_switch_step_default(self, agent, mock_llm_client):
        """Test executing switch step with default case"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"format": "xml", "task_output_dir": "/tmp/test"}

        step_data = {
            "switch": {
                "variable": "format",
                "cases": {
                    "json": [
                        {
                            "task": {
                                "name": "json_format",
                                "instruction": "Format as JSON",
                            }
                        }
                    ]
                },
                "default": [
                    {"task": {"name": "text_format", "instruction": "Format as text"}}
                ],
            }
        }

        output, tokens = agent.execute_switch_step(
            step_data, context, 1, args, mock_logger
        )

        assert tokens == 100

    def test_execute_increment_step(self, agent):
        """Test executing increment step"""
        mock_logger = Mock()
        args = MockArgs()
        context = {"counter": 5}

        step_data = {"increment": "counter"}

        output, tokens = agent.execute_increment_step(
            step_data, context, 1, args, mock_logger
        )

        assert context["counter"] == 6
        assert "counter=6" in output
        assert tokens == 0

    def test_execute_increment_step_new_variable(self, agent):
        """Test executing increment step with new variable"""
        mock_logger = Mock()
        args = MockArgs()
        context = {}

        step_data = {"increment": "new_counter"}

        output, tokens = agent.execute_increment_step(
            step_data, context, 1, args, mock_logger
        )

        assert context["new_counter"] == 1

    def test_execute_basic_step_with_save_as_string(self, agent, mock_llm_client):
        """Test basic step with save_as storing string output"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        # Mock LLM to return a string output
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "This is a test result"
        choice.message.tool_calls = None
        response.choices = [choice]
        agent.llm_client.completion.return_value = response

        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        step_data = {
            "step": {
                "name": "analyze_data",
                "instruction": "Analyze the data",
                "save_as": "analysis_result",
            }
        }

        output, tokens = agent.execute_basic_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify output is saved to context
        assert "analysis_result" in context
        assert context["analysis_result"] == "This is a test result"
        assert output == "This is a test result"
        assert tokens == 100
        # Verify logger was called with save message
        assert any("Saved output" in str(call) for call in mock_logger.call_args_list)

    def test_execute_basic_step_with_save_as_json(self, agent, mock_llm_client):
        """Test basic step with save_as storing eval-able output (number)"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        # Mock LLM to return a number
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "42"
        choice.message.tool_calls = None
        response.choices = [choice]
        agent.llm_client.completion.return_value = response

        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        step_data = {
            "step": {
                "name": "calculate",
                "instruction": "Calculate the answer",
                "save_as": "answer",
            }
        }

        output, tokens = agent.execute_basic_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify output is evaluated and saved as integer
        assert "answer" in context
        assert context["answer"] == 42
        assert isinstance(context["answer"], int)

    def test_execute_basic_step_with_save_as_list(self, agent, mock_llm_client):
        """Test basic step with save_as storing list output"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        # Mock LLM to return a JSON list
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = '["item1", "item2", "item3"]'
        choice.message.tool_calls = None
        response.choices = [choice]
        agent.llm_client.completion.return_value = response

        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        step_data = {
            "step": {
                "name": "get_items",
                "instruction": "Get list of items",
                "save_as": "items",
            }
        }

        output, tokens = agent.execute_basic_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify output is evaluated and saved as list
        assert "items" in context
        assert isinstance(context["items"], list)
        assert len(context["items"]) == 3
        assert context["items"] == ["item1", "item2", "item3"]

    def test_execute_basic_step_with_save_as_template_variable(
        self, agent, mock_llm_client
    ):
        """Test basic step with save_as using template variable for var name"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "result data"
        choice.message.tool_calls = None
        response.choices = [choice]
        agent.llm_client.completion.return_value = response

        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test", "iteration": "5"}

        step_data = {
            "step": {
                "name": "process",
                "instruction": "Process data",
                "save_as": "result_{{iteration}}",
            }
        }

        output, tokens = agent.execute_basic_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify template in save_as is expanded
        assert "result_5" in context
        assert context["result_5"] == "result data"

    def test_execute_set_variable_step_literal_value(self, agent):
        """Test set_variable step with literal value"""
        mock_logger = Mock()
        args = MockArgs()
        context = {}

        step_data = {"set_variable": {"name": "max_iterations", "value": "10"}}

        output, tokens = agent.execute_set_variable_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify variable is set with evaluated value
        assert "max_iterations" in context
        assert context["max_iterations"] == 10
        assert tokens == 0
        assert "Set max_iterations" in output

    def test_execute_set_variable_step_string_value(self, agent):
        """Test set_variable step with string value"""
        mock_logger = Mock()
        args = MockArgs()
        context = {}

        step_data = {"set_variable": {"name": "status", "value": "processing"}}

        output, tokens = agent.execute_set_variable_step(
            step_data, context, 1, args, mock_logger
        )

        assert "status" in context
        assert context["status"] == "processing"

    def test_execute_set_variable_step_template_expansion(self, agent):
        """Test set_variable step with template variable expansion"""
        mock_logger = Mock()
        args = MockArgs()
        context = {"current_value": "5", "multiplier": "2"}

        step_data = {
            "set_variable": {
                "name": "new_value",
                "value": "{{current_value}} * {{multiplier}}",
            }
        }

        output, tokens = agent.execute_set_variable_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify template expansion and evaluation
        assert "new_value" in context
        assert context["new_value"] == 10  # 5 * 2 should be evaluated

    def test_execute_set_variable_step_python_expression(self, agent):
        """Test set_variable step with Python expression"""
        mock_logger = Mock()
        args = MockArgs()
        context = {"breadth": "8"}

        step_data = {
            "set_variable": {"name": "half_breadth", "value": "{{breadth}} // 2"}
        }

        output, tokens = agent.execute_set_variable_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify Python expression is evaluated
        assert "half_breadth" in context
        assert context["half_breadth"] == 4  # 8 // 2

    def test_execute_set_variable_step_from_prev_output(self, agent):
        """Test set_variable step using prev_output as default"""
        mock_logger = Mock()
        args = MockArgs()
        context = {"prev_output": "previous step result"}

        step_data = {"set_variable": {"name": "saved_result"}}

        output, tokens = agent.execute_set_variable_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify prev_output is used when value is not specified
        assert "saved_result" in context
        assert context["saved_result"] == "previous step result"

    def test_execute_set_variable_step_complex_expression(self, agent):
        """Test set_variable step with complex Python expression"""
        mock_logger = Mock()
        args = MockArgs()
        context = {"items": "[1, 2, 3, 4, 5]"}

        step_data = {"set_variable": {"name": "item_count", "value": "len({{items}})"}}

        output, tokens = agent.execute_set_variable_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify complex expression is evaluated
        assert "item_count" in context
        assert context["item_count"] == 5

    def test_execute_set_variable_step_non_eval_fallback(self, agent):
        """Test set_variable step falls back to string when eval fails"""
        mock_logger = Mock()
        args = MockArgs()
        context = {}

        step_data = {
            "set_variable": {
                "name": "message",
                "value": "This is not eval-able: {invalid}",
            }
        }

        output, tokens = agent.execute_set_variable_step(
            step_data, context, 1, args, mock_logger
        )

        # Verify fallback to string when eval fails
        assert "message" in context
        assert context["message"] == "This is not eval-able: {invalid}"

    def test_workflow_integration_save_as_and_set_variable(
        self, agent, mock_llm_client
    ):
        """Test integration of save_as and set_variable in a workflow"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        # Mock LLM to return different outputs
        responses = [
            Mock(
                usage=Mock(
                    total_tokens=100,
                    prompt_tokens=50,
                    completion_tokens=50,
                    reasoning_tokens=0,
                    completion_tokens_details=None,
                    output_tokens_details=None,
                ),
                choices=[Mock(message=Mock(content="10", tool_calls=None))],
            ),
            Mock(
                usage=Mock(
                    total_tokens=100,
                    prompt_tokens=50,
                    completion_tokens=50,
                    reasoning_tokens=0,
                    completion_tokens_details=None,
                    output_tokens_details=None,
                ),
                choices=[
                    Mock(
                        message=Mock(
                            content="Final result with value 5", tool_calls=None
                        )
                    )
                ],
            ),
        ]
        mock_llm_client.completion.side_effect = responses

        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        # Step 1: Basic step with save_as
        step1 = {
            "step": {
                "name": "get_count",
                "instruction": "Get item count",
                "save_as": "item_count",
            }
        }

        output1, tokens1 = agent.execute_basic_step(
            step1, context, 1, args, mock_logger
        )

        # Step 2: Set variable using saved value
        step2 = {"set_variable": {"name": "half_count", "value": "{{item_count}} // 2"}}

        output2, tokens2 = agent.execute_set_variable_step(
            step2, context, 2, args, mock_logger
        )

        # Step 3: Use the computed variable in next step
        step3 = {
            "step": {
                "name": "process_with_value",
                "instruction": "Process with half_count={{half_count}}",
            }
        }

        output3, tokens3 = agent.execute_basic_step(
            step3, context, 3, args, mock_logger
        )

        # Verify the workflow
        assert context["item_count"] == 10
        assert context["half_count"] == 5
        assert "Final result with value 5" in output3

    def test_execute_parallel_step(self, agent, mock_llm_client):
        """Test executing parallel steps (executed sequentially)"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        step_data = {
            "parallel": [
                {"task": {"name": "task1", "instruction": "Do task 1"}},
                {"task": {"name": "task2", "instruction": "Do task 2"}},
                {"task": {"name": "task3", "instruction": "Do task 3"}},
            ]
        }

        output, tokens = agent.execute_parallel_step(
            step_data, context, 1, args, mock_logger
        )

        # Should execute 3 steps
        assert tokens == 300  # 100 per step * 3
        assert output.count("Test output") == 3

    def test_nested_workflow(self, agent, mock_llm_client):
        """Test executing nested workflow (for_each with if inside)"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {"task_output_dir": "/tmp/test"}

        step_data = {
            "for_each": {
                "variable": "num",
                "in": [1, 2, 3],
                "steps": [
                    {
                        "if": {
                            "condition": "num > 1",
                            "then": [
                                {
                                    "task": {
                                        "name": "process",
                                        "instruction": "Process {{num}}",
                                    }
                                }
                            ],
                            "else": [],
                        }
                    }
                ],
            }
        }

        output, tokens = agent.execute_for_each_step(
            step_data, context, 1, args, mock_logger
        )

        # Should execute 2 times (num=2 and num=3 satisfy condition)
        assert tokens == 200

    def test_load_submodule_tools_from_yaml(self, agent, tmp_path):
        """Test loading submodule tool declarations from YAML"""
        submodule_yaml = {
            "name": "math_add_task",
            "goal": "Add two numbers",
            "function": {
                "name": "math_add",
                "description": "Add two numbers and return sum",
                "parameters": {"model": ["a", "b"]},
                "return": "sum",
            },
            "workflow": [
                {
                    "task": {
                        "name": "add",
                        "instruction": "Add {{a}} and {{b}}",
                        "save_as": "sum",
                    }
                },
                {"return": "sum"},
            ],
        }

        submodule_path = tmp_path / "math_add.yaml"
        with open(submodule_path, "w", encoding="utf-8") as f:
            yaml.dump(submodule_yaml, f, default_flow_style=False)

        main_yaml = {
            "name": "main",
            "goal": "Test submodule tool load",
            "workflow": [],
            "submodules": [{"name": "math_add", "path": "math_add.yaml"}],
        }

        main_path = tmp_path / "main.yaml"
        with open(main_path, "w", encoding="utf-8") as f:
            yaml.dump(main_yaml, f, default_flow_style=False)

        tools, registry = load_submodule_tools_for_yaml(main_yaml, str(main_path))

        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "math_add"
        assert "math_add" in registry
        assert registry["math_add"].return_var == "sum"


class MockFunction:
    """Simple mock for tool function objects"""

    def __init__(self, name, description=""):
        self.name = name
        self.description = description


class TestToolFiltering:
    """Test cases for tool filtering functionality"""

    @pytest.fixture
    def mock_mcp_client(self):
        """Create a mock MCP client with multiple tools"""
        client = Mock()
        client.list_tools.return_value = [
            {"function": MockFunction("fs_read", "Read file")},
            {"function": MockFunction("fs_write", "Write file")},
            {"function": MockFunction("web_search", "Search web")},
            {"function": MockFunction("browser_navigate", "Navigate browser")},
        ]
        client.make_mcp_tool_function.return_value = Mock()
        client.process_tool_calls.return_value = ([], [])
        return client

    @pytest.fixture
    def agent(self, mock_mcp_client):
        """Create a AgentSPEX instance with mocked dependencies"""
        with patch("harness.agent.LLMClient"):
            with patch("harness.agent.MCPClient", return_value=mock_mcp_client):
                agent = AgentSPEX(mcp_url="http://localhost:7002/mcp")
                return agent

    def test_get_effective_tools_no_filtering(self, agent):
        """Test that all tools are returned when no filtering is specified"""
        context = {}
        result = EffectiveToolConfig.compute(agent.tools, context).tools
        assert len(result) == 4

    def test_get_effective_tools_plan_level_only(self, agent):
        """Test filtering with only plan-level enabled_tools"""
        context = {"enabled_tools": ["fs_read", "fs_write"]}
        result = EffectiveToolConfig.compute(agent.tools, context).tools

        assert len(result) == 2
        tool_names = [t["function"].name for t in result]
        assert "fs_read" in tool_names
        assert "fs_write" in tool_names
        assert "web_search" not in tool_names

    def test_get_effective_tools_step_level_only(self, agent):
        """Test filtering with only step-level enabled_tools"""
        context = {}
        step_config = {"enabled_tools": ["web_search"]}
        result = EffectiveToolConfig.compute(agent.tools, context, step_config).tools

        assert len(result) == 1
        assert result[0]["function"].name == "web_search"

    def test_get_effective_tools_intersection(self, agent):
        """Test that plan and step level use intersection"""
        context = {"enabled_tools": ["fs_read", "fs_write", "web_search"]}
        step_config = {"enabled_tools": ["fs_read", "browser_navigate"]}
        result = EffectiveToolConfig.compute(agent.tools, context, step_config).tools

        # Only fs_read is in both lists
        assert len(result) == 1
        assert result[0]["function"].name == "fs_read"

    def test_get_effective_tools_empty_intersection(self, agent):
        """Test that empty intersection returns no tools"""
        context = {"enabled_tools": ["fs_read"]}
        step_config = {"enabled_tools": ["web_search"]}
        result = EffectiveToolConfig.compute(agent.tools, context, step_config).tools

        assert len(result) == 0

    def test_get_effective_tools_nonexistent_tools(self, agent):
        """Test filtering with tool names that don't exist"""
        context = {"enabled_tools": ["nonexistent_tool", "fs_read"]}
        result = EffectiveToolConfig.compute(agent.tools, context).tools

        assert len(result) == 1
        assert result[0]["function"].name == "fs_read"

    def test_get_effective_tools_accepts_single_string(self, agent):
        """Test filtering when enabled_tools is provided as a single string"""
        context = {"enabled_tools": "fs_read"}
        result = EffectiveToolConfig.compute(agent.tools, context).tools

        assert len(result) == 1
        assert result[0]["function"].name == "fs_read"

    def test_get_effective_tools_with_dict_function(self):
        """Test filtering when tool function is a dict"""
        mock_client = Mock()
        mock_client.list_tools.return_value = [
            {"function": {"name": "fs_read"}},
            {"function": {"name": "fs_write"}},
        ]
        mock_client.make_mcp_tool_function.return_value = Mock()
        mock_client.process_tool_calls.return_value = ([], [])
        with patch("harness.agent.LLMClient"):
            with patch("harness.agent.MCPClient", return_value=mock_client):
                agent = AgentSPEX(mcp_url="http://localhost:7002/mcp")

        context = {"enabled_tools": ["fs_read"]}
        result = EffectiveToolConfig.compute(agent.tools, context).tools

        assert len(result) == 1
        assert result[0]["function"]["name"] == "fs_read"

    def test_get_effective_submodule_tools_filters(self, agent):
        """Test submodule tool filtering with plan and step enabled_submodules"""
        context = {
            "submodule_tools": [
                {"function": {"name": "math_add"}},
                {"function": {"name": "math_mul"}},
                {"function": {"name": "text_echo"}},
            ],
            "enabled_submodules": ["math_add", "math_mul"],
        }
        step_config = {"enabled_submodules": ["math_mul", "text_echo"]}

        result = EffectiveToolConfig.compute(
            agent.tools, context, step_config
        ).submodule_tools

        assert len(result) == 1
        assert result[0]["function"]["name"] == "math_mul"

    def test_execute_llm_step_passes_filtered_tools(self, agent):
        """Test that execute_llm_step passes filtered tools to API"""
        mock_openai = Mock()
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "Test output"
        choice.message.tool_calls = None
        response.choices = [choice]
        mock_openai.completion.return_value = response
        agent.llm_client = mock_openai
        agent.agent_interpreter.llm_executor.llm_client = mock_openai

        context = {"enabled_tools": ["fs_read"]}
        step_config = {"name": "test", "instruction": "Test"}
        mock_logger = Mock()
        args = MockArgs()

        agent.agent_interpreter.llm_executor.execute_llm_step(
            "Test instruction",
            "",
            1,
            args,
            mock_logger,
            context=context,
            step_config=step_config,
        )

        call_kwargs = mock_openai.completion.call_args.kwargs
        tools = call_kwargs.get("tools")
        assert tools is not None
        assert len(tools) == 1
        assert tools[0]["function"].name == "fs_read"

    def test_execute_llm_step_no_tools_when_empty_filter(self, agent):
        """Test that no tools are passed when filter results in empty list"""
        mock_openai = Mock()
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "Test output"
        choice.message.tool_calls = None
        response.choices = [choice]
        mock_openai.completion.return_value = response
        agent.llm_client = mock_openai
        agent.agent_interpreter.llm_executor.llm_client = mock_openai

        context = {"enabled_tools": ["nonexistent"]}
        mock_logger = Mock()
        args = MockArgs()

        agent.agent_interpreter.llm_executor.execute_llm_step(
            "Test instruction",
            "",
            1,
            args,
            mock_logger,
            context=context,
        )

        call_kwargs = mock_openai.completion.call_args.kwargs
        assert call_kwargs.get("tools") is None
        assert call_kwargs.get("tool_choice") is None

    def test_basic_step_with_enabled_tools(self, agent):
        """Test basic step respects enabled_tools in step config"""
        mock_openai = Mock()
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "Test output"
        choice.message.tool_calls = None
        response.choices = [choice]
        mock_openai.completion.return_value = response
        agent.llm_client = mock_openai
        agent.agent_interpreter.llm_executor.llm_client = mock_openai

        context = {"task_output_dir": "/tmp/test"}
        step_data = {
            "step": {
                "name": "restricted_step",
                "instruction": "Do something",
                "enabled_tools": ["fs_read"],
            }
        }
        mock_logger = Mock()
        args = MockArgs()

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        call_kwargs = mock_openai.completion.call_args.kwargs
        tools = call_kwargs.get("tools")
        assert len(tools) == 1
        assert tools[0]["function"].name == "fs_read"

    def test_plan_and_step_level_combined(self, agent):
        """Test plan-level and step-level filtering work together"""
        mock_openai = Mock()
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "Test"
        choice.message.tool_calls = None
        response.choices = [choice]
        mock_openai.completion.return_value = response
        agent.llm_client = mock_openai
        agent.agent_interpreter.llm_executor.llm_client = mock_openai

        # Plan allows fs_read, fs_write, web_search
        context = {
            "task_output_dir": "/tmp/test",
            "enabled_tools": ["fs_read", "fs_write", "web_search"],
        }
        # Step only wants fs_read and browser_navigate
        # Intersection should be just fs_read
        step_data = {
            "step": {
                "name": "test",
                "instruction": "Test",
                "enabled_tools": ["fs_read", "browser_navigate"],
            }
        }
        mock_logger = Mock()
        args = MockArgs()

        agent.execute_basic_step(step_data, context, 1, args, mock_logger)

        call_kwargs = mock_openai.completion.call_args.kwargs
        tools = call_kwargs.get("tools")
        assert len(tools) == 1
        assert tools[0]["function"].name == "fs_read"


class TestAgentSPEXIntegration:
    """Integration tests for complete workflow execution"""

    @pytest.fixture
    def sample_yaml_file(self, tmp_path):
        """Create a sample YAML workflow file"""
        yaml_content = """
name: "test_workflow"
goal: "Test workflow execution"

parameters:
  topic: "testing"
  max_count: 3

workflow:
  - task:
      name: "init"
      instruction: "Initialize workflow for {{topic}}"

  - for_each:
      variable: "i"
      in: [1, 2, 3]
      limit: 2
      steps:
        - task:
            name: "iteration_{{i}}"
            instruction: "Process iteration {{i}}"

  - synthesize:
      name: "summary"
      instruction: "Summarize results"
      output_file: "summary.txt"
"""
        file_path = tmp_path / "test_workflow.yaml"
        with open(file_path, "w") as f:
            f.write(yaml_content)
        return str(file_path)

    @patch("harness.agent.LLMClient")
    @patch("harness.agent.MCPClient")
    def test_complete_workflow_execution(
        self, mock_mcp_class, mock_llm_class, sample_yaml_file, tmp_path
    ):
        """Test executing a complete workflow from YAML file"""
        # Setup mocks
        mock_mcp_client = Mock()
        mock_mcp_client.list_tools.return_value = []
        mock_mcp_client.make_mcp_tool_function.return_value = Mock()
        mock_mcp_client.process_tool_calls.return_value = ([], [])
        mock_mcp_class.return_value = mock_mcp_client

        mock_llm_client = Mock()
        response = Mock()
        response.usage.total_tokens = 100
        response.usage.prompt_tokens = 50
        response.usage.completion_tokens = 50
        response.usage.reasoning_tokens = 0
        response.usage.completion_tokens_details = None
        response.usage.output_tokens_details = None
        choice = Mock()
        choice.message.content = "Test output"
        choice.message.tool_calls = None
        response.choices = [choice]
        mock_llm_client.completion.return_value = response
        mock_llm_class.return_value = mock_llm_client

        # Create agent and run with temp output directory
        agent = AgentSPEX(mcp_url="http://localhost:7002/mcp")
        output_dir = tmp_path / "test_output"
        args = MockArgs(output_dir=str(output_dir))
        args.workflow_file = sample_yaml_file

        result = agent.run(args)

        # Verify execution
        assert result is not None
        # Verify multiple steps were executed
        assert mock_llm_client.completion.call_count >= 3


class TestInlineToolCallsConfig:
    """Tests for enable_inline_tool_calls configuration"""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client"""
        return Mock()

    @pytest.fixture
    def agent(self):
        mock_client = Mock()
        mock_client.list_tools.return_value = [
            {"function": Mock(name="fs_read", description="Read file")},
            {"function": Mock(name="shell_run", description="Run shell command")},
        ]
        mock_client.make_mcp_tool_function.return_value = Mock()
        mock_client.process_tool_calls.return_value = ([], [])
        with patch("harness.agent.LLMClient"):
            with patch("harness.agent.MCPClient", return_value=mock_client):
                agent = AgentSPEX(mcp_url="http://localhost:7002/mcp")
        return agent

    def test_inline_tool_calls_disabled_by_default(self, agent, mock_llm_client):
        """Test that inline tool calls are NOT executed when enable_inline_tool_calls is not set"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        # Note: enable_inline_tool_calls is NOT set (default behavior)
        context = {"task_output_dir": "/tmp/test"}

        response1 = Mock()
        response1.usage.total_tokens = 100
        response1.usage.prompt_tokens = 50
        response1.usage.completion_tokens = 50
        response1.usage.reasoning_tokens = 0
        response1.usage.completion_tokens_details = None
        response1.usage.output_tokens_details = None
        choice1 = Mock()
        # Model outputs a code block that looks like a tool call
        choice1.message.content = '```shell\nshell_run({"text": "echo hi"})\n```'
        choice1.message.tool_calls = None
        response1.choices = [choice1]

        response2 = Mock()
        response2.usage.total_tokens = 100
        response2.usage.prompt_tokens = 50
        response2.usage.completion_tokens = 50
        response2.usage.reasoning_tokens = 0
        response2.usage.completion_tokens_details = None
        response2.usage.output_tokens_details = None
        choice2 = Mock()
        choice2.message.content = "Done"
        choice2.message.tool_calls = None
        response2.choices = [choice2]

        mock_llm_client.completion.side_effect = [response1, response2]
        agent.mcp_client.invoke = Mock(return_value={"returncode": 0, "output": "hi"})

        step_data = {"task": {"name": "t1", "instruction": "Run inline tool"}}

        agent.execute_task_step(step_data, context, 1, args, mock_logger)

        # Verify that mcp_client.invoke was NOT called (inline tools disabled)
        agent.mcp_client.invoke.assert_not_called()

    def test_inline_tool_calls_only_implies_enabled(self, agent, mock_llm_client):
        """Test that inline_tool_calls_only=True implies inline tool calls are enabled"""
        agent.llm_client = mock_llm_client
        agent.agent_interpreter.llm_executor.llm_client = mock_llm_client
        mock_logger = Mock()
        args = MockArgs()
        context = {
            "task_output_dir": "/tmp/test",
            "inline_tool_calls_only": True,  # Should imply enable_inline_tool_calls
        }

        response1 = Mock()
        response1.usage.total_tokens = 100
        response1.usage.prompt_tokens = 50
        response1.usage.completion_tokens = 50
        response1.usage.reasoning_tokens = 0
        response1.usage.completion_tokens_details = None
        response1.usage.output_tokens_details = None
        choice1 = Mock()
        choice1.message.content = 'THOUGHT: I need to run a command\n\n```shell\nshell_run({"text": "echo hi"})\n```'
        choice1.message.tool_calls = None
        response1.choices = [choice1]

        response2 = Mock()
        response2.usage.total_tokens = 100
        response2.usage.prompt_tokens = 50
        response2.usage.completion_tokens = 50
        response2.usage.reasoning_tokens = 0
        response2.usage.completion_tokens_details = None
        response2.usage.output_tokens_details = None
        choice2 = Mock()
        choice2.message.content = "Done"
        choice2.message.tool_calls = None
        response2.choices = [choice2]

        mock_llm_client.completion.side_effect = [response1, response2]
        agent.mcp_client.invoke = Mock(return_value={"returncode": 0, "output": "hi"})

        step_data = {"task": {"name": "t1", "instruction": "Run inline tool"}}

        agent.execute_task_step(step_data, context, 1, args, mock_logger)

        # Verify that mcp_client.invoke WAS called (inline tools enabled via inline_tool_calls_only)
        agent.mcp_client.invoke.assert_called()
