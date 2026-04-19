"""
Unit tests for agent/parsing/computer_use_parser.py

Tests Set-of-Marks action parsing, covering:
- All action types (click, type, hover, scroll, answer, goback, wait)
- Prefix stripping (Action:, Next:, I will, etc.)
- Case insensitivity
- Multi-line text (action on second line after thought)
- Returns None when no action found or unknown mode
"""

import pytest

from harness.parsing.computer_use_parser import parse_computer_use_action


class TestSomParser:
    def test_click(self):
        r = parse_computer_use_action("Click [5]", "set_of_marks")
        assert r == {"key": "click", "args": {"element_number": 5}}

    def test_click_large_number(self):
        r = parse_computer_use_action("Click [42]", "set_of_marks")
        assert r == {"key": "click", "args": {"element_number": 42}}

    def test_type(self):
        r = parse_computer_use_action("Type [2] [Boston]", "set_of_marks")
        assert r == {"key": "type", "args": {"element_number": 2, "text": "Boston"}}

    def test_type_empty_text(self):
        r = parse_computer_use_action("Type [3] []", "set_of_marks")
        assert r == {"key": "type", "args": {"element_number": 3, "text": ""}}

    def test_hover(self):
        r = parse_computer_use_action("Hover [10]", "set_of_marks")
        assert r == {"key": "hover", "args": {"element_number": 10}}

    def test_scroll_element(self):
        r = parse_computer_use_action("Scroll [6] [up]", "set_of_marks")
        assert r == {"key": "scroll", "args": {"target": "6", "direction": "up"}}

    def test_scroll_window(self):
        r = parse_computer_use_action("Scroll [WINDOW] [down]", "set_of_marks")
        assert r == {"key": "scroll", "args": {"target": "WINDOW", "direction": "down"}}

    def test_answer(self):
        r = parse_computer_use_action("ANSWER [Guatemala]", "set_of_marks")
        assert r == {"key": "answer", "args": {"content": "Guatemala"}}

    def test_goback(self):
        r = parse_computer_use_action("GoBack", "set_of_marks")
        assert r == {"key": "goback", "args": {}}

    def test_wait(self):
        r = parse_computer_use_action("Wait", "set_of_marks")
        assert r == {"key": "wait", "args": {}}

    def test_action_prefix_stripped(self):
        r = parse_computer_use_action("Action: Click [3]", "set_of_marks")
        assert r == {"key": "click", "args": {"element_number": 3}}

    def test_next_prefix_stripped(self):
        r = parse_computer_use_action("Next: Click [7]", "set_of_marks")
        assert r == {"key": "click", "args": {"element_number": 7}}

    def test_action_after_thought(self):
        text = "I need to search for the answer.\nThought: The search box is element 2.\nClick [2]"
        r = parse_computer_use_action(text, "set_of_marks")
        assert r == {"key": "click", "args": {"element_number": 2}}

    def test_case_insensitive(self):
        r = parse_computer_use_action("click [5]", "set_of_marks")
        assert r == {"key": "click", "args": {"element_number": 5}}

    def test_returns_none_when_no_action(self):
        r = parse_computer_use_action("I am thinking about what to do.", "set_of_marks")
        assert r is None

    def test_returns_none_on_empty(self):
        r = parse_computer_use_action("", "set_of_marks")
        assert r is None

    def test_returns_none_unknown_mode(self):
        r = parse_computer_use_action("Click [5]", "unknown_mode")
        assert r is None
