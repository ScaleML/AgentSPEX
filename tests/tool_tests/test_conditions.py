"""
Unit tests for parsing/conditions.py

Tests the condition evaluation functionality including:
- Numeric comparisons (==, !=, <, >, <=, >=)
- String comparisons
- Variable resolution from context
- Truthiness checks
- Dotted-path nested dict access (A.B.C)
- JSON / code-block string auto-parsing
- Compound conditions (and / or)
"""

import pytest

from harness.parsing.conditions import (_SENTINEL, _try_parse_dict,
                                        evaluate_condition,
                                        resolve_dotted_path, resolve_operand)


# ---------------------------------------------------------------------------
# resolve_operand (original tests)
# ---------------------------------------------------------------------------
class TestResolveOperand:
    """Tests for the resolve_operand function"""

    def test_quoted_double_string(self):
        """Test resolving double-quoted strings"""
        result = resolve_operand('"hello world"', {})
        assert result == "hello world"

    def test_quoted_single_string(self):
        """Test resolving single-quoted strings"""
        result = resolve_operand("'hello world'", {})
        assert result == "hello world"

    def test_integer(self):
        """Test resolving integer values"""
        result = resolve_operand("42", {})
        assert result == 42
        assert isinstance(result, int)

    def test_negative_integer(self):
        """Test resolving negative integer values"""
        result = resolve_operand("-10", {})
        assert result == -10
        assert isinstance(result, int)

    def test_float(self):
        """Test resolving float values"""
        result = resolve_operand("3.14", {})
        assert result == 3.14
        assert isinstance(result, float)

    def test_negative_float(self):
        """Test resolving negative float values"""
        result = resolve_operand("-2.5", {})
        assert result == -2.5
        assert isinstance(result, float)

    def test_variable_from_context(self):
        """Test resolving variable from context"""
        context = {"my_var": "value123"}
        result = resolve_operand("my_var", context)
        assert result == "value123"

    def test_variable_not_in_context(self):
        """Test resolving variable not in context returns original"""
        result = resolve_operand("unknown_var", {})
        assert result == "unknown_var"

    def test_whitespace_trimmed(self):
        """Test that whitespace is trimmed from operands"""
        result = resolve_operand("  42  ", {})
        assert result == 42


class TestResolveOperandDottedPath:
    """Tests for resolve_operand with dotted-path nested dict access"""

    def test_single_level(self):
        context = {"user": {"name": "Alice"}}
        assert resolve_operand("user.name", context) == "Alice"

    def test_two_level(self):
        context = {"config": {"db": {"host": "localhost"}}}
        assert resolve_operand("config.db.host", context) == "localhost"

    def test_three_level(self):
        context = {"a": {"b": {"c": {"d": 42}}}}
        assert resolve_operand("a.b.c.d", context) == 42

    def test_dotted_path_not_found_falls_through(self):
        """If dotted path can't resolve, fall through to float/context logic"""
        # "3.14" starts with a digit → not treated as dotted path → parsed as float
        assert resolve_operand("3.14", {}) == 3.14

    def test_dotted_path_missing_key(self):
        """Missing intermediate key returns operand string as-is"""
        context = {"a": {"x": 1}}
        result = resolve_operand("a.b.c", context)
        # Falls through to float parse (fails), then context.get returns original
        assert result == "a.b.c"

    def test_dotted_path_with_underscore_prefix(self):
        context = {"_private": {"key": "secret"}}
        assert resolve_operand("_private.key", context) == "secret"

    def test_dotted_path_resolves_to_numeric(self):
        context = {"metrics": {"score": 0.95}}
        assert resolve_operand("metrics.score", context) == 0.95

    def test_dotted_path_resolves_to_list(self):
        context = {"data": {"items": [1, 2, 3]}}
        assert resolve_operand("data.items", context) == [1, 2, 3]

    def test_dotted_path_resolves_to_none(self):
        context = {"result": {"value": None}}
        assert resolve_operand("result.value", context) is None

    def test_dotted_path_resolves_to_bool(self):
        context = {"flags": {"enabled": True}}
        assert resolve_operand("flags.enabled", context) is True


# ---------------------------------------------------------------------------
# resolve_dotted_path
# ---------------------------------------------------------------------------
class TestResolveDottedPath:
    """Tests for the resolve_dotted_path helper"""

    def test_single_segment(self):
        assert resolve_dotted_path("key", {"key": "val"}) == "val"

    def test_two_segments(self):
        assert resolve_dotted_path("a.b", {"a": {"b": 1}}) == 1

    def test_three_segments(self):
        ctx = {"a": {"b": {"c": "deep"}}}
        assert resolve_dotted_path("a.b.c", ctx) == "deep"

    def test_missing_root(self):
        assert resolve_dotted_path("missing.key", {}) is _SENTINEL

    def test_missing_intermediate(self):
        assert resolve_dotted_path("a.missing.c", {"a": {"b": 1}}) is _SENTINEL

    def test_missing_leaf(self):
        assert resolve_dotted_path("a.b.missing", {"a": {"b": {"c": 1}}}) is _SENTINEL

    def test_non_dict_intermediate(self):
        """If an intermediate value is a non-parseable string, return _SENTINEL"""
        assert resolve_dotted_path("a.b.c", {"a": {"b": "plain string"}}) is _SENTINEL

    def test_resolves_to_various_types(self):
        ctx = {
            "d": {
                "int": 42,
                "float": 3.14,
                "bool": False,
                "none": None,
                "list": [1, 2],
                "dict": {"nested": True},
            }
        }
        assert resolve_dotted_path("d.int", ctx) == 42
        assert resolve_dotted_path("d.float", ctx) == 3.14
        assert resolve_dotted_path("d.bool", ctx) is False
        assert resolve_dotted_path("d.none", ctx) is None
        assert resolve_dotted_path("d.list", ctx) == [1, 2]
        assert resolve_dotted_path("d.dict", ctx) == {"nested": True}


# ---------------------------------------------------------------------------
# _try_parse_dict  &  resolve_dotted_path with string auto-parsing
# ---------------------------------------------------------------------------
class TestTryParseDict:
    """Tests for the _try_parse_dict helper"""

    def test_plain_json(self):
        result = _try_parse_dict('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_whitespace(self):
        result = _try_parse_dict('  \n  {"key": "value"}  \n  ')
        assert result == {"key": "value"}

    def test_json_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        assert _try_parse_dict(text) == {"key": "value"}

    def test_code_block_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        assert _try_parse_dict(text) == {"key": "value"}

    def test_python_dict_literal(self):
        result = _try_parse_dict("{'key': 'value', 'flag': True}")
        assert result == {"key": "value", "flag": True}

    def test_python_literal_code_block(self):
        text = "```python\n{'a': 1, 'b': 2}\n```"
        assert _try_parse_dict(text) == {"a": 1, "b": 2}

    def test_non_dict_json_returns_sentinel(self):
        """JSON arrays or scalars are not dicts"""
        assert _try_parse_dict("[1, 2, 3]") is _SENTINEL
        assert _try_parse_dict('"just a string"') is _SENTINEL

    def test_plain_string_returns_sentinel(self):
        assert _try_parse_dict("hello world") is _SENTINEL

    def test_empty_string_returns_sentinel(self):
        assert _try_parse_dict("") is _SENTINEL

    def test_multiline_json_code_block(self):
        """Realistic LLM output with multiline JSON"""
        text = (
            "```json\n"
            "{\n"
            '  "research_needed": "yes",\n'
            '  "reason": "Requires factual information",\n'
            '  "search_queries": ["ml in manufacturing"]\n'
            "}\n"
            "```"
        )
        result = _try_parse_dict(text)
        assert result["research_needed"] == "yes"
        assert isinstance(result["search_queries"], list)


class TestResolveDottedPathWithStringParsing:
    """Tests for resolve_dotted_path when intermediate values are JSON strings"""

    def test_json_string_value(self):
        context = {"data": '{"status": "DONE", "score": 0.8}'}
        assert resolve_dotted_path("data.status", context) == "DONE"
        assert resolve_dotted_path("data.score", context) == 0.8

    def test_json_code_block_value(self):
        """The exact scenario from the user's bug report"""
        llm_output = (
            "```json\n"
            "{\n"
            '  "research_needed": "yes",\n'
            '  "reason": "The task requires specific factual information"\n'
            "}\n"
            "```"
        )
        context = {"research_plan": llm_output}
        assert resolve_dotted_path("research_plan.research_needed", context) == "yes"
        assert (
            resolve_dotted_path("research_plan.reason", context)
            == "The task requires specific factual information"
        )

    def test_python_literal_string_value(self):
        context = {"result": "{'ready': True, 'count': 42}"}
        assert resolve_dotted_path("result.ready", context) is True
        assert resolve_dotted_path("result.count", context) == 42

    def test_mixed_native_dict_and_json_string(self):
        """First level is native dict, second level is JSON string"""
        context = {"outer": {"inner": '{"key": "value"}'}}
        assert resolve_dotted_path("outer.inner.key", context) == "value"

    def test_nested_json_strings(self):
        """Both levels are JSON strings"""
        context = {"level1": '{"level2": "{\\"deep\\": \\"found\\"}"}'}
        assert resolve_dotted_path("level1.level2", context) == '{"deep": "found"}'
        assert resolve_dotted_path("level1.level2.deep", context) == "found"

    def test_non_dict_string_stops_traversal(self):
        context = {"msg": "just a plain string"}
        assert resolve_dotted_path("msg.anything", context) is _SENTINEL

    def test_native_dict_still_works(self):
        """Ensure no regression for native dicts"""
        context = {"plan": {"research_needed": "yes"}}
        assert resolve_dotted_path("plan.research_needed", context) == "yes"

    def test_code_block_with_extra_text_around(self):
        """Code block with surrounding commentary"""
        text = 'Here is the result:\n```json\n{"key": "val"}\n```\nDone.'
        context = {"resp": text}
        assert resolve_dotted_path("resp.key", context) == "val"


# ---------------------------------------------------------------------------
# evaluate_condition (original tests)
# ---------------------------------------------------------------------------
class TestEvaluateCondition:
    """Tests for the evaluate_condition function"""

    # Numeric comparison tests
    def test_numeric_equals(self):
        assert evaluate_condition("x == 5", {"x": 5}) is True
        assert evaluate_condition("x == 5", {"x": 6}) is False

    def test_numeric_not_equals(self):
        assert evaluate_condition("x != 5", {"x": 6}) is True
        assert evaluate_condition("x != 5", {"x": 5}) is False

    def test_numeric_less_than(self):
        assert evaluate_condition("x < 10", {"x": 5}) is True
        assert evaluate_condition("x < 10", {"x": 10}) is False
        assert evaluate_condition("x < 10", {"x": 15}) is False

    def test_numeric_greater_than(self):
        assert evaluate_condition("x > 10", {"x": 15}) is True
        assert evaluate_condition("x > 10", {"x": 10}) is False
        assert evaluate_condition("x > 10", {"x": 5}) is False

    def test_numeric_less_than_or_equal(self):
        assert evaluate_condition("x <= 10", {"x": 5}) is True
        assert evaluate_condition("x <= 10", {"x": 10}) is True
        assert evaluate_condition("x <= 10", {"x": 15}) is False

    def test_numeric_greater_than_or_equal(self):
        assert evaluate_condition("x >= 10", {"x": 15}) is True
        assert evaluate_condition("x >= 10", {"x": 10}) is True
        assert evaluate_condition("x >= 10", {"x": 5}) is False

    def test_float_comparison(self):
        assert evaluate_condition("score >= 0.5", {"score": 0.75}) is True
        assert evaluate_condition("score >= 0.5", {"score": 0.3}) is False
        assert evaluate_condition("score == 0.5", {"score": 0.5}) is True

    # String comparison tests
    def test_string_equals(self):
        assert evaluate_condition("status == DONE", {"status": "DONE"}) is True
        assert evaluate_condition("status == DONE", {"status": "PENDING"}) is False

    def test_string_not_equals(self):
        assert evaluate_condition("status != FAILED", {"status": "SUCCESS"}) is True
        assert evaluate_condition("status != FAILED", {"status": "FAILED"}) is False

    def test_quoted_string_comparison(self):
        assert evaluate_condition('name == "test"', {"name": "test"}) is True
        assert evaluate_condition("name == 'test'", {"name": "test"}) is True

    def test_string_lexicographic_comparison(self):
        assert evaluate_condition("a < b", {"a": "apple", "b": "banana"}) is True
        assert evaluate_condition("a > b", {"a": "zebra", "b": "apple"}) is True

    # Variable comparison tests
    def test_variable_to_variable_comparison(self):
        context = {"var1": 10, "var2": 10}
        assert evaluate_condition("var1 == var2", context) is True

        context = {"var1": 10, "var2": 20}
        assert evaluate_condition("var1 == var2", context) is False

    def test_variable_to_literal_comparison(self):
        assert evaluate_condition("iteration < 10", {"iteration": 5}) is True
        assert evaluate_condition("count >= 100", {"count": 150}) is True

    # Truthiness tests
    def test_truthiness_true_value(self):
        assert evaluate_condition("has_data", {"has_data": True}) is True
        assert evaluate_condition("has_data", {"has_data": "yes"}) is True
        assert evaluate_condition("has_data", {"has_data": 1}) is True
        assert evaluate_condition("has_data", {"has_data": [1, 2, 3]}) is True

    def test_truthiness_false_value(self):
        assert evaluate_condition("has_data", {"has_data": False}) is False
        assert evaluate_condition("has_data", {"has_data": ""}) is False
        assert evaluate_condition("has_data", {"has_data": 0}) is False
        assert evaluate_condition("has_data", {"has_data": []}) is False
        assert evaluate_condition("has_data", {"has_data": None}) is False

    def test_truthiness_variable_not_in_context(self):
        assert evaluate_condition("missing_var", {}) is False

    # Edge cases
    def test_empty_condition(self):
        assert evaluate_condition("", {}) is False
        assert evaluate_condition("   ", {}) is False

    def test_none_condition(self):
        assert evaluate_condition(None, {}) is False

    def test_whitespace_handling(self):
        assert evaluate_condition("  x == 5  ", {"x": 5}) is True
        assert evaluate_condition("x  ==  5", {"x": 5}) is True

    def test_underscore_variable_names(self):
        assert evaluate_condition("my_var == 10", {"my_var": 10}) is True
        assert evaluate_condition("_private == 1", {"_private": 1}) is True

    def test_numeric_string_conversion(self):
        assert evaluate_condition("x == 5", {"x": "5"}) is True
        assert evaluate_condition("x > 3", {"x": "5"}) is True

    def test_complex_variable_values(self):
        context = {"status": "COMPLETE"}
        assert evaluate_condition("status == COMPLETE", context) is True


class TestConditionPatternMatching:
    """Tests for condition pattern matching edge cases"""

    def test_invalid_operator(self):
        result = evaluate_condition("x === 5", {"x": 5})
        assert result is False

    def test_malformed_condition(self):
        assert evaluate_condition("== 5", {}) is False
        assert evaluate_condition("5 ==", {}) is False

    def test_operators_in_variable_names(self):
        context = {"value1": 10, "value2": 10}
        assert evaluate_condition("value1 == value2", context) is True


# ---------------------------------------------------------------------------
# Dotted-path conditions
# ---------------------------------------------------------------------------
class TestDottedPathConditions:
    """Tests for conditions using dotted-path operands"""

    def test_single_level_dotted_equals(self):
        ctx = {"result": {"status": "DONE"}}
        assert evaluate_condition("result.status == DONE", ctx) is True
        assert evaluate_condition("result.status == FAILED", ctx) is False

    def test_two_level_dotted_equals(self):
        ctx = {"config": {"db": {"host": "localhost"}}}
        assert evaluate_condition("config.db.host == localhost", ctx) is True

    def test_three_level_dotted(self):
        ctx = {"a": {"b": {"c": {"d": "found"}}}}
        assert evaluate_condition("a.b.c.d == found", ctx) is True

    def test_dotted_numeric_comparison(self):
        ctx = {"metrics": {"score": 0.85}}
        assert evaluate_condition("metrics.score >= 0.5", ctx) is True
        assert evaluate_condition("metrics.score < 0.5", ctx) is False

    def test_dotted_not_equals(self):
        ctx = {"job": {"state": "running"}}
        assert evaluate_condition("job.state != done", ctx) is True

    def test_dotted_both_sides(self):
        """Both operands are dotted paths"""
        ctx = {"left": {"val": 10}, "right": {"val": 10}}
        assert evaluate_condition("left.val == right.val", ctx) is True
        ctx["right"]["val"] = 20
        assert evaluate_condition("left.val == right.val", ctx) is False

    def test_dotted_vs_literal(self):
        ctx = {"result": {"count": 5}}
        assert evaluate_condition("result.count > 3", ctx) is True
        assert evaluate_condition("result.count <= 5", ctx) is True

    def test_dotted_with_quoted_string(self):
        ctx = {"info": {"label": "hello world"}}
        assert evaluate_condition('info.label == "hello world"', ctx) is True

    def test_dotted_missing_path_returns_false(self):
        ctx = {"a": {"b": 1}}
        assert evaluate_condition("a.c == 1", ctx) is False

    def test_dotted_truthiness(self):
        ctx = {"result": {"ready": True}}
        assert evaluate_condition("result.ready", ctx) is True
        ctx = {"result": {"ready": False}}
        assert evaluate_condition("result.ready", ctx) is False
        ctx = {"result": {"ready": ""}}
        assert evaluate_condition("result.ready", ctx) is False

    def test_dotted_truthiness_missing(self):
        assert evaluate_condition("missing.path", {}) is False

    def test_dotted_truthiness_three_level(self):
        ctx = {"a": {"b": {"c": [1, 2]}}}
        assert evaluate_condition("a.b.c", ctx) is True
        ctx["a"]["b"]["c"] = []
        assert evaluate_condition("a.b.c", ctx) is False


# ---------------------------------------------------------------------------
# Conditions with JSON-string auto-parsing
# ---------------------------------------------------------------------------
class TestConditionsWithJsonStringParsing:
    """Tests for conditions where context values are JSON/code-block strings"""

    def test_json_string_condition(self):
        ctx = {"data": '{"status": "DONE"}'}
        assert evaluate_condition("data.status == DONE", ctx) is True

    def test_code_block_json_condition(self):
        """The exact real-world scenario from the user"""
        llm_output = (
            "```json\n"
            "{\n"
            '  "research_needed": "yes",\n'
            '  "reason": "The task requires factual information"\n'
            "}\n"
            "```"
        )
        ctx = {"research_plan": llm_output}
        assert evaluate_condition("research_plan.research_needed == yes", ctx) is True
        assert evaluate_condition("research_plan.research_needed == no", ctx) is False

    def test_python_literal_string_condition(self):
        ctx = {"result": "{'status': 'DONE', 'count': 10}"}
        assert evaluate_condition("result.status == DONE", ctx) is True
        assert evaluate_condition("result.count >= 5", ctx) is True

    def test_mixed_native_and_json_condition(self):
        ctx = {"outer": {"inner": '{"val": 42}'}}
        assert evaluate_condition("outer.inner.val == 42", ctx) is True

    def test_json_string_truthiness(self):
        ctx = {"plan": '{"ready": true}'}
        assert evaluate_condition("plan.ready", ctx) is True
        ctx = {"plan": '{"ready": false}'}
        assert evaluate_condition("plan.ready", ctx) is False

    def test_non_parseable_string_returns_false(self):
        ctx = {"msg": "just a plain string"}
        assert evaluate_condition("msg.key == anything", ctx) is False


# ---------------------------------------------------------------------------
# Compound conditions (and / or)
# ---------------------------------------------------------------------------
class TestCompoundConditions:
    """Tests for compound conditions with 'and' / 'or' connectives"""

    # --- and ---
    def test_and_both_true(self):
        ctx = {"status": "DONE", "score": 0.8}
        assert evaluate_condition("status == DONE and score >= 0.5", ctx) is True

    def test_and_first_false(self):
        ctx = {"status": "PENDING", "score": 0.8}
        assert evaluate_condition("status == DONE and score >= 0.5", ctx) is False

    def test_and_second_false(self):
        ctx = {"status": "DONE", "score": 0.3}
        assert evaluate_condition("status == DONE and score >= 0.5", ctx) is False

    def test_and_both_false(self):
        ctx = {"status": "PENDING", "score": 0.3}
        assert evaluate_condition("status == DONE and score >= 0.5", ctx) is False

    def test_triple_and(self):
        ctx = {"a": 1, "b": 2, "c": 3}
        assert evaluate_condition("a == 1 and b == 2 and c == 3", ctx) is True
        assert evaluate_condition("a == 1 and b == 99 and c == 3", ctx) is False

    # --- or ---
    def test_or_both_true(self):
        ctx = {"mode": "fast"}
        assert evaluate_condition("mode == fast or mode == turbo", ctx) is True

    def test_or_first_true(self):
        ctx = {"mode": "fast"}
        assert evaluate_condition("mode == fast or mode == slow", ctx) is True

    def test_or_second_true(self):
        ctx = {"mode": "turbo"}
        assert evaluate_condition("mode == fast or mode == turbo", ctx) is True

    def test_or_both_false(self):
        ctx = {"mode": "normal"}
        assert evaluate_condition("mode == fast or mode == turbo", ctx) is False

    def test_triple_or(self):
        ctx = {"x": 3}
        assert evaluate_condition("x == 1 or x == 2 or x == 3", ctx) is True
        assert evaluate_condition("x == 1 or x == 2 or x == 4", ctx) is False

    # --- mixed (and binds tighter than or) ---
    def test_and_or_precedence_and_group_true(self):
        """(a==1 AND b==2) OR (c==99)  →  True OR False → True"""
        ctx = {"a": 1, "b": 2, "c": 3}
        assert evaluate_condition("a == 1 and b == 2 or c == 99", ctx) is True

    def test_and_or_precedence_or_group_true(self):
        """(a==99 AND b==2) OR (c==3)  →  False OR True → True"""
        ctx = {"a": 1, "b": 2, "c": 3}
        assert evaluate_condition("a == 99 and b == 2 or c == 3", ctx) is True

    def test_and_or_precedence_all_false(self):
        """(a==99 AND b==2) OR (c==99)  →  False OR False → False"""
        ctx = {"a": 1, "b": 2, "c": 3}
        assert evaluate_condition("a == 99 and b == 2 or c == 99", ctx) is False

    def test_multiple_or_with_and(self):
        """(a==1 AND b==99) OR (c==99 AND d==4) OR (e==5)  →  F OR F OR T"""
        ctx = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        cond = "a == 1 and b == 99 or c == 99 and d == 4 or e == 5"
        assert evaluate_condition(cond, ctx) is True

    # --- compound with dotted paths ---
    def test_compound_with_dotted_paths(self):
        ctx = {"result": {"status": "DONE"}, "metrics": {"score": 0.9}}
        cond = "result.status == DONE and metrics.score >= 0.5"
        assert evaluate_condition(cond, ctx) is True
        cond = "result.status == DONE and metrics.score >= 0.95"
        assert evaluate_condition(cond, ctx) is False

    def test_compound_or_with_dotted_paths(self):
        ctx = {"job": {"state": "failed"}, "fallback": {"ready": "yes"}}
        cond = "job.state == success or fallback.ready == yes"
        assert evaluate_condition(cond, ctx) is True

    # --- compound with JSON string values ---
    def test_compound_with_json_strings(self):
        ctx = {
            "plan": '{"research_needed": "yes"}',
            "config": '{"mode": "fast"}',
        }
        cond = "plan.research_needed == yes and config.mode == fast"
        assert evaluate_condition(cond, ctx) is True

    # --- edge cases for and / or splitting ---
    def test_variable_name_containing_and(self):
        """'commandline' contains 'and' but should NOT be split"""
        ctx = {"commandline": "yes"}
        assert evaluate_condition("commandline == yes", ctx) is True

    def test_variable_name_containing_or(self):
        """'formula' contains 'or' but should NOT be split"""
        ctx = {"formula": "correct"}
        assert evaluate_condition("formula == correct", ctx) is True

    def test_variable_name_sand(self):
        """'sandbox' contains 'and' substring"""
        ctx = {"sandbox": "active"}
        assert evaluate_condition("sandbox == active", ctx) is True

    def test_variable_name_fork(self):
        """'fork' contains 'or' substring"""
        ctx = {"fork": "yes"}
        assert evaluate_condition("fork == yes", ctx) is True

    def test_and_or_with_extra_whitespace(self):
        ctx = {"a": 1, "b": 2}
        assert evaluate_condition("a == 1   and   b == 2", ctx) is True
        assert evaluate_condition("a == 1   or   b == 99", ctx) is True

    def test_compound_with_truthiness(self):
        ctx = {"has_data": True, "status": "DONE"}
        assert evaluate_condition("has_data and status == DONE", ctx) is True
        ctx["has_data"] = False
        assert evaluate_condition("has_data and status == DONE", ctx) is False

    def test_compound_or_with_truthiness(self):
        ctx = {"has_data": False, "status": "DONE"}
        assert evaluate_condition("has_data or status == DONE", ctx) is True
        ctx["status"] = "PENDING"
        assert evaluate_condition("has_data or status == DONE", ctx) is False
