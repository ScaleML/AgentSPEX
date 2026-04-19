"""
Unit tests for sandbox_vm/tools/app_control/som_annotator.py

Tests:
- _color: determinism, alpha channel, different IDs produce different colors
- annotate_som: filtering logic, sequential IDs, ac_tree format, som_map contents,
                output file is created, handles empty/all-offscreen element lists
"""

import os
import tempfile

import pytest
from PIL import Image

from sandbox_vm.tools.app_control.som_annotator import (TOP_NO_LABEL_ZONE,
                                                        _color, annotate_som)

# ---------------------------------------------------------------------------
# _color
# ---------------------------------------------------------------------------


class TestColor:
    def test_deterministic(self):
        assert _color(1) == _color(1)
        assert _color(42) == _color(42)

    def test_different_ids_differ(self):
        # Highly unlikely same color for different seeds
        assert _color(1) != _color(2)

    def test_alpha_always_255(self):
        for i in range(1, 20):
            assert _color(i)[3] == 255

    def test_returns_four_ints(self):
        c = _color(5)
        assert len(c) == 4
        assert all(isinstance(v, int) for v in c)
        assert all(0 <= v <= 255 for v in c)


# ---------------------------------------------------------------------------
# annotate_som helpers
# ---------------------------------------------------------------------------


def _make_screenshot(width=200, height=150) -> str:
    """Create a temporary PNG screenshot and return its path."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp.name)
    return tmp.name


def _elem(
    left,
    top,
    right,
    bottom,
    label="btn",
    tag="button",
    in_viewport=True,
    occluded=False,
):
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "label": label,
        "tag": tag,
        "inViewport": in_viewport,
        "occluded": occluded,
    }


# ---------------------------------------------------------------------------
# annotate_som
# ---------------------------------------------------------------------------


class TestAnnotateSom:
    def test_creates_output_file(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            elements = [_elem(10, 10, 60, 30, "Search")]
            annotate_som(src, elements, out)
            assert os.path.exists(out)
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_output_is_valid_image(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            annotate_som(src, [_elem(10, 10, 60, 30)], out)
            img = Image.open(out)
            assert img.size == (200, 150)
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_sequential_ids_start_at_1(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            elements = [
                _elem(10, 10, 60, 30, "A"),
                _elem(70, 10, 120, 30, "B"),
                _elem(130, 10, 180, 30, "C"),
            ]
            som_map, ac_tree = annotate_som(src, elements, out)
            assert set(som_map.keys()) == {1, 2, 3}
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_som_map_contains_element_data(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            elements = [_elem(10, 10, 60, 30, label="Login", tag="button")]
            som_map, _ = annotate_som(src, elements, out)
            assert som_map[1]["label"] == "Login"
            assert som_map[1]["tag"] == "button"
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_ac_tree_format(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            elements = [_elem(10, 10, 60, 30, label="Search", tag="input")]
            _, ac_tree = annotate_som(src, elements, out)
            assert len(ac_tree) == 1
            assert ac_tree[0] == "id: 1, text: Search, tag: input"
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_offscreen_elements_excluded(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            elements = [
                _elem(10, 10, 60, 30, label="visible", in_viewport=True),
                _elem(10, 200, 60, 220, label="offscreen", in_viewport=False),
            ]
            som_map, ac_tree = annotate_som(src, elements, out)
            assert len(som_map) == 1
            assert len(ac_tree) == 1
            assert ac_tree[0].startswith("id: 1, text: visible")
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_occluded_elements_excluded(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            elements = [
                _elem(10, 10, 60, 30, label="visible", occluded=False),
                _elem(10, 50, 60, 70, label="hidden", occluded=True),
            ]
            som_map, ac_tree = annotate_som(src, elements, out)
            assert len(som_map) == 1
            assert "visible" in ac_tree[0]
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_fullscreen_element_excluded(self):
        """Elements covering >90% of the screen should be skipped."""
        src = _make_screenshot(200, 150)  # 30000px area
        out = src.replace(".png", "-som.png")
        try:
            elements = [
                _elem(0, 0, 200, 150, label="fullscreen"),  # 100% — skip
                _elem(10, 10, 60, 30, label="small"),  # tiny — keep
            ]
            som_map, _ = annotate_som(src, elements, out)
            assert len(som_map) == 1
            assert som_map[1]["label"] == "small"
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)

    def test_empty_elements_returns_empty(self):
        src = _make_screenshot()
        out = src.replace(".png", "-som.png")
        try:
            som_map, ac_tree = annotate_som(src, [], out)
            assert som_map == {}
            assert ac_tree == []
        finally:
            os.unlink(src)
            if os.path.exists(out):
                os.unlink(out)
