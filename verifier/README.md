# AgentVerifier — Structural Verifier for AgentSPEX Workflows

AgentVerifier is a Lean 4 library and accompanying Python pipeline that turns
an AgentSPEX workflow into a mechanically checked structural
specification: graph well-formedness, read/write type flow, reachability,
and node-level rules for each of the 13 YAML step types (`step`, `task`,
`for_each`, `if`, `parallel`, `while`, `switch`, `increment`,
`set_variable`, `input`, `call`, `gather`, `return`).

The generated Lean file declares the workflow as a `WorkflowGraph`, emits
per-node diagnostics, and closes with a suite of `native_decide` theorems
covering:

- `writesConsistent` — every node obeys its step type's output rules.
- `readsResolvable` — every variable read is produced by an upstream writer
  or the workflow parameters.
- `edgesValid`, `entryValid`, `exitsValid` — every edge and entry/exit
  references an existing node.
- `exitsReachable`, `noOrphans` — reachability properties from the entry.
- `seqPath_typeChecks` — an existential showing at least one well-typed
  execution order exists.

---

## 1. Prerequisites

- **Lean 4 toolchain (via `elan`).** The `lean-toolchain` file pins
  `leanprover/lean4:v4.20.0`; `elan` will fetch the matching toolchain on
  first build. Install `elan` with:
  ```bash
  curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh
  ```
  Follow the prompt to add `~/.elan/bin` to your `PATH`.

- **Python 3.11+** and **PyYAML**:
  ```bash
  pip install pyyaml
  ```

- **Lean 4 VS Code extension** for interactive theorem checking and inline
  diagnostics.
  
  Search and install `Lean 4` in the VS Code Extensions
  marketplace.

Nothing else is required. The verifier pulls in Mathlib via `lake`
automatically.

---

## 2. Build the verifier

From inside `verifier/`:

```bash
lake update       # first build only — fetches Mathlib v4.20.0 (~5 min)
lake build        # compile AgentVerifier + Main
```

`lake build AgentVerifier` targets only the core library (BaseTypes,
YamlStepType, WorkflowGraphBaiscs, WorkflowGraphUtilies, WorkflowTypeCheck,
WorkflowProperties, Basics) and is the recommended target during
iterative development.

---

## 3. Generate a Lean verification from a YAML workflow

The end-to-end pipeline is a single Python entry point:

```bash
python AgentVerifier/yaml_to_lean.py <workflow.yaml> [-o out.lean] [--prefix name]
```

- If `-o/--output` is omitted, the tool writes `<workflow>.generated.lean`
  next to the input.
- If `--prefix` is omitted, the tool derives a camelCase Lean identifier
  prefix from the workflow's `name` field (e.g. `rlhf_verifiable_rewards_search_2025_2026`
  → `rlhfVerifiableRewardsSearch20252026`).
- Use `--save_ir <path>` to inspect the intermediate `WorkflowIR` as JSON.
- Use `--env_file <path>` one or more times to resolve `${VAR}` references
  in YAML parameters.

Worked example (the shipped test case):

```bash
cd verifier
python AgentVerifier/yaml_to_lean.py \
    TestVerifications/sample_001/task_001.yaml \
    --prefix rlhfSearch
```

Expected output:

```
Workflow : rlhf_verifiable_rewards_search_2025_2026
Prefix   : rlhfSearch
Nodes    : 8 (2 deterministic, 6 LLM/composition)
Edges    : 4
Output   : TestVerifications/sample_001/task_001.generated.lean
```

The file `task_001.generated.lean` is self-contained and importable by any
module that already imports `AgentVerifier.Basics`.

The pipeline steps, in order, are:

1. `yaml_parser.YAMLTaskParser.load_task` expands `${VAR}` env references
   and validates the required `name` / `goal` / `workflow` fields.
2. `WorkflowToLean.parse_task_json` walks the YAML, assigns node IDs,
   builds typed `reads`/`writes` from `{{template}}` references and
   `save_as` annotations, and emits a `WorkflowIR` with sequential,
   branch, loop/loopBack, and fork/join edges.
3. `WorkflowToLean.generate_lean` prints the Lean source: imports,
   per-node `WorkflowNode` definitions, the `WorkflowGraph` literal,
   per-node `#eval` diagnostics, graph-level `#eval`s, and
   `native_decide` theorems.

---

## 4. Interpreting the generated Lean file

### Header banner

The top of the file lists every node with its step type, a `[DET]` /
`[LLM]` tag, and the read/write variable names. `[DET]` nodes are
fully determined by the YAML structure. `[LLM]` nodes involve a
language-model call whose output content is not inspected here — only
their read/write shape is verified.

### Diagnostic `#eval`s

Run `lake env lean TestVerifications/...task_001.generated.lean` (or open
the file in an editor with Lean support) to print per-node and
graph-level diagnostics. Each read is marked `✓` or `✗ UNRESOLVED`, giving
an at-a-glance view of which variables are provided and which are missing.

### Structural theorems

Several `native_decide` theorems assert graph-level properties plus
`seqPath_typeChecks` (existence of a well-typed sequential execution).

A failing `native_decide` on any of these theorems is a **real defect** in
the input YAML — the verifier's job is to surface these. For example, if
`readsResolvable` fails on a workflow that reads a variable written only
inside a parallel branch, the plan depends on a value that is not
structurally guaranteed to be published post-join. Fix the YAML (e.g.,
replace the parallel block with a `gather` of a submodule that returns
the variable, or restructure to write the variable outside the parallel
block), regenerate, and re-check.

---

## 5. Directory layout

```
verifier/
├── AgentVerifier.lean                    -- umbrella import (Basics)
├── AgentVerifier/
│   ├── BaseTypes.lean                    -- TString / TInt / TList / ... and compatibility
│   ├── YamlStepType.lean                 -- ExecType, StepType (13 constructors), TypedVar
│   ├── WorkflowGraphBaiscs.lean          -- WorkflowNode, writesConsistent, WorkflowEdge, WorkflowGraph
│   ├── WorkflowGraphUtilies.lean         -- predecessors, successors, reachability, summaries
│   ├── WorkflowTypeCheck.lean            -- typeCheckSequence, readResolved
│   ├── WorkflowProperties.lean           -- graph-level properties (allWritesConsistent etc.)
│   ├── Basics.lean                       -- umbrella module for the above
│   ├── yaml_parser.py                    -- YAML loader (mirror of src/harness/parsing/yaml_parser.py)
│   ├── WorkflowToLean.py                 -- WorkflowIR + Lean code generator
│   └── yaml_to_lean.py                   -- end-to-end CLI
├── TestVerifications/
│   └── sample_001/
│       ├── task_001.yaml                 -- canonical sample workflow
│       ├── task_001.lean                 -- pre-existing snapshot, kept for reference
│       └── task_001.generated.lean       -- produced by yaml_to_lean.py
├── Main.lean                             -- trivial executable (Hello, AgentVerifier!)
├── lakefile.toml                         -- Lake build spec (Mathlib v4.20.0)
├── lean-toolchain                        -- pin: leanprover/lean4:v4.20.0
└── README.md
```

---

## 6. Adding a new step type

The 13 step types mirror AgentSPEX's
`src/harness/execution/interpreter.py::_STEP_TYPE_KEYS`. To extend:

1. Add a constructor to `StepType` in
   `AgentVerifier/YamlStepType.lean` and update `StepType.execType` and
   `StepType.defaultOutputType` with the new case.
2. Add a branch to `WorkflowNode.writesConsistent` in
   `AgentVerifier/WorkflowGraphBaiscs.lean` describing the output rule.
3. In `AgentVerifier/WorkflowToLean.py`:
   - extend `yaml_key_to_step_type` with the YAML key → StepType mapping;
   - extend `determine_write_type` if the step produces a known type;
   - add a top-level or body-level branch in `parse_task_json` so the
     generator emits the right `NodeIR` and edges.
4. Regenerate `task_001.generated.lean` and re-run `lake build`.
