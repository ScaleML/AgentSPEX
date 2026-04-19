"""
Comprehensive unit tests for per-file model configuration feature.

This module tests:
1. EffectiveArgs class - immutable wrapper for execution arguments
2. YAMLTaskParser.get_config_with_defaults() - config extraction from YAML
3. Config inheritance between parent and submodule workflows
4. YAML config fallback when .env file is not present
5. Thread-safety for parallel execution
"""

import copy
import os
import tempfile
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from harness.parsing import YAMLTaskParser
from harness.run import apply_yaml_config_fallback, load_yaml_config
from harness.types.config import EffectiveArgs

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_args():
    """Create a sample argparse namespace similar to what run.py produces."""
    return Namespace(
        model="gpt-4o",
        max_tokens_per_step=100000,
        max_tool_calls_per_step=10,
        temperature=0.2,
        plan_revision_max_steps=0,
        workflow_file="/path/to/task.yaml",
        mcp_url="http://localhost:7002/mcp",
        mode="simple",
    )


@pytest.fixture
def sample_args_with_none():
    """Create args with None values (unset CLI args)."""
    return Namespace(
        model=None,
        max_tokens_per_step=None,
        max_tool_calls_per_step=None,
        temperature=None,
        plan_revision_max_steps=None,
        workflow_file="/path/to/task.yaml",
        mcp_url="http://localhost:7002/mcp",
        mode="simple",
    )


@pytest.fixture
def yaml_config_full():
    """Full YAML config with all settings."""
    return {
        "model": "gpt-5-mini",
        "max_tokens_per_step": 150000,
        "max_tool_calls_per_step": 15,
        "temperature": 0.5,
        "plan_revision_max_steps": 2,
    }


@pytest.fixture
def yaml_config_partial():
    """Partial YAML config with some settings."""
    return {
        "model": "o3-mini",
        "max_tokens_per_step": 120000,
    }


@pytest.fixture
def temp_yaml_files():
    """Create temporary YAML test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Main workflow with config
        main_yaml = os.path.join(tmpdir, "main_workflow.yaml")
        with open(main_yaml, "w") as f:
            f.write("""name: "test_main_workflow"
goal: "Test main workflow with config"

config:
    model: "gpt-4o"
    max_tokens_per_step: 150000
    max_tool_calls_per_step: 15

parameters:
    topic: "test topic"

workflow:
    - step:
        name: "test_step"
        instruction: "Do something"
""")

        # Submodule with custom config
        submodule_with_config = os.path.join(tmpdir, "submodule_with_config.yaml")
        with open(submodule_with_config, "w") as f:
            f.write("""name: "submodule_with_custom_config"
goal: "Submodule that overrides parent config"

config:
    model: "gpt-4o-mini"
    max_tokens_per_step: 50000

parameters:
    input: "${INPUT}"

workflow:
    - step:
        name: "sub_step"
        instruction: "Process input"
""")

        # Submodule without config (inherits parent)
        submodule_no_config = os.path.join(tmpdir, "submodule_no_config.yaml")
        with open(submodule_no_config, "w") as f:
            f.write("""name: "submodule_inherits_config"
goal: "Submodule that inherits parent config"

parameters:
    data: "${DATA}"

workflow:
    - step:
        name: "inherit_step"
        instruction: "Use parent config"
""")

        # YAML without config section
        no_config_yaml = os.path.join(tmpdir, "no_config_workflow.yaml")
        with open(no_config_yaml, "w") as f:
            f.write("""name: "test_no_config"
goal: "Test workflow without config section"

parameters:
    value: "test"

workflow:
    - step:
        name: "simple_step"
        instruction: "Do simple task"
""")

        yield {
            "dir": tmpdir,
            "main_yaml": main_yaml,
            "submodule_with_config": submodule_with_config,
            "submodule_no_config": submodule_no_config,
            "no_config_yaml": no_config_yaml,
        }


# =============================================================================
# Test EffectiveArgs Class
# =============================================================================


class TestEffectiveArgs:
    """Tests for the EffectiveArgs dataclass."""

    def test_default_values(self):
        """Test that EffectiveArgs has correct default values."""
        args = EffectiveArgs()
        assert args.model == "gpt-4.1-mini"
        assert args.max_tokens_per_step == 100000
        assert args.max_tool_calls_per_step == 10
        assert args.temperature == 0.2
        assert args.plan_revision_max_steps == 0

    def test_from_args_with_all_values(self, sample_args):
        """Test creating EffectiveArgs from argparse namespace with all values."""
        effective = EffectiveArgs.from_args(sample_args)
        assert effective.model == "gpt-4o"
        assert effective.max_tokens_per_step == 100000
        assert effective.max_tool_calls_per_step == 10
        assert effective.temperature == 0.2
        assert effective.plan_revision_max_steps == 0
        assert effective.workflow_file == "/path/to/task.yaml"

    def test_from_args_preserves_original_args(self, sample_args):
        """Test that from_args stores reference to original args."""
        effective = EffectiveArgs.from_args(sample_args)
        # Access an attribute not in EffectiveArgs via __getattr__
        assert effective.mcp_url == "http://localhost:7002/mcp"
        assert effective.mode == "simple"

    def test_with_yaml_config_creates_new_object(self, sample_args, yaml_config_full):
        """Test that with_yaml_config returns a NEW object (immutable)."""
        original = EffectiveArgs.from_args(sample_args)
        modified = original.with_yaml_config(yaml_config_full)

        # Check they are different objects
        assert original is not modified

        # Original should be unchanged
        assert original.model == "gpt-4o"
        assert original.max_tokens_per_step == 100000

        # Modified should have new values
        assert modified.model == "gpt-5-mini"
        assert modified.max_tokens_per_step == 150000
        assert modified.max_tool_calls_per_step == 15
        assert modified.temperature == 0.5

    def test_with_yaml_config_partial_override(self, sample_args, yaml_config_partial):
        """Test that partial YAML config only overrides specified values."""
        original = EffectiveArgs.from_args(sample_args)
        modified = original.with_yaml_config(yaml_config_partial)

        # Values in yaml_config should be overridden
        assert modified.model == "o3-mini"
        assert modified.max_tokens_per_step == 120000

        # Values not in yaml_config should be inherited
        assert modified.max_tool_calls_per_step == original.max_tool_calls_per_step
        assert modified.temperature == original.temperature

    def test_with_yaml_config_empty_dict(self, sample_args):
        """Test that empty YAML config doesn't change values."""
        original = EffectiveArgs.from_args(sample_args)
        modified = original.with_yaml_config({})

        assert modified.model == original.model
        assert modified.max_tokens_per_step == original.max_tokens_per_step
        assert modified.max_tool_calls_per_step == original.max_tool_calls_per_step

    def test_immutability_chain(self, sample_args):
        """Test that chained with_yaml_config calls don't affect earlier objects."""
        base = EffectiveArgs.from_args(sample_args)

        first = base.with_yaml_config({"model": "model-1"})
        second = first.with_yaml_config({"model": "model-2"})
        third = second.with_yaml_config({"model": "model-3"})

        assert base.model == "gpt-4o"
        assert first.model == "model-1"
        assert second.model == "model-2"
        assert third.model == "model-3"

    def test_getattr_fallback_to_original_args(self, sample_args):
        """Test that __getattr__ falls back to original args for unknown attributes."""
        effective = EffectiveArgs.from_args(sample_args)

        # These should be accessed via __getattr__
        assert effective.mcp_url == "http://localhost:7002/mcp"
        assert effective.mode == "simple"

    def test_getattr_raises_for_missing_attribute(self):
        """Test that __getattr__ raises AttributeError for truly missing attributes."""
        effective = EffectiveArgs()

        with pytest.raises(AttributeError):
            _ = effective.nonexistent_attribute


# =============================================================================
# Test YAMLTaskParser Config Methods
# =============================================================================


class TestYAMLParserConfig:
    """Tests for YAMLTaskParser config-related methods."""

    def test_get_config_with_defaults_full_config(self, temp_yaml_files):
        """Test getting config from YAML with all values specified."""
        parser = YAMLTaskParser()
        yaml_data = parser.load_task(temp_yaml_files["main_yaml"])
        config = parser.get_config_with_defaults(yaml_data)

        assert config["model"] == "gpt-4o"
        assert config["max_tokens_per_step"] == 150000
        assert config["max_tool_calls_per_step"] == 15
        # These should use defaults since not specified
        assert config["temperature"] == 0.2
        assert config["plan_revision_max_steps"] == 0

    def test_get_config_with_defaults_no_config_section(self, temp_yaml_files):
        """Test getting config from YAML without config section."""
        parser = YAMLTaskParser()
        yaml_data = parser.load_task(temp_yaml_files["no_config_yaml"])
        config = parser.get_config_with_defaults(yaml_data)

        # Should return all defaults
        assert config["model"] == "gpt-4.1-mini"
        assert config["max_tokens_per_step"] == 100000
        assert config["max_tool_calls_per_step"] == 10
        assert config["temperature"] == 0.2
        assert config["plan_revision_max_steps"] == 0

    def test_get_config_with_defaults_partial_config(self, temp_yaml_files):
        """Test getting config from YAML with partial config section."""
        parser = YAMLTaskParser()
        yaml_data = parser.load_task(temp_yaml_files["submodule_with_config"])
        config = parser.get_config_with_defaults(yaml_data)

        # Specified values
        assert config["model"] == "gpt-4o-mini"
        assert config["max_tokens_per_step"] == 50000

        # Defaults for unspecified
        assert config["max_tool_calls_per_step"] == 10
        assert config["temperature"] == 0.2

    def test_has_config_true(self, temp_yaml_files):
        """Test has_config returns True when config section exists."""
        parser = YAMLTaskParser()
        yaml_data = parser.load_task(temp_yaml_files["main_yaml"])
        assert parser.has_config(yaml_data) is True

    def test_has_config_false(self, temp_yaml_files):
        """Test has_config returns False when no config section."""
        parser = YAMLTaskParser()
        yaml_data = parser.load_task(temp_yaml_files["no_config_yaml"])
        assert parser.has_config(yaml_data) is False


# =============================================================================
# Test YAML Config Fallback in run.py
# =============================================================================


class TestYAMLConfigFallback:
    """Tests for apply_yaml_config_fallback function in run.py."""

    def test_fallback_with_all_none_args(self, sample_args_with_none, yaml_config_full):
        """Test that all None args get filled from YAML config."""
        apply_yaml_config_fallback(sample_args_with_none, yaml_config_full)

        assert sample_args_with_none.model == "gpt-5-mini"
        assert sample_args_with_none.max_tokens_per_step == 150000
        assert sample_args_with_none.max_tool_calls_per_step == 15
        assert sample_args_with_none.temperature == 0.5
        assert sample_args_with_none.plan_revision_max_steps == 2

    def test_fallback_preserves_cli_args(self, sample_args, yaml_config_full):
        """Test that CLI args are NOT overwritten by YAML config."""
        original_model = sample_args.model
        original_tokens = sample_args.max_tokens_per_step

        apply_yaml_config_fallback(sample_args, yaml_config_full)

        # CLI values should be preserved
        assert sample_args.model == original_model
        assert sample_args.max_tokens_per_step == original_tokens

    def test_fallback_partial_none_args(self):
        """Test fallback with some args set and some None."""
        args = Namespace(
            model="cli-model",  # Set via CLI
            max_tokens_per_step=None,  # Not set
            max_tool_calls_per_step=5,  # Set via CLI
            temperature=None,  # Not set
            plan_revision_max_steps=None,  # Not set
        )

        yaml_config = {
            "model": "yaml-model",
            "max_tokens_per_step": 200000,
            "max_tool_calls_per_step": 20,
            "temperature": 0.8,
            "plan_revision_max_steps": 3,
        }

        apply_yaml_config_fallback(args, yaml_config)

        # CLI values preserved
        assert args.model == "cli-model"
        assert args.max_tool_calls_per_step == 5

        # None values filled from YAML
        assert args.max_tokens_per_step == 200000
        assert args.temperature == 0.8
        assert args.plan_revision_max_steps == 3

    def test_load_yaml_config_function(self, temp_yaml_files):
        """Test load_yaml_config loads config from YAML file."""
        config = load_yaml_config(temp_yaml_files["main_yaml"])

        assert config["model"] == "gpt-4o"
        assert config["max_tokens_per_step"] == 150000
        assert config["max_tool_calls_per_step"] == 15


# =============================================================================
# Test Config Inheritance
# =============================================================================


class TestConfigInheritance:
    """Tests for config inheritance between parent and submodule."""

    def test_submodule_with_config_overrides_parent(self, temp_yaml_files):
        """Test that submodule config overrides parent config."""
        parser = YAMLTaskParser()

        # Load parent config
        parent_data = parser.load_task(temp_yaml_files["main_yaml"])
        parent_config = parser.get_config_with_defaults(parent_data)

        # Load submodule config
        sub_data = parser.load_task(temp_yaml_files["submodule_with_config"])
        sub_config = sub_data.get("config", {})

        # Create effective args chain
        parent_args = EffectiveArgs(
            model=parent_config["model"],
            max_tokens_per_step=parent_config["max_tokens_per_step"],
        )
        sub_args = parent_args.with_yaml_config(sub_config)

        # Parent unchanged
        assert parent_args.model == "gpt-4o"
        assert parent_args.max_tokens_per_step == 150000

        # Submodule has overridden values
        assert sub_args.model == "gpt-4o-mini"
        assert sub_args.max_tokens_per_step == 50000

    def test_submodule_without_config_inherits_parent(self, temp_yaml_files):
        """Test that submodule without config inherits parent config."""
        parser = YAMLTaskParser()

        # Load parent config
        parent_data = parser.load_task(temp_yaml_files["main_yaml"])
        parent_config = parser.get_config_with_defaults(parent_data)

        # Load submodule (no config)
        sub_data = parser.load_task(temp_yaml_files["submodule_no_config"])
        sub_config = sub_data.get("config", {})

        # Verify no config in submodule
        assert sub_config == {}

        # Create effective args - submodule should inherit
        parent_args = EffectiveArgs(
            model=parent_config["model"],
            max_tokens_per_step=parent_config["max_tokens_per_step"],
        )
        sub_args = parent_args.with_yaml_config(sub_config)  # Empty config

        # Submodule should have same values as parent
        assert sub_args.model == parent_args.model
        assert sub_args.max_tokens_per_step == parent_args.max_tokens_per_step


# =============================================================================
# Test Thread Safety
# =============================================================================


class TestThreadSafety:
    """Tests for thread-safety of EffectiveArgs in parallel execution."""

    def test_parallel_config_creation_isolation(self, sample_args):
        """Test that parallel EffectiveArgs creation doesn't cause race conditions."""
        base_args = EffectiveArgs.from_args(sample_args)

        configs = [
            {"model": f"model-{i}", "max_tokens_per_step": 1000 * i} for i in range(10)
        ]

        results = {}

        def create_effective_args(index, config):
            effective = base_args.with_yaml_config(config)
            return index, effective.model, effective.max_tokens_per_step

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(create_effective_args, i, config): i
                for i, config in enumerate(configs)
            }

            for future in as_completed(futures):
                idx, model, tokens = future.result()
                results[idx] = (model, tokens)

        # Verify each got correct values (no cross-contamination)
        for i in range(10):
            assert results[i] == (f"model-{i}", 1000 * i)

        # Verify base_args is unchanged
        assert base_args.model == "gpt-4o"

    def test_parallel_modification_doesnt_affect_shared_parent(self, sample_args):
        """Test that parallel submodules don't affect shared parent args."""
        parent_args = EffectiveArgs.from_args(sample_args)
        original_model = parent_args.model
        original_tokens = parent_args.max_tokens_per_step

        def simulate_submodule(submodule_config):
            # Each "submodule" creates its own effective args
            sub_args = parent_args.with_yaml_config(submodule_config)
            # Do some work with sub_args
            _ = sub_args.model + "_processed"
            return sub_args.model

        configs = [{"model": f"sub-model-{i}"} for i in range(20)]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(simulate_submodule, c) for c in configs]
            results = [f.result() for f in as_completed(futures)]

        # All submodules should have gotten their own model
        assert len(set(results)) == 20

        # Parent should be completely unchanged
        assert parent_args.model == original_model
        assert parent_args.max_tokens_per_step == original_tokens

    def test_deep_copy_not_needed_for_effective_args(self, sample_args):
        """Test that EffectiveArgs immutability means deep copy isn't needed."""
        original = EffectiveArgs.from_args(sample_args)

        # Simulate what happens in execute_gather_step
        # Each thread gets reference to same 'args' but creates its own effective_args
        def thread_work(config):
            # This is what execute_call_step does
            effective = original.with_yaml_config(config)
            return id(effective), effective.model

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(thread_work, {"model": f"m{i}"}) for i in range(5)
            ]
            results = [f.result() for f in futures]

        # All should be different objects
        ids = [r[0] for r in results]
        assert len(set(ids)) == 5

        # Original unchanged
        assert original.model == "gpt-4o"


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_effective_args_with_missing_original_args_attribute(self):
        """Test EffectiveArgs handles missing attributes in original args."""
        minimal_args = Namespace(model="test")
        effective = EffectiveArgs.from_args(minimal_args)

        # Should use defaults for missing attributes
        assert effective.max_tokens_per_step == 100000
        assert effective.max_tool_calls_per_step == 10

    def test_yaml_config_with_extra_keys(self, temp_yaml_files):
        """Test that extra keys in YAML config are ignored."""
        parser = YAMLTaskParser()

        # Create YAML with extra config keys
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""name: "test"
goal: "test"

config:
    model: "test-model"
    unknown_key: "should be ignored"
    another_unknown: 123

workflow:
    - step:
        name: "test"
        instruction: "test"
""")
            temp_path = f.name

        try:
            yaml_data = parser.load_task(temp_path)
            config = parser.get_config_with_defaults(yaml_data)

            # Known keys should work
            assert config["model"] == "test-model"

            # Unknown keys should not cause errors
            assert "unknown_key" not in config
        finally:
            os.unlink(temp_path)

    def test_effective_args_isinstance_check(self, sample_args):
        """Test isinstance check works correctly for EffectiveArgs."""
        effective = EffectiveArgs.from_args(sample_args)

        assert isinstance(effective, EffectiveArgs)
        assert not isinstance(sample_args, EffectiveArgs)

    def test_config_with_none_values(self):
        """Test handling of None values in YAML config."""
        args = EffectiveArgs(model="original")
        config = {"model": None, "max_tokens_per_step": 50000}

        modified = args.with_yaml_config(config)

        # None should override (explicit None in config)
        assert modified.model is None
        assert modified.max_tokens_per_step == 50000


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestConfigFlowIntegration:
    """Integration-style tests for the complete config flow."""

    def test_complete_config_flow(self, temp_yaml_files):
        """Test complete flow: CLI args -> YAML config -> submodule config."""
        # Simulate CLI args (some set, some None)
        cli_args = Namespace(
            model=None,  # Will come from YAML
            max_tokens_per_step=200000,  # CLI override
            max_tool_calls_per_step=None,
            temperature=None,
            plan_revision_max_steps=None,
            workflow_file=temp_yaml_files["main_yaml"],
        )

        # Step 1: Load main YAML config
        main_config = load_yaml_config(temp_yaml_files["main_yaml"])

        # Step 2: Apply YAML config as fallback
        apply_yaml_config_fallback(cli_args, main_config)

        # CLI override should be preserved
        assert cli_args.max_tokens_per_step == 200000
        # YAML values should fill None
        assert cli_args.model == "gpt-4o"
        assert cli_args.max_tool_calls_per_step == 15

        # Step 3: Create EffectiveArgs for main workflow
        main_effective = EffectiveArgs.from_args(cli_args)

        # Step 4: Simulate submodule with custom config
        parser = YAMLTaskParser()
        sub_data = parser.load_task(temp_yaml_files["submodule_with_config"])
        sub_config = sub_data.get("config", {})

        sub_effective = main_effective.with_yaml_config(sub_config)

        # Submodule should have its own model
        assert sub_effective.model == "gpt-4o-mini"
        # But inherit CLI override for tokens
        assert sub_effective.max_tokens_per_step == 50000  # Submodule config

        # Main workflow should be unchanged
        assert main_effective.model == "gpt-4o"
        assert main_effective.max_tokens_per_step == 200000

    def test_nested_submodule_config_chain(self, sample_args):
        """Test config inheritance through multiple nesting levels."""
        # Main workflow
        main = EffectiveArgs.from_args(sample_args)
        assert main.model == "gpt-4o"

        # Level 1 submodule with custom config
        level1 = main.with_yaml_config({"model": "level1-model"})
        assert level1.model == "level1-model"
        assert main.model == "gpt-4o"  # Unchanged

        # Level 2 submodule inherits from level 1
        level2 = level1.with_yaml_config({})  # No config, inherits
        assert level2.model == "level1-model"

        # Level 3 submodule with new config
        level3 = level2.with_yaml_config({"model": "level3-model"})
        assert level3.model == "level3-model"

        # All previous levels unchanged
        assert main.model == "gpt-4o"
        assert level1.model == "level1-model"
        assert level2.model == "level1-model"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
