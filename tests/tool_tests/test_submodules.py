"""
Unit tests for submodules/specs.py and submodules/loader.py

Tests the submodule specification and loading functionality including:
- SubmoduleParamSpec dataclass
- SubmoduleFunctionSpec dataclass
- Submodule result extraction
- Submodule loading from YAML
- Tool definition building
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from harness.submodules.loader import (build_submodule_tool,
                                       load_submodule_tools_for_yaml,
                                       normalize_submodule_declarations,
                                       parse_submodule_function_declaration)
from harness.submodules.specs import (SubmoduleFunctionSpec,
                                      SubmoduleParamSpec,
                                      extract_submodule_result_value)


class TestSubmoduleParamSpec:
    """Tests for SubmoduleParamSpec dataclass"""

    def test_default_values(self):
        """Test default values for SubmoduleParamSpec"""
        spec = SubmoduleParamSpec(name="param1")
        assert spec.name == "param1"
        assert spec.param_type == "string"
        assert spec.description == ""
        assert spec.required is True
        assert spec.source == "model"
        assert spec.default is None
        assert spec.schema is None

    def test_custom_values(self):
        """Test custom values for SubmoduleParamSpec"""
        spec = SubmoduleParamSpec(
            name="count",
            param_type="integer",
            description="Number of items",
            required=False,
            source="context",
            default=10,
            schema={"type": "integer", "minimum": 0},
        )
        assert spec.name == "count"
        assert spec.param_type == "integer"
        assert spec.description == "Number of items"
        assert spec.required is False
        assert spec.source == "context"
        assert spec.default == 10
        assert spec.schema == {"type": "integer", "minimum": 0}

    def test_frozen(self):
        """Test that SubmoduleParamSpec is frozen/immutable"""
        spec = SubmoduleParamSpec(name="param1")
        with pytest.raises(AttributeError):
            spec.name = "new_name"


class TestSubmoduleFunctionSpec:
    """Tests for SubmoduleFunctionSpec dataclass"""

    def test_default_values(self):
        """Test default values for SubmoduleFunctionSpec"""
        spec = SubmoduleFunctionSpec(
            name="my_func", description="A function", module_path="/path/to/module.yaml"
        )
        assert spec.name == "my_func"
        assert spec.description == "A function"
        assert spec.module_path == "/path/to/module.yaml"
        assert spec.model_params == []
        assert spec.context_params == []
        assert spec.return_var == "prev_output"

    def test_with_params(self):
        """Test SubmoduleFunctionSpec with parameters"""
        model_param = SubmoduleParamSpec(name="input", source="model")
        context_param = SubmoduleParamSpec(name="config", source="context")

        spec = SubmoduleFunctionSpec(
            name="my_func",
            description="A function",
            module_path="/path/to/module.yaml",
            model_params=[model_param],
            context_params=[context_param],
            return_var="result",
        )
        assert len(spec.model_params) == 1
        assert len(spec.context_params) == 1
        assert spec.return_var == "result"


class TestExtractSubmoduleResultValue:
    """Tests for extract_submodule_result_value function"""

    def test_none_value(self):
        """Test with None value"""
        result = extract_submodule_result_value(None)
        assert result is None

    def test_string_with_return(self):
        """Test string value with RETURN: prefix"""
        result = extract_submodule_result_value("RETURN: 42")
        assert result == "42"

    def test_string_with_multiline_return(self):
        """Test string value with multiline RETURN"""
        text = """RETURN: line1
line2
line3"""
        result = extract_submodule_result_value(text)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_string_without_return(self):
        """Test string without RETURN: prefix"""
        result = extract_submodule_result_value("just some text")
        assert result is None

    def test_dict_with_output_key(self):
        """Test dict with 'output' key containing RETURN"""
        result = extract_submodule_result_value({"output": "RETURN: value123"})
        assert result == "value123"

    def test_dict_with_content_key(self):
        """Test dict with 'content' key containing RETURN"""
        result = extract_submodule_result_value({"content": "RETURN: content_value"})
        assert result == "content_value"

    def test_dict_with_result_key(self):
        """Test dict with 'result' key containing RETURN"""
        result = extract_submodule_result_value({"result": "RETURN: result_value"})
        assert result == "result_value"

    def test_dict_with_stdout_key(self):
        """Test dict with 'stdout' key containing RETURN"""
        result = extract_submodule_result_value({"stdout": "RETURN: stdout_value"})
        assert result == "stdout_value"

    def test_dict_without_return(self):
        """Test dict without RETURN in any key"""
        result = extract_submodule_result_value({"output": "no return prefix"})
        assert result is None

    def test_other_type_serialized(self):
        """Test other types are serialized to JSON"""
        result = extract_submodule_result_value([1, 2, 3])
        # Should be serialized and searched for RETURN
        assert result is None  # No RETURN in serialized [1, 2, 3]


class TestNormalizeSubmoduleDeclarations:
    """Tests for normalize_submodule_declarations function"""

    def test_empty_submodules(self):
        """Test with no submodules"""
        yaml_data = {"name": "test", "workflow": []}
        result = normalize_submodule_declarations(yaml_data, "/path/to/main.yaml")
        assert result == []

    def test_list_format(self):
        """Test with list format submodules"""
        yaml_data = {
            "submodules": [
                {"name": "mod1", "path": "mod1.yaml"},
                {"name": "mod2", "path": "mod2.yaml"},
            ]
        }
        result = normalize_submodule_declarations(yaml_data, "/base/main.yaml")
        assert len(result) == 2
        assert result[0]["name"] == "mod1"
        assert result[1]["name"] == "mod2"

    def test_dict_format(self):
        """Test with dict format submodules"""
        yaml_data = {"submodules": {"mod1": "mod1.yaml", "mod2": "mod2.yaml"}}
        result = normalize_submodule_declarations(yaml_data, "/base/main.yaml")
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "mod1" in names
        assert "mod2" in names

    def test_string_format(self):
        """Test with string-only submodule entries"""
        yaml_data = {"submodules": ["mod1.yaml", "mod2.yaml"]}
        result = normalize_submodule_declarations(yaml_data, "/base/main.yaml")
        assert len(result) == 2
        # Name should be None, path should be set
        assert result[0]["name"] is None

    def test_relative_path_resolution(self):
        """Test that relative paths are resolved correctly"""
        yaml_data = {"submodules": [{"name": "mod1", "path": "subdir/mod1.yaml"}]}
        result = normalize_submodule_declarations(yaml_data, "/base/main.yaml")
        assert "/base/subdir/mod1.yaml" in result[0]["path"]

    def test_absolute_path_preserved(self):
        """Test that absolute paths are preserved"""
        yaml_data = {
            "submodules": [{"name": "mod1", "path": "/absolute/path/mod1.yaml"}]
        }
        result = normalize_submodule_declarations(yaml_data, "/base/main.yaml")
        assert result[0]["path"] == "/absolute/path/mod1.yaml"

    def test_invalid_format_raises(self):
        """Test that invalid format raises ValueError"""
        yaml_data = {"submodules": "invalid_string"}
        with pytest.raises(ValueError, match="must be a list or mapping"):
            normalize_submodule_declarations(yaml_data, "/base/main.yaml")


class TestBuildSubmoduleTool:
    """Tests for build_submodule_tool function"""

    def test_basic_tool(self):
        """Test building a basic tool definition"""
        spec = SubmoduleFunctionSpec(
            name="add_numbers",
            description="Add two numbers",
            module_path="/path/to/add.yaml",
        )
        tool = build_submodule_tool(spec)

        assert tool["type"] == "function"
        assert tool["function"]["name"] == "add_numbers"
        assert tool["function"]["description"] == "Add two numbers"
        assert tool["function"]["parameters"]["type"] == "object"

    def test_tool_with_params(self):
        """Test building tool with parameters"""
        spec = SubmoduleFunctionSpec(
            name="process",
            description="Process data",
            module_path="/path/to/process.yaml",
            model_params=[
                SubmoduleParamSpec(name="input", param_type="string", required=True),
                SubmoduleParamSpec(name="count", param_type="integer", required=False),
            ],
        )
        tool = build_submodule_tool(spec)

        params = tool["function"]["parameters"]
        assert "input" in params["properties"]
        assert "count" in params["properties"]
        assert "input" in params["required"]
        assert "count" not in params["required"]

    def test_tool_with_schema(self):
        """Test building tool with custom schema"""
        spec = SubmoduleFunctionSpec(
            name="process",
            description="Process data",
            module_path="/path/to/process.yaml",
            model_params=[
                SubmoduleParamSpec(
                    name="config",
                    schema={
                        "type": "object",
                        "properties": {"key": {"type": "string"}},
                    },
                ),
            ],
        )
        tool = build_submodule_tool(spec)

        params = tool["function"]["parameters"]
        assert params["properties"]["config"]["type"] == "object"


class TestParseSubmoduleFunctionDeclaration:
    """Tests for parse_submodule_function_declaration function"""

    def test_basic_declaration(self):
        """Test parsing basic function declaration"""
        yaml_data = {
            "function": {
                "name": "my_func",
                "description": "A test function",
                "return": "result",
            }
        }
        spec = parse_submodule_function_declaration(yaml_data, "/path/to/module.yaml")

        assert spec.name == "my_func"
        assert spec.description == "A test function"
        assert spec.return_var == "result"
        assert spec.module_path == "/path/to/module.yaml"

    def test_with_list_parameters(self):
        """Test parsing with list-style parameters"""
        yaml_data = {
            "function": {
                "name": "my_func",
                "description": "A test function",
                "parameters": [
                    {"name": "input", "type": "string"},
                    {"name": "count", "type": "integer", "required": False},
                ],
            }
        }
        spec = parse_submodule_function_declaration(yaml_data, "/path/to/module.yaml")

        assert len(spec.model_params) == 2
        assert spec.model_params[0].name == "input"
        assert spec.model_params[1].name == "count"
        assert spec.model_params[1].required is False

    def test_with_dict_parameters(self):
        """Test parsing with dict-style parameters (model/context split)"""
        yaml_data = {
            "function": {
                "name": "my_func",
                "description": "A test function",
                "parameters": {"model": ["input"], "context": ["config"]},
            }
        }
        spec = parse_submodule_function_declaration(yaml_data, "/path/to/module.yaml")

        assert len(spec.model_params) == 1
        assert len(spec.context_params) == 1
        assert spec.model_params[0].name == "input"
        assert spec.context_params[0].name == "config"

    def test_missing_function_block_raises(self):
        """Test that missing function block raises ValueError"""
        yaml_data = {"name": "module"}
        with pytest.raises(
            ValueError, match="must define a top-level 'function' block"
        ):
            parse_submodule_function_declaration(yaml_data, "/path/to/module.yaml")

    def test_missing_name_raises(self):
        """Test that missing function name raises ValueError"""
        yaml_data = {"function": {"description": "No name"}}
        with pytest.raises(ValueError, match="function must define a name"):
            parse_submodule_function_declaration(yaml_data, "/path/to/module.yaml")

    def test_name_mismatch_raises(self):
        """Test that name mismatch raises ValueError"""
        yaml_data = {"function": {"name": "actual_name", "description": "Test"}}
        with pytest.raises(ValueError, match="name mismatch"):
            parse_submodule_function_declaration(
                yaml_data, "/path/to/module.yaml", declared_name="different_name"
            )


class TestLoadSubmoduleToolsForYaml:
    """Integration tests for load_submodule_tools_for_yaml function"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_load_single_submodule(self, temp_dir):
        """Test loading a single submodule"""
        # Create submodule file
        submodule_yaml = {
            "name": "add_task",
            "goal": "Add numbers",
            "function": {
                "name": "add",
                "description": "Add two numbers",
                "parameters": [
                    {"name": "a", "type": "integer"},
                    {"name": "b", "type": "integer"},
                ],
                "return": "sum",
            },
            "workflow": [
                {"task": {"name": "add", "instruction": "Add {{a}} and {{b}}"}}
            ],
        }
        submodule_path = os.path.join(temp_dir, "add.yaml")
        with open(submodule_path, "w") as f:
            yaml.dump(submodule_yaml, f)

        # Create main file
        main_yaml = {
            "name": "main",
            "goal": "Test",
            "workflow": [],
            "submodules": [{"name": "add", "path": "add.yaml"}],
        }
        main_path = os.path.join(temp_dir, "main.yaml")
        with open(main_path, "w") as f:
            yaml.dump(main_yaml, f)

        # Load submodules
        tools, registry = load_submodule_tools_for_yaml(main_yaml, main_path)

        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "add"
        assert "add" in registry
        assert registry["add"].return_var == "sum"

    def test_no_submodules(self, temp_dir):
        """Test with no submodules defined"""
        main_yaml = {"name": "main", "goal": "Test", "workflow": []}
        main_path = os.path.join(temp_dir, "main.yaml")

        tools, registry = load_submodule_tools_for_yaml(main_yaml, main_path)

        assert tools == []
        assert registry == {}

    def test_duplicate_name_raises(self, temp_dir):
        """Test that duplicate submodule names raise ValueError"""
        # Create two submodule files with same function name
        submodule_yaml = {
            "name": "task",
            "goal": "Do something",
            "function": {"name": "same_name", "description": "Same name"},
            "workflow": [],
        }

        path1 = os.path.join(temp_dir, "mod1.yaml")
        path2 = os.path.join(temp_dir, "mod2.yaml")
        with open(path1, "w") as f:
            yaml.dump(submodule_yaml, f)
        with open(path2, "w") as f:
            yaml.dump(submodule_yaml, f)

        main_yaml = {
            "name": "main",
            "goal": "Test",
            "workflow": [],
            "submodules": [
                {"name": "same_name", "path": "mod1.yaml"},
                {"name": "same_name", "path": "mod2.yaml"},
            ],
        }
        main_path = os.path.join(temp_dir, "main.yaml")

        with pytest.raises(ValueError, match="Duplicate submodule function name"):
            load_submodule_tools_for_yaml(main_yaml, main_path)
