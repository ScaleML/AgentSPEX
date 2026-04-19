#!/usr/bin/env python3
"""End-to-end YAML → Lean 4 structural verification generator.

Usage:
    python yaml_to_lean.py <yaml_path> [-o <lean_path>] [--prefix <name>]

Chains yaml_parser.YAMLTaskParser → WorkflowToLean.parse_task_json →
WorkflowToLean.generate_lean to emit a standalone .lean file.

Default output path is "<yaml_stem>.generated.lean" next to the input YAML.
Default prefix is derived from the workflow's `name` field (camelCased,
stripped to alphanumerics).
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Make sibling modules importable when the script is run directly.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from yaml_parser import YAMLTaskParser
from WorkflowToLean import parse_task_json, generate_lean


def _derive_prefix(name: str) -> str:
    """Convert a workflow name to a valid Lean identifier prefix.

    Examples:
        "rlhf_verifiable_rewards_search_2025_2026" → "rlhfVerifiableRewardsSearch20252026"
        "Quick Start"                              → "quickStart"
        ""                                         → "workflow"
    """
    if not name:
        return "workflow"
    clean = re.sub(r'[^0-9A-Za-z]+', ' ', name).strip()
    if not clean:
        return "workflow"
    parts = clean.split()
    head = parts[0].lower() if parts[0] else "workflow"
    tail = "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    prefix = head + tail
    if not prefix[0].isalpha() and not prefix[0] == "_":
        prefix = "w_" + prefix
    return prefix


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate a Lean 4 structural verification file from a YAML workflow.",
    )
    ap.add_argument("yaml_path", help="Path to the YAML workflow file")
    ap.add_argument("-o", "--output",
                    help="Output .lean path (default: <yaml>.generated.lean next to input)")
    ap.add_argument("--prefix", default=None,
                    help="Lean definition name prefix (default: derived from workflow name)")
    ap.add_argument("--env_file", action="append", default=[],
                    help="Load env vars from file(s) before parsing (repeatable)")
    ap.add_argument("--save_ir", default=None,
                    help="Optional path to save the intermediate WorkflowIR JSON")
    args = ap.parse_args(argv)

    yaml_path = Path(args.yaml_path)
    if not yaml_path.is_file():
        print(f"ERROR: YAML file not found: {yaml_path}", file=sys.stderr)
        return 1

    # Load env files first so ${VAR} references in the YAML can resolve.
    if args.env_file:
        from WorkflowToLean import _load_env_file
        for ef in args.env_file:
            print(f"Loading env: {ef}")
            _load_env_file(ef)

    # 1. Parse YAML → task dict
    parser = YAMLTaskParser()
    task_data = parser.load_task(str(yaml_path))

    # 2. Serialize to a temporary JSON for parse_task_json to consume.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(task_data, tf, ensure_ascii=False)
        tmp_json = tf.name

    try:
        # 3. Build the structural WorkflowIR
        ir = parse_task_json(tmp_json)
    finally:
        try:
            os.unlink(tmp_json)
        except OSError:
            pass

    # 4. Derive prefix
    prefix = args.prefix or _derive_prefix(ir.name)

    # 5. Optionally save IR
    if args.save_ir:
        ir.save_json(args.save_ir)
        print(f"Saved IR: {args.save_ir}")

    # 6. Generate Lean
    lean_src = generate_lean(ir, prefix)

    # 7. Write to output
    out_path = Path(args.output) if args.output else yaml_path.with_suffix(".generated.lean")
    out_path.write_text(lean_src, encoding="utf-8")

    n_det = sum(1 for n in ir.nodes if not n.is_llm_node)
    n_llm = sum(1 for n in ir.nodes if n.is_llm_node)
    print(f"Workflow : {ir.name}")
    print(f"Prefix   : {prefix}")
    print(f"Nodes    : {len(ir.nodes)} ({n_det} deterministic, {n_llm} LLM/composition)")
    print(f"Edges    : {len(ir.edges)}")
    print(f"Output   : {out_path}")
    print()
    print("Next: build with `lake build` from the Verifier/ directory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
