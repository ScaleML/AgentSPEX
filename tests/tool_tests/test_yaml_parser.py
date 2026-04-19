"""
Unit tests for YAMLTaskParser

Tests the YAML task parser functionality including:
- Loading and parsing YAML files
- Environment variable expansion
- Template variable expansion
- Workflow step parsing
- Validation
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from harness.parsing import YAMLTaskParser, convert_json_to_yaml


class TestYAMLTaskParser:
    """Test cases for YAMLTaskParser class"""

    @pytest.fixture
    def parser(self):
        """Create a fresh parser instance for each test"""
        return YAMLTaskParser()

    @pytest.fixture
    def temp_yaml_file(self, tmp_path):
        """Create a temporary YAML file for testing"""

        def _create_yaml(content: Dict[str, Any]) -> str:
            file_path = tmp_path / "test_task.yaml"
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(content, f, default_flow_style=False, allow_unicode=True)
            return str(file_path)

        return _create_yaml

    def test_load_valid_yaml(self, parser, temp_yaml_file):
        """Test loading a valid YAML task file"""
        yaml_content = {
            "name": "test_task",
            "goal": "Test loading YAML",
            "workflow": [{"task": {"name": "task1", "instruction": "Do something"}}],
        }
        file_path = temp_yaml_file(yaml_content)

        result = parser.load_task(file_path)

        assert result["name"] == "test_task"
        assert result["goal"] == "Test loading YAML"
        assert len(result["workflow"]) == 1

    def test_load_with_submodules_and_step(self, parser, temp_yaml_file):
        """Test loading YAML with submodules and step with conversation history"""
        yaml_content = {
            "name": "test_task",
            "goal": "Test submodules and steps",
            "submodules": [{"name": "math_add", "path": "submodules/math_add.yaml"}],
            "workflow": [
                {"step": {"name": "step1", "instruction": "Remember a value"}},
                {"task": {"name": "task1", "instruction": "Use the value"}},
            ],
        }
        file_path = temp_yaml_file(yaml_content)

        result = parser.load_task(file_path)

        assert result["name"] == "test_task"
        assert result["goal"] == "Test submodules and steps"
        assert "submodules" in result
        assert len(result["workflow"]) == 2

    def test_load_missing_required_fields(self, parser, temp_yaml_file):
        """Test that loading fails when required fields are missing"""
        # Missing 'workflow' field
        yaml_content = {"name": "test_task", "goal": "Test loading YAML"}
        file_path = temp_yaml_file(yaml_content)

        with pytest.raises(ValueError, match="Missing required field: workflow"):
            parser.load_task(file_path)

    def test_env_variable_expansion(self, parser, tmp_path):
        """Test environment variable expansion in YAML content"""
        # Set environment variable
        os.environ["TEST_VAR"] = "test_value"
        os.environ["TEST_VAR_2"] = "value2"

        yaml_content = """
name: "test_${TEST_VAR}"
goal: "Test with ${TEST_VAR_2}"
workflow:
  - step:
      name: "step1"
      instruction: "Use ${TEST_VAR}"
"""
        file_path = tmp_path / "test_env.yaml"
        with open(file_path, "w") as f:
            f.write(yaml_content)

        result = parser.load_task(str(file_path))

        assert result["name"] == "test_test_value"
        assert result["goal"] == "Test with value2"

        # Clean up
        del os.environ["TEST_VAR"]
        del os.environ["TEST_VAR_2"]

    def test_env_variable_with_default(self, parser, tmp_path):
        """Test environment variable expansion with default values"""
        yaml_content = """
name: "test_${NONEXISTENT_VAR:-default_name}"
goal: "Test default"
workflow:
  - step:
      name: "step1"
      instruction: "Test"
"""
        file_path = tmp_path / "test_env_default.yaml"
        with open(file_path, "w") as f:
            f.write(yaml_content)

        result = parser.load_task(str(file_path))

        assert result["name"] == "test_default_name"

    def test_validate_task_missing_name(self, parser):
        """Test validation fails when task name is missing"""
        task_data = {"goal": "Test", "workflow": []}

        with pytest.raises(ValueError, match="Missing required field: name"):
            parser._validate_task(task_data)

    def test_validate_task_workflow_not_list(self, parser):
        """Test validation fails when workflow is not a list"""
        task_data = {"name": "test", "goal": "Test", "workflow": "not a list"}

        with pytest.raises(ValueError, match="Workflow must be a list"):
            parser._validate_task(task_data)

    def test_expand_template_variables(self, parser):
        """Test template variable expansion"""
        parser.context = {"topic": "AI", "counter": 5}

        text = "Research about {{topic}} iteration {{counter}}"
        result = parser._expand_template(text)

        assert result == "Research about AI iteration 5"

    def test_expand_template_missing_variable(self, parser):
        """Test template expansion with missing variable keeps placeholder"""
        parser.context = {"existing": "value"}

        text = "Has {{existing}} but {{missing}}"
        result = parser._expand_template(text)

        assert result == "Has value but {{missing}}"

    def test_parse_basic_step(self, parser):
        """Test parsing a basic step"""
        step_data = {
            "name": "test_step",
            "instruction": "Do something",
            "output_file": "output.txt",
        }

        result = parser._parse_basic_step(step_data)

        assert result["type"] == "step"
        assert result["name"] == "test_step"
        assert result["instruction"] == "Do something"
        assert result["output_file"] == "output.txt"

    def test_parse_for_each_step(self, parser):
        """Test parsing a for_each loop step"""
        step_data = {
            "variable": "item",
            "in": ["a", "b", "c"],
            "limit": 2,
            "steps": [{"task": {"name": "process", "instruction": "Process {{item}}"}}],
        }

        result = parser._parse_for_each_step(step_data)

        assert result["type"] == "loop"
        assert result["variable"] == "item"
        assert result["source"] == ["a", "b", "c"]
        assert result["limit"] == 2
        assert len(result["body"]) == 1

    def test_parse_if_step(self, parser):
        """Test parsing a conditional if step"""
        step_data = {
            "condition": "var == 'value'",
            "then": [{"task": {"name": "then_step", "instruction": "Do then"}}],
            "else": [{"task": {"name": "else_step", "instruction": "Do else"}}],
        }

        result = parser._parse_if_step(step_data)

        assert result["type"] == "conditional"
        assert result["condition"] == "var == 'value'"
        assert len(result["then"]) == 1
        assert len(result["else"]) == 1

    def test_parse_while_step(self, parser):
        """Test parsing a while loop step"""
        step_data = {
            "condition": "counter < 10",
            "max_iterations": 5,
            "steps": [
                {"task": {"name": "loop_body", "instruction": "Do work"}},
                {"increment": "counter"},
            ],
        }

        result = parser._parse_while_step(step_data)

        assert result["type"] == "while_loop"
        assert result["condition"] == "counter < 10"
        assert result["max_iterations"] == 5
        assert len(result["steps"]) == 2

    def test_parse_switch_step(self, parser):
        """Test parsing a switch/case step"""
        step_data = {
            "variable": "format",
            "cases": {
                "json": [
                    {"task": {"name": "json_step", "instruction": "Format as JSON"}}
                ],
                "yaml": [
                    {"task": {"name": "yaml_step", "instruction": "Format as YAML"}}
                ],
            },
            "default": [
                {"task": {"name": "default_step", "instruction": "Default format"}}
            ],
        }

        result = parser._parse_switch_step(step_data)

        assert result["type"] == "switch"
        assert result["variable"] == "format"
        assert "json" in result["cases"]
        assert "yaml" in result["cases"]
        assert len(result["default"]) == 1

    def test_parse_increment_step(self, parser):
        """Test parsing an increment step"""
        step_data = "counter"

        result = parser._parse_increment_step(step_data)

        assert result["type"] == "increment"
        assert result["variable"] == "counter"

    def test_validate_yaml_syntax_valid(self, parser, temp_yaml_file):
        """Test YAML syntax validation with valid file"""
        yaml_content = {"name": "test", "goal": "test", "workflow": []}
        file_path = temp_yaml_file(yaml_content)

        is_valid, message = parser.validate_yaml_syntax(file_path)

        assert is_valid
        assert message == "Valid YAML syntax"

    def test_validate_yaml_syntax_invalid(self, parser, tmp_path):
        """Test YAML syntax validation with invalid file"""
        file_path = tmp_path / "invalid.yaml"
        with open(file_path, "w") as f:
            f.write("name: test\ninvalid: [unclosed bracket")

        is_valid, message = parser.validate_yaml_syntax(str(file_path))

        assert not is_valid
        assert "YAML syntax error" in message


class TestConvertJSONToYAML:
    """Test cases for JSON to YAML conversion"""

    def test_convert_basic_json_to_yaml(self, tmp_path):
        """Test converting a basic JSON task to YAML"""
        json_content = {
            "task_name": "test_task",
            "goal": "Test conversion",
            "constraints": {"max_iterations": 10},
            "control_flows": [
                {"type": "step", "name": "step1", "instruction": "Do something"}
            ],
        }

        json_file = tmp_path / "test.json"
        with open(json_file, "w") as f:
            import json

            json.dump(json_content, f)

        yaml_file = convert_json_to_yaml(str(json_file))

        assert os.path.exists(yaml_file)

        with open(yaml_file, "r") as f:
            yaml_data = yaml.safe_load(f)

        assert yaml_data["name"] == "test_task"
        assert yaml_data["goal"] == "Test conversion"
        assert yaml_data["config"]["max_iterations"] == 10

    def test_convert_loop_flow(self, tmp_path):
        """Test converting loop control flow"""
        json_content = {
            "task_name": "test",
            "goal": "test",
            "control_flows": [
                {
                    "type": "loop",
                    "variable": "item",
                    "source": "items",
                    "max_iterations": 5,
                    "body": {"process": "Process item"},
                }
            ],
        }

        json_file = tmp_path / "test_loop.json"
        with open(json_file, "w") as f:
            import json

            json.dump(json_content, f)

        yaml_file = convert_json_to_yaml(str(json_file))

        with open(yaml_file, "r") as f:
            yaml_data = yaml.safe_load(f)

        assert "for_each" in yaml_data["workflow"][0]
        assert yaml_data["workflow"][0]["for_each"]["variable"] == "item"
