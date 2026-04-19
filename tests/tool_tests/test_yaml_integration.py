"""
Integration tests for YAML workflows

Tests complete end-to-end workflows including:
- Real YAML file execution
- MCP server integration
- Complex nested workflows
- Error handling and recovery
"""

import os

import pytest
import yaml

MCP_URL = os.getenv("MCP_URL", "http://localhost:7002/mcp")


@pytest.fixture
def test_yaml_dir(tmp_path):
    """Create a directory for test YAML files"""
    yaml_dir = tmp_path / "yaml_tasks"
    yaml_dir.mkdir()
    return yaml_dir


@pytest.fixture
def basic_workflow_yaml(test_yaml_dir):
    """Create a basic workflow YAML file"""
    yaml_content = {
        "name": "basic_test",
        "goal": "Test basic workflow execution",
        "workflow": [
            {
                "task": {
                    "name": "task1",
                    "instruction": "Create a test file with content 'Hello World'",
                }
            },
            {
                "task": {
                    "name": "task2",
                    "instruction": "Read the test file and verify its content",
                }
            },
        ],
    }

    file_path = test_yaml_dir / "basic_workflow.yaml"
    with open(file_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    return str(file_path)


@pytest.fixture
def task_workflow_yaml(test_yaml_dir):
    """Create a workflow with step entries that carry conversation history"""
    yaml_content = {
        "name": "step_history_test",
        "goal": "Test step conversation history",
        "workflow": [
            {"step": {"name": "step1", "instruction": "Remember the codeword ALPHA"}},
            {
                "step": {
                    "name": "step2",
                    "instruction": "What codeword did I ask you to remember?",
                }
            },
        ],
    }

    file_path = test_yaml_dir / "task_workflow.yaml"
    with open(file_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    return str(file_path)


@pytest.fixture
def loop_workflow_yaml(test_yaml_dir):
    """Create a workflow with loops"""
    yaml_content = {
        "name": "loop_test",
        "goal": "Test loop execution",
        "parameters": {"items": ["apple", "banana", "cherry"]},
        "workflow": [
            {
                "for_each": {
                    "variable": "fruit",
                    "in": ["apple", "banana", "cherry"],
                    "steps": [
                        {
                            "task": {
                                "name": "process_{{fruit}}",
                                "instruction": "Process fruit: {{fruit}}",
                            }
                        }
                    ],
                }
            }
        ],
    }

    file_path = test_yaml_dir / "loop_workflow.yaml"
    with open(file_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    return str(file_path)


@pytest.fixture
def conditional_workflow_yaml(test_yaml_dir):
    """Create a workflow with conditionals"""
    yaml_content = {
        "name": "conditional_test",
        "goal": "Test conditional execution",
        "parameters": {"mode": "production"},
        "workflow": [
            {
                "if": {
                    "condition": "mode == 'production'",
                    "then": [
                        {
                            "task": {
                                "name": "production_setup",
                                "instruction": "Set up production environment",
                            }
                        }
                    ],
                    "else": [
                        {
                            "task": {
                                "name": "dev_setup",
                                "instruction": "Set up development environment",
                            }
                        }
                    ],
                }
            }
        ],
    }

    file_path = test_yaml_dir / "conditional_workflow.yaml"
    with open(file_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    return str(file_path)


@pytest.fixture
def nested_workflow_yaml(test_yaml_dir):
    """Create a complex nested workflow"""
    yaml_content = {
        "name": "nested_test",
        "goal": "Test nested control structures",
        "parameters": {"categories": ["tech", "science", "arts"], "counter": 0},
        "workflow": [
            {
                "for_each": {
                    "variable": "category",
                    "in": ["tech", "science"],
                    "limit": 2,
                    "steps": [
                        {
                            "task": {
                                "name": "init_{{category}}",
                                "instruction": "Initialize category {{category}}",
                            }
                        },
                        {
                            "if": {
                                "condition": "category == 'tech'",
                                "then": [
                                    {
                                        "task": {
                                            "name": "tech_specific",
                                            "instruction": "Process tech-specific tasks",
                                        }
                                    }
                                ],
                                "else": [
                                    {
                                        "task": {
                                            "name": "general_processing",
                                            "instruction": "Process general tasks",
                                        }
                                    }
                                ],
                            }
                        },
                        {"increment": "counter"},
                    ],
                }
            },
            {
                "task": {
                    "name": "summary",
                    "instruction": "Summarize all category processing. Counter value: {{counter}}",
                }
            },
        ],
    }

    file_path = test_yaml_dir / "nested_workflow.yaml"
    with open(file_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    return str(file_path)


@pytest.fixture
def while_loop_yaml(test_yaml_dir):
    """Create a workflow with while loop"""
    yaml_content = {
        "name": "while_test",
        "goal": "Test while loop execution",
        "parameters": {"iterations": 0, "max_iterations": 3},
        "workflow": [
            {
                "while": {
                    "condition": "iterations < 3",
                    "max_iterations": 5,
                    "steps": [
                        {
                            "task": {
                                "name": "iteration_{{iterations}}",
                                "instruction": "Execute iteration {{iterations}}",
                            }
                        },
                        {"increment": "iterations"},
                    ],
                }
            }
        ],
    }

    file_path = test_yaml_dir / "while_workflow.yaml"
    with open(file_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    return str(file_path)


@pytest.fixture
def switch_workflow_yaml(test_yaml_dir):
    """Create a workflow with switch statement"""
    yaml_content = {
        "name": "switch_test",
        "goal": "Test switch/case execution",
        "parameters": {"output_format": "markdown"},
        "workflow": [
            {"task": {"name": "generate_data", "instruction": "Generate sample data"}},
            {
                "switch": {
                    "variable": "output_format",
                    "cases": {
                        "markdown": [
                            {
                                "task": {
                                    "name": "format_markdown",
                                    "instruction": "Format output as Markdown",
                                }
                            }
                        ],
                        "json": [
                            {
                                "task": {
                                    "name": "format_json",
                                    "instruction": "Format output as JSON",
                                }
                            }
                        ],
                        "yaml": [
                            {
                                "task": {
                                    "name": "format_yaml",
                                    "instruction": "Format output as YAML",
                                }
                            }
                        ],
                    },
                    "default": [
                        {
                            "task": {
                                "name": "format_text",
                                "instruction": "Format output as plain text",
                            }
                        }
                    ],
                }
            },
        ],
    }

    file_path = test_yaml_dir / "switch_workflow.yaml"
    with open(file_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    return str(file_path)


@pytest.fixture
def env_variable_yaml(test_yaml_dir):
    """Create a workflow that uses environment variables"""
    yaml_content = """
name: "env_var_test_${TEST_ENV_VAR:-default}"
goal: "Test environment variable expansion"

parameters:
  env_value: "${TEST_ENV_VAR:-fallback_value}"
  project_name: "${PROJECT_NAME:-my_project}"

workflow:
  - task:
      name: "use_env_vars"
      instruction: "Process with env value: {{env_value}} for project {{project_name}}"
"""

    file_path = test_yaml_dir / "env_variable_workflow.yaml"
    with open(file_path, "w") as f:
        f.write(yaml_content)

    return str(file_path)


class TestYAMLWorkflowIntegration:
    """Integration tests for complete YAML workflows"""

    def test_yaml_parser_loads_all_fixtures(
        self,
        basic_workflow_yaml,
        task_workflow_yaml,
        loop_workflow_yaml,
        conditional_workflow_yaml,
        nested_workflow_yaml,
    ):
        """Test that all fixture YAML files can be loaded"""
        from harness.parsing import YAMLTaskParser

        parser = YAMLTaskParser()

        # Load each YAML file
        for yaml_file in [
            basic_workflow_yaml,
            task_workflow_yaml,
            loop_workflow_yaml,
            conditional_workflow_yaml,
            nested_workflow_yaml,
        ]:
            data = parser.load_task(yaml_file)
            assert data is not None
            assert "name" in data
            assert "goal" in data
            assert "workflow" in data

    def test_workflow_with_parameters(self, loop_workflow_yaml):
        """Test workflow with parameters"""
        from harness.parsing import YAMLTaskParser

        parser = YAMLTaskParser()
        data = parser.load_task(loop_workflow_yaml)

        assert "parameters" in data
        assert "items" in data["parameters"]
        assert data["parameters"]["items"] == ["apple", "banana", "cherry"]

    def test_env_variable_expansion(self, env_variable_yaml):
        """Test environment variable expansion in YAML"""
        from harness.parsing import YAMLTaskParser

        # Set environment variables
        os.environ["TEST_ENV_VAR"] = "test_value"
        os.environ["PROJECT_NAME"] = "awesome_project"

        parser = YAMLTaskParser()
        data = parser.load_task(env_variable_yaml)

        assert "test_value" in data["name"]
        assert data["parameters"]["env_value"] == "test_value"
        assert data["parameters"]["project_name"] == "awesome_project"

        # Clean up
        del os.environ["TEST_ENV_VAR"]
        del os.environ["PROJECT_NAME"]

    def test_nested_workflow_structure(self, nested_workflow_yaml):
        """Test nested workflow structure is correctly parsed"""
        from harness.parsing import YAMLTaskParser

        parser = YAMLTaskParser()
        data = parser.load_task(nested_workflow_yaml)

        # Check top-level workflow
        assert len(data["workflow"]) == 2

        # Check nested for_each -> if structure
        for_each_step = data["workflow"][0]
        assert "for_each" in for_each_step
        assert len(for_each_step["for_each"]["steps"]) == 3

        # Check if statement inside for_each
        if_step = for_each_step["for_each"]["steps"][1]
        assert "if" in if_step

    def test_all_workflow_types_present(
        self,
        basic_workflow_yaml,
        loop_workflow_yaml,
        conditional_workflow_yaml,
        while_loop_yaml,
        switch_workflow_yaml,
    ):
        """Test that all workflow types can be loaded"""
        from harness.parsing import YAMLTaskParser

        parser = YAMLTaskParser()

        workflows = {
            "basic": basic_workflow_yaml,
            "loop": loop_workflow_yaml,
            "conditional": conditional_workflow_yaml,
            "while": while_loop_yaml,
            "switch": switch_workflow_yaml,
        }

        for name, yaml_file in workflows.items():
            data = parser.load_task(yaml_file)
            assert data is not None, f"Failed to load {name} workflow"
            assert len(data["workflow"]) > 0, f"{name} workflow is empty"


class TestYAMLWorkflowExecution:
    """Tests for executing YAML workflows (requires running MCP server)"""

    @pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Integration tests require running MCP server",
    )
    def test_execute_basic_workflow(self, basic_workflow_yaml):
        """Test executing a basic workflow end-to-end"""
        from harness.agent import AgentSPEX

        class MockArgs:
            model = "gpt-4"
            temperature = 0.7
            max_tool_calls_per_step = 5
            max_tokens_per_step = 4000
            workflow_file = basic_workflow_yaml

        agent = AgentSPEX(mcp_url=MCP_URL)
        result = agent.run(MockArgs())

        assert result is not None
        assert len(result) > 0

    @pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Integration tests require running MCP server",
    )
    def test_execute_loop_workflow(self, loop_workflow_yaml):
        """Test executing a workflow with loops"""
        from harness.agent import AgentSPEX

        class MockArgs:
            model = "gpt-4"
            temperature = 0.7
            max_tool_calls_per_step = 5
            max_tokens_per_step = 4000
            workflow_file = loop_workflow_yaml

        agent = AgentSPEX(mcp_url=MCP_URL)
        result = agent.run(MockArgs())

        assert result is not None


class TestYAMLWorkflowValidation:
    """Tests for YAML workflow validation"""

    def test_invalid_yaml_syntax(self, test_yaml_dir):
        """Test that invalid YAML syntax is caught"""
        from harness.parsing import YAMLTaskParser

        invalid_yaml = test_yaml_dir / "invalid.yaml"
        with open(invalid_yaml, "w") as f:
            f.write("name: test\ninvalid: [unclosed")

        parser = YAMLTaskParser()
        is_valid, message = parser.validate_yaml_syntax(str(invalid_yaml))

        assert not is_valid
        assert "YAML syntax error" in message

    def test_missing_required_fields(self, test_yaml_dir):
        """Test that missing required fields are caught"""
        from harness.parsing import YAMLTaskParser

        incomplete_yaml = test_yaml_dir / "incomplete.yaml"
        yaml_content = {
            "name": "test",
            "goal": "test",
            # Missing 'workflow' field
        }
        with open(incomplete_yaml, "w") as f:
            yaml.dump(yaml_content, f)

        parser = YAMLTaskParser()

        with pytest.raises(ValueError, match="Missing required field: workflow"):
            parser.load_task(str(incomplete_yaml))
