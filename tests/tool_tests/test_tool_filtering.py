"""
Unit tests for tools/filtering.py

Tests the EffectiveToolConfig class and tool filtering functionality including:
- Plan-level tool filtering
- Step-level tool filtering
- Intersection of plan and step filters
- Submodule tool filtering
"""

import pytest

from harness.tools.filtering import EffectiveToolConfig
from harness.types.context import ContextKeys


class TestEffectiveToolConfigCompute:
    """Tests for EffectiveToolConfig.compute() method"""

    @pytest.fixture
    def sample_tools(self):
        """Create sample tools for testing"""
        return [
            {"function": {"name": "tool1", "description": "Tool 1"}},
            {"function": {"name": "tool2", "description": "Tool 2"}},
            {"function": {"name": "tool3", "description": "Tool 3"}},
            {"function": {"name": "tool4", "description": "Tool 4"}},
        ]

    # Basic filtering tests
    def test_no_filtering(self, sample_tools):
        """Test that all tools are returned when no filtering is specified"""
        context = {}
        config = EffectiveToolConfig.compute(sample_tools, context)

        assert len(config.tools) == 4
        assert config.submodule_tools == []
        assert config.enabled_submodule_names == []

    def test_plan_level_filtering(self, sample_tools):
        """Test filtering with only plan-level enabled_tools"""
        context = {ContextKeys.ENABLED_TOOLS: ["tool1", "tool2"]}
        config = EffectiveToolConfig.compute(sample_tools, context)

        assert len(config.tools) == 2
        tool_names = [t["function"]["name"] for t in config.tools]
        assert "tool1" in tool_names
        assert "tool2" in tool_names
        assert "tool3" not in tool_names
        assert "tool4" not in tool_names

    def test_step_level_filtering(self, sample_tools):
        """Test filtering with only step-level enabled_tools"""
        context = {}
        step_config = {ContextKeys.ENABLED_TOOLS: ["tool2", "tool3"]}
        config = EffectiveToolConfig.compute(sample_tools, context, step_config)

        assert len(config.tools) == 2
        tool_names = [t["function"]["name"] for t in config.tools]
        assert "tool2" in tool_names
        assert "tool3" in tool_names

    def test_plan_and_step_intersection(self, sample_tools):
        """Test that plan and step filters use intersection"""
        context = {ContextKeys.ENABLED_TOOLS: ["tool1", "tool2", "tool3"]}
        step_config = {ContextKeys.ENABLED_TOOLS: ["tool2", "tool3", "tool4"]}
        config = EffectiveToolConfig.compute(sample_tools, context, step_config)

        # Only tool2 and tool3 are in both lists
        assert len(config.tools) == 2
        tool_names = [t["function"]["name"] for t in config.tools]
        assert "tool2" in tool_names
        assert "tool3" in tool_names

    def test_empty_intersection(self, sample_tools):
        """Test that empty intersection returns no tools"""
        context = {ContextKeys.ENABLED_TOOLS: ["tool1"]}
        step_config = {ContextKeys.ENABLED_TOOLS: ["tool4"]}
        config = EffectiveToolConfig.compute(sample_tools, context, step_config)

        assert len(config.tools) == 0

    def test_nonexistent_tools_ignored(self, sample_tools):
        """Test that nonexistent tool names are ignored"""
        context = {ContextKeys.ENABLED_TOOLS: ["nonexistent", "tool1"]}
        config = EffectiveToolConfig.compute(sample_tools, context)

        assert len(config.tools) == 1
        assert config.tools[0]["function"]["name"] == "tool1"

    # Input normalization tests
    def test_single_string_normalized_to_list(self, sample_tools):
        """Test that single string is normalized to list"""
        context = {ContextKeys.ENABLED_TOOLS: "tool1"}
        config = EffectiveToolConfig.compute(sample_tools, context)

        assert len(config.tools) == 1
        assert config.tools[0]["function"]["name"] == "tool1"

    def test_tuple_normalized_to_list(self, sample_tools):
        """Test that tuple is normalized to list"""
        context = {ContextKeys.ENABLED_TOOLS: ("tool1", "tool2")}
        config = EffectiveToolConfig.compute(sample_tools, context)

        assert len(config.tools) == 2

    def test_set_normalized_to_list(self, sample_tools):
        """Test that set is normalized to list"""
        context = {ContextKeys.ENABLED_TOOLS: {"tool1", "tool2"}}
        config = EffectiveToolConfig.compute(sample_tools, context)

        assert len(config.tools) == 2

    # Submodule filtering tests
    def test_submodule_tools_no_filtering(self):
        """Test that all submodule tools are returned when no filtering"""
        tools = []
        submodule_tools = [
            {"function": {"name": "sub1"}},
            {"function": {"name": "sub2"}},
        ]
        context = {ContextKeys.SUBMODULE_TOOLS: submodule_tools}
        config = EffectiveToolConfig.compute(tools, context)

        assert len(config.submodule_tools) == 2

    def test_submodule_tools_plan_level_filtering(self):
        """Test submodule filtering with plan-level enabled_submodules"""
        tools = []
        submodule_tools = [
            {"function": {"name": "sub1"}},
            {"function": {"name": "sub2"}},
            {"function": {"name": "sub3"}},
        ]
        context = {
            ContextKeys.SUBMODULE_TOOLS: submodule_tools,
            ContextKeys.ENABLED_SUBMODULES: ["sub1", "sub2"],
        }
        config = EffectiveToolConfig.compute(tools, context)

        assert len(config.submodule_tools) == 2
        names = [t["function"]["name"] for t in config.submodule_tools]
        assert "sub1" in names
        assert "sub2" in names
        assert "sub3" not in names

    def test_submodule_tools_step_level_filtering(self):
        """Test submodule filtering with step-level enabled_submodules"""
        tools = []
        submodule_tools = [
            {"function": {"name": "sub1"}},
            {"function": {"name": "sub2"}},
        ]
        context = {ContextKeys.SUBMODULE_TOOLS: submodule_tools}
        step_config = {ContextKeys.ENABLED_SUBMODULES: ["sub1"]}
        config = EffectiveToolConfig.compute(tools, context, step_config)

        assert len(config.submodule_tools) == 1
        assert config.submodule_tools[0]["function"]["name"] == "sub1"

    def test_submodule_tools_intersection(self):
        """Test submodule filtering intersection"""
        tools = []
        submodule_tools = [
            {"function": {"name": "sub1"}},
            {"function": {"name": "sub2"}},
            {"function": {"name": "sub3"}},
        ]
        context = {
            ContextKeys.SUBMODULE_TOOLS: submodule_tools,
            ContextKeys.ENABLED_SUBMODULES: ["sub1", "sub2"],
        }
        step_config = {ContextKeys.ENABLED_SUBMODULES: ["sub2", "sub3"]}
        config = EffectiveToolConfig.compute(tools, context, step_config)

        # Only sub2 is in both
        assert len(config.submodule_tools) == 1
        assert config.submodule_tools[0]["function"]["name"] == "sub2"

    # Enabled submodule names tests
    def test_enabled_submodule_names_from_registry(self):
        """Test enabled submodule names extracted from registry"""
        tools = []
        context = {
            ContextKeys.SUBMODULE_REGISTRY: {
                "sub1": "spec1",
                "sub2": "spec2",
            }
        }
        config = EffectiveToolConfig.compute(tools, context)

        assert set(config.enabled_submodule_names) == {"sub1", "sub2"}

    def test_enabled_submodule_names_filtered(self):
        """Test enabled submodule names are filtered"""
        tools = []
        context = {
            ContextKeys.SUBMODULE_REGISTRY: {
                "sub1": "spec1",
                "sub2": "spec2",
                "sub3": "spec3",
            },
            ContextKeys.ENABLED_SUBMODULES: ["sub1", "sub3"],
        }
        config = EffectiveToolConfig.compute(tools, context)

        assert set(config.enabled_submodule_names) == {"sub1", "sub3"}

    def test_enabled_submodule_names_from_tools_fallback(self):
        """Test enabled submodule names fall back to tools when no registry"""
        tools = []
        submodule_tools = [
            {"function": {"name": "sub1"}},
            {"function": {"name": "sub2"}},
        ]
        context = {ContextKeys.SUBMODULE_TOOLS: submodule_tools}
        config = EffectiveToolConfig.compute(tools, context)

        assert set(config.enabled_submodule_names) == {"sub1", "sub2"}


class TestEffectiveToolConfigDataclass:
    """Tests for EffectiveToolConfig dataclass properties"""

    def test_dataclass_fields(self):
        """Test that dataclass has expected fields"""
        config = EffectiveToolConfig(
            tools=[{"function": {"name": "tool1"}}],
            submodule_tools=[{"function": {"name": "sub1"}}],
            enabled_submodule_names=["sub1"],
        )

        assert config.tools == [{"function": {"name": "tool1"}}]
        assert config.submodule_tools == [{"function": {"name": "sub1"}}]
        assert config.enabled_submodule_names == ["sub1"]

    def test_empty_config(self):
        """Test creating empty config"""
        config = EffectiveToolConfig(
            tools=[], submodule_tools=[], enabled_submodule_names=[]
        )

        assert config.tools == []
        assert config.submodule_tools == []
        assert config.enabled_submodule_names == []


class TestToolNameExtraction:
    """Tests for tool name extraction from various formats"""

    def test_function_as_dict(self):
        """Test extracting name from dict-style function"""
        tools = [{"function": {"name": "tool1"}}]
        context = {ContextKeys.ENABLED_TOOLS: ["tool1"]}
        config = EffectiveToolConfig.compute(tools, context)

        assert len(config.tools) == 1

    def test_function_as_object_with_name_attribute(self):
        """Test extracting name from object with name attribute"""

        class MockFunction:
            def __init__(self, name):
                self.name = name

        tools = [{"function": MockFunction("tool1")}]
        context = {ContextKeys.ENABLED_TOOLS: ["tool1"]}
        config = EffectiveToolConfig.compute(tools, context)

        assert len(config.tools) == 1


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_tools_list(self):
        """Test with empty tools list"""
        config = EffectiveToolConfig.compute([], {})
        assert config.tools == []

    def test_none_step_config(self):
        """Test with None step_config"""
        tools = [{"function": {"name": "tool1"}}]
        config = EffectiveToolConfig.compute(tools, {}, None)
        assert len(config.tools) == 1

    def test_empty_enabled_list(self):
        """Test with empty enabled list"""
        tools = [{"function": {"name": "tool1"}}]
        context = {ContextKeys.ENABLED_TOOLS: []}
        config = EffectiveToolConfig.compute(tools, context)

        assert len(config.tools) == 0

    def test_no_submodule_tools(self):
        """Test when no submodule tools exist"""
        tools = [{"function": {"name": "tool1"}}]
        context = {}
        config = EffectiveToolConfig.compute(tools, context)

        assert config.submodule_tools == []
        assert config.enabled_submodule_names == []
