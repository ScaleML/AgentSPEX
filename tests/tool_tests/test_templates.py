"""
Unit tests for parsing/templates.py

Tests the template variable expansion functionality including:
- Basic variable substitution
- Dot notation for dict access (single and multi-level)
- JSON / code-block string auto-parsing during dot resolution
- Missing variable handling
- Non-string input handling
"""

import pytest

from harness.parsing.templates import expand_template_variables


class TestExpandTemplateVariables:
    """Tests for the expand_template_variables function"""

    # Basic substitution tests
    def test_single_variable(self):
        """Test single variable substitution"""
        result = expand_template_variables("Hello, {{name}}!", {"name": "World"})
        assert result == "Hello, World!"

    def test_multiple_variables(self):
        """Test multiple variable substitution"""
        template = "{{greeting}}, {{name}}! Your score is {{score}}."
        context = {"greeting": "Hello", "name": "Alice", "score": 100}
        result = expand_template_variables(template, context)
        assert result == "Hello, Alice! Your score is 100."

    def test_same_variable_multiple_times(self):
        """Test same variable used multiple times"""
        template = "{{x}} + {{x}} = {{result}}"
        context = {"x": 5, "result": 10}
        result = expand_template_variables(template, context)
        assert result == "5 + 5 = 10"

    def test_no_variables(self):
        """Test text without variables"""
        template = "Plain text without variables"
        result = expand_template_variables(template, {})
        assert result == "Plain text without variables"

    # Missing variable tests
    def test_missing_variable_kept(self):
        """Test that missing variables are kept as-is"""
        template = "Hello, {{name}}!"
        result = expand_template_variables(template, {})
        assert result == "Hello, {{name}}!"

    def test_partial_missing_variables(self):
        """Test mix of present and missing variables"""
        template = "{{greeting}}, {{name}}!"
        context = {"greeting": "Hello"}
        result = expand_template_variables(template, context)
        assert result == "Hello, {{name}}!"

    # Dot notation tests (single level)
    def test_dict_access_dot_notation(self):
        """Test single-level dict access with dot notation"""
        template = "User: {{user.name}}, Age: {{user.age}}"
        context = {"user": {"name": "Alice", "age": 30}}
        result = expand_template_variables(template, context)
        assert result == "User: Alice, Age: 30"

    def test_dict_missing_key(self):
        """Test dot notation with missing dict key"""
        template = "Value: {{data.missing}}"
        context = {"data": {"other": "value"}}
        result = expand_template_variables(template, context)
        assert result == "Value: {{data.missing}}"

    def test_dict_missing_dict(self):
        """Test dot notation with missing dict"""
        template = "Value: {{missing.key}}"
        result = expand_template_variables(template, {})
        assert result == "Value: {{missing.key}}"

    def test_dict_non_dict_value(self):
        """Test dot notation when value is a non-parseable string"""
        template = "Value: {{data.key}}"
        context = {"data": "not a dict"}
        result = expand_template_variables(template, context)
        assert result == "Value: {{data.key}}"

    # Type conversion tests
    def test_integer_value(self):
        result = expand_template_variables("Count: {{count}}", {"count": 42})
        assert result == "Count: 42"

    def test_float_value(self):
        result = expand_template_variables("Score: {{score}}", {"score": 3.14})
        assert result == "Score: 3.14"

    def test_boolean_value(self):
        result = expand_template_variables("Active: {{active}}", {"active": True})
        assert result == "Active: True"

    def test_list_value(self):
        result = expand_template_variables("Items: {{items}}", {"items": [1, 2, 3]})
        assert result == "Items: [1, 2, 3]"

    def test_none_value(self):
        result = expand_template_variables("Value: {{value}}", {"value": None})
        assert result == "Value: None"

    # Non-string input tests
    def test_non_string_input_converted(self):
        result = expand_template_variables(123, {})
        assert result == "123"

    def test_none_input(self):
        result = expand_template_variables(None, {})
        assert result == "None"

    # Edge cases
    def test_empty_template(self):
        result = expand_template_variables("", {})
        assert result == ""

    def test_whitespace_in_variable_name(self):
        template = "{{ name }}"
        context = {" name ": "value"}
        result = expand_template_variables(template, context)
        assert result == "value"

    def test_adjacent_variables(self):
        template = "{{a}}{{b}}{{c}}"
        context = {"a": "1", "b": "2", "c": "3"}
        result = expand_template_variables(template, context)
        assert result == "123"

    def test_curly_braces_not_variables(self):
        template = "JSON: {key: value}"
        result = expand_template_variables(template, {"key": "other"})
        assert result == "JSON: {key: value}"

    def test_triple_curly_braces(self):
        template = "{{{name}}}"
        context = {"name": "value"}
        result = expand_template_variables(template, context)
        assert result == "{{{name}}}"

    def test_multiline_template(self):
        template = """Line 1: {{first}}
Line 2: {{second}}
Line 3: {{third}}"""
        context = {"first": "a", "second": "b", "third": "c"}
        result = expand_template_variables(template, context)
        expected = """Line 1: a
Line 2: b
Line 3: c"""
        assert result == expected

    def test_special_characters_in_value(self):
        context = {"value": "<script>alert('xss')</script>"}
        result = expand_template_variables("HTML: {{value}}", context)
        assert result == "HTML: <script>alert('xss')</script>"

    def test_newline_in_value(self):
        context = {"text": "line1\nline2\nline3"}
        result = expand_template_variables("Text:\n{{text}}", context)
        assert result == "Text:\nline1\nline2\nline3"


# ---------------------------------------------------------------------------
# Multi-level dot notation (NEW)
# ---------------------------------------------------------------------------
class TestMultiLevelDotNotation:
    """Tests for multi-level dotted-path template variable expansion"""

    def test_two_level(self):
        template = "Host: {{config.db.host}}"
        context = {"config": {"db": {"host": "localhost"}}}
        assert expand_template_variables(template, context) == "Host: localhost"

    def test_three_level(self):
        template = "{{a.b.c.d}}"
        context = {"a": {"b": {"c": {"d": "deep"}}}}
        assert expand_template_variables(template, context) == "deep"

    def test_mixed_depths_in_same_template(self):
        template = "{{user.name}} at {{config.db.host}}:{{config.db.port}}"
        context = {
            "user": {"name": "Alice"},
            "config": {"db": {"host": "localhost", "port": 5432}},
        }
        result = expand_template_variables(template, context)
        assert result == "Alice at localhost:5432"

    def test_multi_level_missing_intermediate(self):
        """Missing intermediate key keeps original template"""
        template = "{{a.b.missing.d}}"
        context = {"a": {"b": {"c": 1}}}
        assert expand_template_variables(template, context) == "{{a.b.missing.d}}"

    def test_multi_level_missing_leaf(self):
        template = "{{a.b.missing}}"
        context = {"a": {"b": {"c": 1}}}
        assert expand_template_variables(template, context) == "{{a.b.missing}}"

    def test_multi_level_missing_root(self):
        template = "{{missing.b.c}}"
        assert expand_template_variables(template, {}) == "{{missing.b.c}}"

    def test_multi_level_resolves_to_dict(self):
        """When dotted path resolves to a dict, it's stringified"""
        template = "Nested: {{a.b}}"
        context = {"a": {"b": {"c": 1, "d": 2}}}
        result = expand_template_variables(template, context)
        assert result == "Nested: {'c': 1, 'd': 2}"

    def test_multi_level_resolves_to_list(self):
        template = "Items: {{data.items}}"
        context = {"data": {"items": [1, 2, 3]}}
        assert expand_template_variables(template, context) == "Items: [1, 2, 3]"

    def test_multi_level_resolves_to_bool(self):
        template = "Ready: {{status.ready}}"
        context = {"status": {"ready": True}}
        assert expand_template_variables(template, context) == "Ready: True"

    def test_multi_level_resolves_to_none(self):
        template = "Val: {{result.value}}"
        context = {"result": {"value": None}}
        assert expand_template_variables(template, context) == "Val: None"

    def test_single_level_still_works(self):
        """No regression for single-level dot notation"""
        template = "{{user.name}}"
        context = {"user": {"name": "Alice"}}
        assert expand_template_variables(template, context) == "Alice"


# ---------------------------------------------------------------------------
# JSON / code-block string auto-parsing in templates (NEW)
# ---------------------------------------------------------------------------
class TestTemplatesWithJsonStringParsing:
    """Tests for template expansion when context values are JSON strings"""

    def test_plain_json_string(self):
        context = {"data": '{"status": "DONE", "score": 0.8}'}
        assert expand_template_variables("{{data.status}}", context) == "DONE"
        assert expand_template_variables("{{data.score}}", context) == "0.8"

    def test_json_code_block_string(self):
        """The exact real-world scenario: LLM outputs JSON in code block"""
        llm_output = (
            "```json\n"
            "{\n"
            '  "research_needed": "yes",\n'
            '  "reason": "Requires factual information",\n'
            '  "search_queries": ["ml in manufacturing"]\n'
            "}\n"
            "```"
        )
        context = {"research_plan": llm_output}
        result = expand_template_variables("{{research_plan.research_needed}}", context)
        assert result == "yes"

    def test_python_dict_literal_string(self):
        context = {"result": "{'ready': True, 'count': 42}"}
        assert expand_template_variables("{{result.ready}}", context) == "True"
        assert expand_template_variables("{{result.count}}", context) == "42"

    def test_mixed_native_dict_and_json_string(self):
        """First level native dict, second level JSON string"""
        context = {"outer": {"inner": '{"key": "value"}'}}
        assert expand_template_variables("{{outer.inner.key}}", context) == "value"

    def test_non_parseable_string_keeps_original(self):
        context = {"msg": "just plain text"}
        template = "{{msg.something}}"
        assert expand_template_variables(template, context) == "{{msg.something}}"

    def test_code_block_with_surrounding_text(self):
        text = 'Here is the result:\n```json\n{"key": "val"}\n```\nDone.'
        context = {"resp": text}
        assert expand_template_variables("{{resp.key}}", context) == "val"

    def test_json_string_in_condition_like_template(self):
        """Simulate the template-expansion step before evaluate_condition"""
        context = {
            "research_plan": '```json\n{"research_needed": "yes"}\n```',
        }
        raw = "{{research_plan.research_needed}} == yes"
        expanded = expand_template_variables(raw, context)
        assert expanded == "yes == yes"

    def test_compound_template_with_json_strings(self):
        """Simulate compound condition template expansion"""
        context = {
            "A": '{"b": "yes"}',
            "C": '{"d": "True"}',
        }
        raw = "{{A.b}} == yes and {{C.d}} == True"
        expanded = expand_template_variables(raw, context)
        assert expanded == "yes == yes and True == True"

    def test_mixed_template_native_and_json(self):
        """Mix of {{}} templates, native dicts, and JSON strings"""
        context = {
            "native": {"key": "native_val"},
            "json_str": '{"key": "json_val"}',
        }
        template = "{{native.key}} and {{json_str.key}}"
        result = expand_template_variables(template, context)
        assert result == "native_val and json_val"

    def test_nested_json_strings(self):
        """JSON string containing another JSON string value"""
        context = {"l1": '{"l2": "{\\"deep\\": \\"found\\"}"}'}
        assert expand_template_variables("{{l1.l2.deep}}", context) == "found"

    def test_workflow_values_expression(self):
        """The .values() pattern used in real workflows stays intact after expansion"""
        context = {"all_citations": {"k1": ["a"], "k2": ["b"]}}
        template = "list( {{all_citations}}.values() )"
        result = expand_template_variables(template, context)
        # The whole dict is stringified; .values() stays as literal text for eval()
        assert ".values()" in result
        assert "k1" in result
