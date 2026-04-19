"""
Parsed Task JSON → Lean WorkflowGraph Code Generator.

Pipeline role:
    YAML workflow
      └── yaml_parser.YAMLTaskParser.load_task → parsed_task.json
            └── WorkflowToLean.parse_task_json → WorkflowIR
                  └── WorkflowToLean.generate_lean → .lean source

The emitted Lean file defines a `WorkflowGraph` and a suite of
`native_decide` structural theorems (writesConsistent, readsResolvable,
edgesValid, entryValid, exitsValid, exitsReachable, noOrphans,
seqPath_typeChecks). It depends on `AgentVerifier.Basics` only.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional


# ============================================================================
# 1. IR DATA STRUCTURES
# ============================================================================

# ---------- SubmoduleRef: describes a submodule dependency ----------

@dataclass
class SubmoduleRef:
    """A submodule invoked via call / parallel / gather.

    Records only enough about the submodule to produce human-readable
    diagnostics; the verifier does not inspect its body.
    """
    name: str
    kind: str                         # "parallel" | "call" | "gather"
    output_var: Optional[str] = None
    input_var:  Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "kind": self.kind}
        if self.output_var is not None: d["output_var"] = self.output_var
        if self.input_var  is not None: d["input_var"]  = self.input_var
        return d

    @staticmethod
    def from_dict(d: dict) -> "SubmoduleRef":
        return SubmoduleRef(
            name=d["name"], kind=d.get("kind", "call"),
            output_var=d.get("output_var"),
            input_var=d.get("input_var"),
        )


# ---------- TypedVar ----------

@dataclass
class TypedVar:
    """A typed workflow variable used in reads/writes/parameters."""
    name: str
    base_type: str                      # e.g. "TString", "TList TUnknown"
    value: Optional[object] = None      # populated only for parameters

    def to_lean_typed(self) -> str:
        parts = self.base_type.split()
        lean_type = " .".join(parts)
        return f'⟨"{self.name}", .{lean_type}⟩'

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "base_type": self.base_type}
        if self.value is not None:
            d["value"] = self.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "TypedVar":
        return TypedVar(name=d["name"], base_type=d["base_type"], value=d.get("value"))


# ---------- NodeIR ----------

@dataclass
class NodeIR:
    """A workflow node."""
    id: int
    name: str
    step_type: str                                  # one of the 13 Lean StepType names
    reads: list[TypedVar]
    writes: list[TypedVar]
    instruction: Optional[str] = None
    submodule_ref: Optional[SubmoduleRef] = None

    @property
    def exec_type(self) -> str:
        # Mirror AgentVerifier/YamlStepType.lean::StepType.execType
        deterministic = {
            "forEachLoop", "whileLoop", "conditional", "switchBranch",
            "setVariable", "incrementVariable", "returnValue", "input",
            "parallel", "gather",
        }
        composition = {"call"}
        if self.step_type in deterministic:
            return "deterministic"
        if self.step_type in composition:
            return "composition"
        return "unstructured"

    @property
    def is_llm_node(self) -> bool:
        """True iff the node's behaviour depends on an LLM call."""
        return self.exec_type != "deterministic"

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id, "name": self.name, "step_type": self.step_type,
            "reads": [r.to_dict() for r in self.reads],
            "writes": [w.to_dict() for w in self.writes],
        }
        if self.instruction is not None:
            d["instruction"] = self.instruction
        if self.submodule_ref is not None:
            d["submodule_ref"] = self.submodule_ref.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "NodeIR":
        return NodeIR(
            id=d["id"], name=d["name"], step_type=d["step_type"],
            reads=[TypedVar.from_dict(r) for r in d["reads"]],
            writes=[TypedVar.from_dict(w) for w in d["writes"]],
            instruction=d.get("instruction"),
            submodule_ref=SubmoduleRef.from_dict(d["submodule_ref"]) if d.get("submodule_ref") else None,
        )


# ---------- EdgeIR ----------

@dataclass
class EdgeIR:
    edge_type: str
    from_node: Optional[int] = None
    to_node: Optional[int] = None
    cond_node: Optional[int] = None
    then_entry: Optional[int] = None
    else_entry: Optional[int] = None
    header: Optional[int] = None
    body_entry: Optional[int] = None
    exit_node: Optional[int] = None
    fork_node: Optional[int] = None
    branches: Optional[list[int]] = None
    join_node: Optional[int] = None

    def to_lean(self, prefix: str) -> str:
        if self.edge_type == "seq":
            return f".seqEdge {prefix}_nodeId{self.from_node} {prefix}_nodeId{self.to_node}"
        if self.edge_type == "branch":
            if self.else_entry is None:
                return "-- ERROR: branchEdge with None else_entry"
            return (f".branchEdge {prefix}_nodeId{self.cond_node} "
                    f"{prefix}_nodeId{self.then_entry} {prefix}_nodeId{self.else_entry}")
        if self.edge_type == "loop":
            if self.exit_node is None:
                return "-- ERROR: loopEdge with None exit"
            return (f".loopEdge {prefix}_nodeId{self.header} "
                    f"{prefix}_nodeId{self.body_entry} {prefix}_nodeId{self.exit_node}")
        if self.edge_type == "loopBack":
            return f".loopBackEdge {prefix}_nodeId{self.from_node} {prefix}_nodeId{self.to_node}"
        if self.edge_type == "fork" and self.fork_node is not None and self.branches:
            bl = ", ".join(f"{prefix}_nodeId{b}" for b in self.branches)
            return f".forkEdge {prefix}_nodeId{self.fork_node} [{bl}]"
        if self.edge_type == "join" and self.branches and self.join_node is not None:
            bl = ", ".join(f"{prefix}_nodeId{b}" for b in self.branches)
            return f".joinEdge [{bl}] {prefix}_nodeId{self.join_node}"
        return f"-- UNSUPPORTED edge: {self.edge_type}"

    def to_dict(self) -> dict:
        d: dict = {"edge_type": self.edge_type}
        for k in ("from_node", "to_node", "cond_node", "then_entry",
                  "else_entry", "header", "body_entry", "exit_node",
                  "fork_node", "branches", "join_node"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d

    @staticmethod
    def from_dict(d: dict) -> "EdgeIR":
        return EdgeIR(**{k: d.get(k) for k in (
            "edge_type", "from_node", "to_node", "cond_node", "then_entry",
            "else_entry", "header", "body_entry", "exit_node",
            "fork_node", "branches", "join_node",
        )})


# ---------- WorkflowIR ----------

@dataclass
class WorkflowIR:
    name: str
    goal: str
    parameters: list[TypedVar]
    nodes: list[NodeIR]
    edges: list[EdgeIR]
    entry: int
    exits: list[int]
    submodule_map: Optional[dict[str, SubmoduleRef]] = None

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name, "goal": self.goal,
            "parameters": [p.to_dict() for p in self.parameters],
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "entry": self.entry, "exits": self.exits,
        }
        if self.submodule_map:
            d["submodule_map"] = {k: v.to_dict() for k, v in self.submodule_map.items()}
        return d

    @staticmethod
    def from_dict(d: dict) -> "WorkflowIR":
        return WorkflowIR(
            name=d["name"], goal=d["goal"],
            parameters=[TypedVar.from_dict(p) for p in d["parameters"]],
            nodes=[NodeIR.from_dict(n) for n in d["nodes"]],
            edges=[EdgeIR.from_dict(e) for e in d["edges"]],
            entry=d["entry"], exits=d["exits"],
            submodule_map={k: SubmoduleRef.from_dict(v) for k, v in d["submodule_map"].items()}
                if d.get("submodule_map") else None,
        )

    def save_json(self, path: str, indent: int = 2) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)

    @staticmethod
    def load_json(path: str) -> "WorkflowIR":
        with open(path, "r", encoding="utf-8") as f:
            return WorkflowIR.from_dict(json.load(f))


# ============================================================================
# 2. PARSER
# ============================================================================

def extract_template_vars(text: str) -> list[str]:
    """Extract {{var}} or {{var.field}} references from a string."""
    if not text:
        return []
    return sorted(set(re.findall(r'\{\{(\w+)(?:\.\w+)*\}\}', text)))


def determine_write_type(yaml_key: str) -> str:
    """Map a YAML step-type key to the Lean output BaseType.

    Current YAML workflow language (src/harness/execution/interpreter.py::_STEP_TYPE_KEYS)
    only dispatches 13 step keys. The table below covers exactly those.
    Keys not listed (evaluate / validate / save) are no longer supported.
    synthesize / discover are documented as informal aliases for `task` and
    fall back to the default "TString" write type.
    """
    mapping = {
        "step": "TString", "task": "TString",
        "input": "TString",
        "incrementVariable": "TInt",
        "parallel": "TList TUnknown", "gather": "TList TUnknown",
        "call": "TUnknown",
        "setVariable": "TString",
    }
    return mapping.get(yaml_key, "TString")


def yaml_key_to_step_type(yaml_key: str) -> str:
    """Map a YAML step-type key to the Lean StepType constructor name.

    Historical note: Lean's `step` and `task` meanings were once reversed
    relative to the YAML language (Lean's `task` used to preserve conversation
    history, while YAML's `step` does). The Lean side has been corrected so
    both sides now agree: `step` = stateful, `task` = stateless. This mapping
    is therefore identity for those two keys.

    `synthesize` and `discover` are informal aliases for `task`.
    Keys not listed (evaluate, validate, save) fall through to `step` and
    emit a `[WARN]` in the parser.
    """
    mapping = {
        "step": "step",
        "task": "task",
        "synthesize": "task",
        "discover": "task",
        "set_variable": "setVariable",
        "parallel": "parallel",
        "for_each": "forEachLoop",
        "while": "whileLoop",
        "if": "conditional",
        "switch": "switchBranch",
        "call": "call",
        "gather": "gather",
        "input": "input",
        "return": "returnValue",
        "increment": "incrementVariable",
    }
    return mapping.get(yaml_key, "step")


def _load_env_file(env_path: str) -> None:
    """Load KEY=VALUE pairs from an env file into os.environ."""
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            os.environ[key] = val


def _resolve_env_vars(value):
    """Resolve ${VAR} / ${VAR:-default} references in a parameter value."""
    if not isinstance(value, str):
        return value

    m = re.fullmatch(r'\$\{(\w+)\}', value)
    if m:
        env_name = m.group(1)
        resolved = os.environ.get(env_name)
        if resolved is not None:
            if resolved.lower() in ('true', 'false'):
                return resolved.lower() == 'true'
            try:
                return int(resolved)
            except ValueError:
                pass
            try:
                return float(resolved)
            except ValueError:
                pass
            return resolved
        return value

    def _replace(match):
        env_name = match.group(1)
        return os.environ.get(env_name, match.group(0))

    return re.sub(r'\$\{(\w+)\}', _replace, value)


def _infer_param_type(value) -> str:
    """Infer Lean BaseType from a JSON parameter value."""
    if isinstance(value, bool):
        return "TBool"
    if isinstance(value, int):
        return "TInt"
    if isinstance(value, float):
        return "TFloat"
    if isinstance(value, list):
        return "TList TUnknown"
    if isinstance(value, dict):
        return "TJson"
    return "TString"


def _infer_set_variable_type(raw_value, type_ctx: dict[str, str]) -> str:
    """Infer set_variable output type; keep passthrough type when possible."""
    if isinstance(raw_value, str):
        m = re.fullmatch(r'\s*\{\{(\w+)(?:\.\w+)*\}\}\s*', raw_value)
        if m:
            return type_ctx.get(m.group(1), "TString")
    return _infer_param_type(raw_value)


def _extract_condition_vars(condition: str) -> list[str]:
    """Extract variable names from a condition string."""
    tmpl_vars = extract_template_vars(condition)
    ident = r'([A-Za-z_]\w*)'
    expr_vars = re.findall(rf'{ident}\s*(?:<=|>=|<|>|==|!=)', condition)
    expr_vars += re.findall(rf'(?:<=|>=|<|>|==|!=)\s*{ident}', condition)
    keywords = {'and', 'or', 'true', 'false', 'True', 'False', 'None', 'not'}
    return sorted(set(v for v in (tmpl_vars + expr_vars) if v not in keywords))


def parse_task_json(json_path: str) -> WorkflowIR:
    """Parse parsed_task.json → WorkflowIR."""
    with open(json_path) as f:
        data = json.load(f)

    wf_name = data["name"]
    wf_goal = data.get("goal", "")

    # ---- Parameters ----
    params: list[TypedVar] = []
    raw_params = data.get("parameters", {}) or {}
    for pname, pval in raw_params.items():
        pval = _resolve_env_vars(pval)
        ptype = _infer_param_type(pval)
        params.append(TypedVar(pname, ptype, value=pval))

    type_ctx: dict[str, str] = {p.name: p.base_type for p in params}
    nodes: list[NodeIR] = []
    edges: list[EdgeIR] = []
    nid = 0
    loop_patches: list[dict] = []

    def alloc_id() -> int:
        nonlocal nid
        cur = nid
        nid += 1
        return cur

    def resolve_type(v: str) -> str:
        return type_ctx.get(v, "TString")

    def build_reads(vs: list[str]) -> list[TypedVar]:
        return [TypedVar(v, resolve_type(v)) for v in vs]

    def add_seq(f: Optional[int], t: int):
        if f is not None:
            edges.append(EdgeIR("seq", from_node=f, to_node=t))

    # ---------- Recursive body-step parser ----------
    def parse_body_steps(body_steps: list, body_prev: Optional[int]) -> tuple:
        bf: Optional[int] = None
        extra_tails: list[int] = []

        def link_to(new_id: int) -> None:
            nonlocal extra_tails
            add_seq(body_prev, new_id)
            if extra_tails:
                for tail_id in list(dict.fromkeys(extra_tails)):
                    add_seq(tail_id, new_id)
                extra_tails = []

        for bs in body_steps:
            bk = list(bs.keys())[0]
            bd = bs[bk]

            if bk in ("step", "task", "synthesize", "discover"):
                bid = alloc_id()
                bname = bd.get("name", f"{bk}_{bid}")
                binstr = bd.get("instruction", "")
                bsave = bd.get("save_as", None)
                # `discover` also reads from a `from` expression in the old YAML
                # form; include its template vars for backward compatibility.
                extra = bd.get("from", "") if bk == "discover" else ""
                breads = build_reads(
                    sorted(set(extract_template_vars(binstr) + extract_template_vars(extra)))
                )
                bwrites: list[TypedVar] = []
                if bsave:
                    bwt = determine_write_type(yaml_key_to_step_type(bk))
                    bwrites.append(TypedVar(bsave, bwt))
                    type_ctx[bsave] = bwt
                nodes.append(NodeIR(
                    id=bid, name=bname, step_type=yaml_key_to_step_type(bk),
                    reads=breads, writes=bwrites,
                    instruction=binstr if binstr else None,
                ))
                link_to(bid)
                if bf is None: bf = bid
                body_prev = bid

            elif bk == "set_variable":
                bid = alloc_id()
                bvar = bd["name"]
                raw_val = bd.get("value", "")
                bval = str(raw_val)
                breads = build_reads(extract_template_vars(bval))
                bwt = _infer_set_variable_type(raw_val, type_ctx)
                bwrites = [TypedVar(bvar, bwt)]
                type_ctx[bvar] = bwt
                nodes.append(NodeIR(
                    id=bid, name=f"set_{bvar}", step_type="setVariable",
                    reads=breads, writes=bwrites,
                ))
                link_to(bid)
                if bf is None: bf = bid
                body_prev = bid

            elif bk == "for_each":
                hid = alloc_id()
                lvar = bd["variable"]; llist = bd["in"]
                lt = type_ctx.get(llist, "TString")
                if lt.startswith("TList"):
                    lparts = lt.split(maxsplit=1)
                    et = lparts[1] if len(lparts) > 1 else "TUnknown"
                else:
                    et = "TUnknown"
                type_ctx[lvar] = et
                nodes.append(NodeIR(
                    id=hid, name=f"foreach_{lvar}", step_type="forEachLoop",
                    reads=[TypedVar(llist, lt)], writes=[TypedVar(lvar, et)],
                ))
                link_to(hid)
                if bf is None: bf = hid
                inner_first, inner_last, inner_extra = parse_body_steps(bd.get("steps", []), None)
                if inner_first is not None and inner_last is not None:
                    le_idx = len(edges)
                    edges.append(EdgeIR("loop", header=hid, body_entry=inner_first, exit_node=None))
                    edges.append(EdgeIR("loopBack", from_node=inner_last, to_node=hid))
                    for et_id in inner_extra:
                        edges.append(EdgeIR("loopBack", from_node=et_id, to_node=hid))
                    loop_patches.append({'edge_idx': le_idx, 'header_id': hid})
                body_prev = hid

            elif bk == "while":
                bhdr_id = alloc_id()
                bcondition = bd.get("condition", "")
                breads = build_reads(_extract_condition_vars(bcondition))
                nodes.append(NodeIR(
                    id=bhdr_id, name=f"while_{bcondition[:30]}", step_type="whileLoop",
                    reads=breads, writes=[],
                ))
                link_to(bhdr_id)
                if bf is None: bf = bhdr_id
                binner_first, binner_last, binner_extra = parse_body_steps(bd.get("steps", []), None)
                if binner_first is not None and binner_last is not None:
                    ble_idx = len(edges)
                    edges.append(EdgeIR("loop", header=bhdr_id, body_entry=binner_first, exit_node=None))
                    edges.append(EdgeIR("loopBack", from_node=binner_last, to_node=bhdr_id))
                    for et_id in binner_extra:
                        edges.append(EdgeIR("loopBack", from_node=et_id, to_node=bhdr_id))
                    loop_patches.append({'edge_idx': ble_idx, 'header_id': bhdr_id})
                body_prev = bhdr_id

            elif bk == "if":
                bcond_id = alloc_id()
                bcondition = bd.get("condition", "")
                breads = build_reads(_extract_condition_vars(bcondition))
                nodes.append(NodeIR(
                    id=bcond_id, name=f"check_{bcondition[:30]}", step_type="conditional",
                    reads=breads, writes=[],
                ))
                link_to(bcond_id)
                if bf is None: bf = bcond_id
                bthen_first, bthen_last, bthen_extra = parse_body_steps(bd.get("then", []), None)
                belse_first, belse_last, belse_extra = parse_body_steps(bd.get("else", []), None)
                edges.append(EdgeIR("branch", cond_node=bcond_id, then_entry=bthen_first, else_entry=belse_first))
                extra_tails.extend(bthen_extra)
                extra_tails.extend(belse_extra)
                if belse_first is None:
                    extra_tails.append(bcond_id)
                if belse_last is not None and bthen_last is not None:
                    body_prev = belse_last
                    extra_tails.append(bthen_last)
                elif belse_last is not None:
                    body_prev = belse_last
                elif bthen_last is not None:
                    body_prev = bthen_last
                else:
                    body_prev = bcond_id

            elif bk == "parallel":
                if isinstance(bd, list):
                    bfork_id = alloc_id()
                    nodes.append(NodeIR(
                        id=bfork_id, name=f"parallel_fork_{bfork_id}", step_type="parallel",
                        reads=[], writes=[],
                    ))
                    link_to(bfork_id)
                    if bf is None: bf = bfork_id

                    bbranch_entries: list[int] = []
                    bbranch_exits: list[int] = []
                    for bsub_step in bd:
                        bsub_first, bsub_last, bsub_extra = parse_body_steps([bsub_step], None)
                        if bsub_first is not None:
                            bbranch_entries.append(bsub_first)
                        if bsub_last is not None:
                            bbranch_exits.append(bsub_last)
                        bbranch_exits.extend(bsub_extra)

                    bjoin_id = alloc_id()
                    nodes.append(NodeIR(
                        id=bjoin_id, name=f"parallel_join_{bjoin_id}", step_type="parallel",
                        reads=[], writes=[],
                    ))
                    if bbranch_entries:
                        edges.append(EdgeIR("fork", fork_node=bfork_id, branches=bbranch_entries))
                    if bbranch_exits:
                        edges.append(EdgeIR("join", branches=list(dict.fromkeys(bbranch_exits)), join_node=bjoin_id))
                    body_prev = bjoin_id
                else:
                    bid = alloc_id()
                    bpl = bd.get("parameters_list", "")
                    bsave = bd.get("save_results_as", None)
                    module_path = bd.get("module", "")
                    breads = build_reads([bpl]) if bpl else []
                    bwrites: list[TypedVar] = []
                    if bsave:
                        bwrites.append(TypedVar(bsave, "TList TUnknown"))
                        type_ctx[bsave] = "TList TUnknown"
                    sub_ref = None
                    if module_path:
                        sub_name = module_path.split("/")[-1].replace(".yaml", "")
                        sub_ref = SubmoduleRef(name=sub_name, kind="parallel",
                                               output_var=bsave, input_var=bpl or None)
                    nodes.append(NodeIR(
                        id=bid, name=f"parallel_{bsave or bid}", step_type="parallel",
                        reads=breads, writes=bwrites,
                        submodule_ref=sub_ref,
                    ))
                    link_to(bid)
                    if bf is None: bf = bid
                    body_prev = bid

            elif bk == "call":
                bid = alloc_id()
                bmodule = bd.get("module", "")
                bsave = bd.get("save_as", None)
                bcall_params = bd.get("parameters", {}) or {}
                bread_vars: list[str] = []
                for pval in bcall_params.values():
                    bread_vars.extend(extract_template_vars(str(pval)))
                breads = build_reads(sorted(set(bread_vars)))
                bwrites = []
                if bsave:
                    bwt = determine_write_type("call")
                    bwrites.append(TypedVar(bsave, bwt))
                    type_ctx[bsave] = bwt
                bmod_name = bmodule.split("/")[-1].replace(".yaml", "") if bmodule else f"call_{bid}"
                sub_ref = SubmoduleRef(name=bmod_name, kind="call", output_var=bsave) if bmodule else None
                nodes.append(NodeIR(
                    id=bid, name=f"call_{bmod_name}", step_type="call",
                    reads=breads, writes=bwrites,
                    instruction=f"Call module: {bmodule}" if bmodule else None,
                    submodule_ref=sub_ref,
                ))
                link_to(bid)
                if bf is None: bf = bid
                body_prev = bid

            elif bk == "increment":
                bid = alloc_id()
                bvar = bd if isinstance(bd, str) else str(bd)
                nodes.append(NodeIR(
                    id=bid, name=f"increment_{bvar}", step_type="incrementVariable",
                    reads=build_reads([bvar]), writes=[TypedVar(bvar, "TInt")],
                ))
                type_ctx[bvar] = "TInt"
                link_to(bid)
                if bf is None: bf = bid
                body_prev = bid

            elif bk == "return":
                bid = alloc_id()
                ret_var = bd if isinstance(bd, str) else str(bd)
                nodes.append(NodeIR(
                    id=bid, name="return_result", step_type="returnValue",
                    reads=build_reads([ret_var]), writes=[],
                ))
                link_to(bid)
                if bf is None: bf = bid
                body_prev = bid

            elif bk == "input":
                bid = alloc_id()
                bprompt = bd.get("prompt", "")
                bsave = bd.get("save_as", "user_input")
                breads = build_reads(extract_template_vars(bprompt))
                bwrites = [TypedVar(bsave, "TString")]
                type_ctx[bsave] = "TString"
                nodes.append(NodeIR(
                    id=bid, name=f"input_{bsave}", step_type="input",
                    reads=breads, writes=bwrites,
                    instruction=bprompt if bprompt else None,
                ))
                link_to(bid)
                if bf is None: bf = bid
                body_prev = bid

            else:
                print(f"[WARN] Unhandled step type in body: {bk}")

        return bf, body_prev, extra_tails

    # ---------- Top-level workflow steps ----------
    prev: Optional[int] = None

    for raw_step in data["workflow"]:
        yaml_key = list(raw_step.keys())[0]
        step_data = raw_step[yaml_key]

        if yaml_key in ("step", "task", "synthesize", "discover"):
            cur = alloc_id()
            name = step_data.get("name", f"{yaml_key}_{cur}")
            instruction = step_data.get("instruction", "")
            save_as = step_data.get("save_as", None)
            extra = step_data.get("from", "") if yaml_key == "discover" else ""
            reads = build_reads(sorted(set(
                extract_template_vars(instruction) + extract_template_vars(extra)
            )))
            writes: list[TypedVar] = []
            if save_as:
                wt = determine_write_type(yaml_key_to_step_type(yaml_key))
                writes.append(TypedVar(save_as, wt))
                type_ctx[save_as] = wt
            nodes.append(NodeIR(
                id=cur, name=name, step_type=yaml_key_to_step_type(yaml_key),
                reads=reads, writes=writes,
                instruction=instruction if instruction else None,
            ))
            add_seq(prev, cur); prev = cur

        elif yaml_key == "set_variable":
            cur = alloc_id()
            var_name = step_data["name"]
            raw_value = step_data.get("value", "")
            value_str = str(raw_value)
            reads = build_reads(extract_template_vars(value_str))
            wt = _infer_set_variable_type(raw_value, type_ctx)
            writes = [TypedVar(var_name, wt)]
            type_ctx[var_name] = wt
            nodes.append(NodeIR(
                id=cur, name=f"set_{var_name}", step_type="setVariable",
                reads=reads, writes=writes,
            ))
            add_seq(prev, cur); prev = cur

        elif yaml_key == "parallel":
            if isinstance(step_data, list):
                fork_id = alloc_id()
                nodes.append(NodeIR(
                    id=fork_id, name=f"parallel_fork_{fork_id}", step_type="parallel",
                    reads=[], writes=[],
                ))
                add_seq(prev, fork_id)

                branch_entries: list[int] = []
                branch_exits: list[int] = []
                for sub_step in step_data:
                    sub_first, sub_last, sub_extra = parse_body_steps([sub_step], None)
                    if sub_first is not None:
                        branch_entries.append(sub_first)
                    if sub_last is not None:
                        branch_exits.append(sub_last)
                    branch_exits.extend(sub_extra)

                join_id = alloc_id()
                nodes.append(NodeIR(
                    id=join_id, name=f"parallel_join_{join_id}", step_type="parallel",
                    reads=[], writes=[],
                ))
                if branch_entries:
                    edges.append(EdgeIR("fork", fork_node=fork_id, branches=branch_entries))
                if branch_exits:
                    edges.append(EdgeIR("join", branches=list(dict.fromkeys(branch_exits)), join_node=join_id))
                prev = join_id
            else:
                cur = alloc_id()
                params_list_var = step_data.get("parameters_list", "")
                save_as = step_data.get("save_results_as", None)
                module_path = step_data.get("module", "")
                reads = build_reads([params_list_var]) if params_list_var else []
                writes = []
                if save_as:
                    writes.append(TypedVar(save_as, "TList TUnknown"))
                    type_ctx[save_as] = "TList TUnknown"
                sub_ref = None
                if module_path:
                    sub_name = module_path.split("/")[-1].replace(".yaml", "")
                    sub_ref = SubmoduleRef(name=sub_name, kind="parallel",
                                           output_var=save_as, input_var=params_list_var or None)
                nodes.append(NodeIR(
                    id=cur, name=f"parallel_{save_as or cur}", step_type="parallel",
                    reads=reads, writes=writes,
                    submodule_ref=sub_ref,
                ))
                add_seq(prev, cur); prev = cur

        elif yaml_key == "for_each":
            header_id = alloc_id()
            loop_var = step_data["variable"]; list_var = step_data["in"]
            list_type = type_ctx.get(list_var, "TString")
            if list_type.startswith("TList"):
                parts = list_type.split(maxsplit=1)
                elem_type = parts[1] if len(parts) > 1 else "TUnknown"
            else:
                elem_type = "TUnknown"
            type_ctx[loop_var] = elem_type
            nodes.append(NodeIR(
                id=header_id, name=f"foreach_{loop_var}", step_type="forEachLoop",
                reads=[TypedVar(list_var, list_type)],
                writes=[TypedVar(loop_var, elem_type)],
            ))
            add_seq(prev, header_id)
            body_first, body_last, body_extra = parse_body_steps(step_data.get("steps", []), None)
            if body_first is not None and body_last is not None:
                loop_edge_idx = len(edges)
                edges.append(EdgeIR("loop", header=header_id, body_entry=body_first, exit_node=None))
                edges.append(EdgeIR("loopBack", from_node=body_last, to_node=header_id))
                for et_id in body_extra:
                    edges.append(EdgeIR("loopBack", from_node=et_id, to_node=header_id))
                loop_patches.append({'edge_idx': loop_edge_idx, 'header_id': header_id})
            prev = header_id

        elif yaml_key == "while":
            header_id = alloc_id()
            condition = step_data.get("condition", "")
            reads = build_reads(_extract_condition_vars(condition))
            nodes.append(NodeIR(
                id=header_id, name=f"while_{condition[:30]}", step_type="whileLoop",
                reads=reads, writes=[],
            ))
            add_seq(prev, header_id)
            body_first, body_last, body_extra = parse_body_steps(step_data.get("steps", []), None)
            if body_first is not None and body_last is not None:
                loop_edge_idx = len(edges)
                edges.append(EdgeIR("loop", header=header_id, body_entry=body_first, exit_node=None))
                edges.append(EdgeIR("loopBack", from_node=body_last, to_node=header_id))
                for et_id in body_extra:
                    edges.append(EdgeIR("loopBack", from_node=et_id, to_node=header_id))
                loop_patches.append({'edge_idx': loop_edge_idx, 'header_id': header_id})
            prev = header_id

        elif yaml_key == "call":
            cur = alloc_id()
            module = step_data.get("module", "")
            save_as = step_data.get("save_as", None)
            call_params = step_data.get("parameters", {}) or {}
            read_vars: list[str] = []
            for pval in call_params.values():
                read_vars.extend(extract_template_vars(str(pval)))
            reads = build_reads(sorted(set(read_vars)))
            writes = []
            if save_as:
                wt = determine_write_type("call")
                writes.append(TypedVar(save_as, wt))
                type_ctx[save_as] = wt
            module_name = module.split("/")[-1].replace(".yaml", "") if module else f"call_{cur}"
            sub_ref = SubmoduleRef(name=module_name, kind="call", output_var=save_as) if module else None
            nodes.append(NodeIR(
                id=cur, name=f"call_{module_name}", step_type="call",
                reads=reads, writes=writes,
                instruction=f"Call module: {module}" if module else None,
                submodule_ref=sub_ref,
            ))
            add_seq(prev, cur); prev = cur

        elif yaml_key == "increment":
            cur = alloc_id()
            var_name = step_data if isinstance(step_data, str) else str(step_data)
            reads = build_reads([var_name])
            writes = [TypedVar(var_name, "TInt")]
            type_ctx[var_name] = "TInt"
            nodes.append(NodeIR(
                id=cur, name=f"increment_{var_name}", step_type="incrementVariable",
                reads=reads, writes=writes,
            ))
            add_seq(prev, cur); prev = cur

        elif yaml_key == "if":
            cond_id = alloc_id()
            condition = step_data.get("condition", "")
            reads = build_reads(_extract_condition_vars(condition))
            nodes.append(NodeIR(
                id=cond_id, name=f"check_{condition[:30]}", step_type="conditional",
                reads=reads, writes=[],
            ))
            add_seq(prev, cond_id)
            then_first, then_last, _ = parse_body_steps(step_data.get("then", []), None)
            else_first, else_last, _ = parse_body_steps(step_data.get("else", []), None)
            edges.append(EdgeIR("branch", cond_node=cond_id, then_entry=then_first, else_entry=else_first))
            if not hasattr(parse_task_json, '_pending_branches'):
                parse_task_json._pending_branches = []
            parse_task_json._pending_branches.append({
                'cond_id': cond_id, 'then_last': then_last,
                'else_last': else_last, 'has_else': else_first is not None,
            })
            if else_last is not None: prev = else_last
            elif then_last is not None: prev = then_last
            else: prev = cond_id

        elif yaml_key == "return":
            cur = alloc_id()
            ret_var = step_data if isinstance(step_data, str) else str(step_data)
            nodes.append(NodeIR(
                id=cur, name="return_result", step_type="returnValue",
                reads=build_reads([ret_var]), writes=[],
            ))
            add_seq(prev, cur); prev = cur

        elif yaml_key == "input":
            cur = alloc_id()
            prompt = step_data.get("prompt", "")
            save_as = step_data.get("save_as", "user_input")
            reads = build_reads(extract_template_vars(prompt))
            writes = [TypedVar(save_as, "TString")]
            type_ctx[save_as] = "TString"
            nodes.append(NodeIR(
                id=cur, name=f"input_{save_as}", step_type="input",
                reads=reads, writes=writes,
                instruction=prompt if prompt else None,
            ))
            add_seq(prev, cur); prev = cur

        elif yaml_key == "switch":
            cur = alloc_id()
            switch_var = step_data.get("variable", "")
            reads = build_reads([switch_var]) if switch_var else []
            nodes.append(NodeIR(
                id=cur, name=f"switch_{switch_var}", step_type="switchBranch",
                reads=reads, writes=[],
            ))
            add_seq(prev, cur); prev = cur

        elif yaml_key == "gather":
            cur = alloc_id()
            save_results_as = step_data.get("save_results_as", None) if isinstance(step_data, dict) else None
            nodes.append(NodeIR(
                id=cur, name=f"gather_{cur}", step_type="gather",
                reads=[], writes=[TypedVar(save_results_as, "TList TUnknown")] if save_results_as else [],
            ))
            if save_results_as:
                type_ctx[save_results_as] = "TList TUnknown"
            add_seq(prev, cur); prev = cur

        else:
            print(f"[WARN] Unhandled step type: {yaml_key}")

    # ---- Patch loop exits ----
    for loop_info in loop_patches:
        edge_idx = loop_info['edge_idx']
        header_id = loop_info['header_id']
        found = False
        for i, e in enumerate(edges):
            if e is not None and e.edge_type == "seq" and e.from_node == header_id:
                edges[edge_idx].exit_node = e.to_node
                edges[i] = None
                found = True
                break
        if not found:
            edges[edge_idx].exit_node = header_id
    edges[:] = [e for e in edges if e is not None]

    # ---- Patch branch edges ----
    if hasattr(parse_task_json, '_pending_branches'):
        for branch_info in parse_task_json._pending_branches:
            cond_id = branch_info['cond_id']
            branch_edge = next(
                (e for e in edges if e.edge_type == "branch" and e.cond_node == cond_id),
                None,
            )
            if branch_edge is None:
                continue
            then_last = branch_info['then_last']
            then_first = branch_edge.then_entry
            else_last = branch_info['else_last']
            has_else = branch_info['has_else']
            merge_point = None
            search_from = then_last if then_last is not None else cond_id
            for e in edges:
                if e.edge_type == "seq" and e.from_node == search_from:
                    merge_point = e.to_node
                    break
            if merge_point is None and not has_else:
                loop_header = None
                if then_first is not None:
                    for e in edges:
                        if e.edge_type == "loop" and e.header == then_first:
                            merge_point = e.exit_node
                            break
                if merge_point is None and then_last is not None:
                    for e in edges:
                        if e.edge_type == "loopBack" and e.from_node == then_last:
                            loop_header = e.to_node
                            break
                    if loop_header is not None:
                        for e in edges:
                            if e.edge_type == "loop" and e.header == loop_header:
                                merge_point = e.exit_node
                                break
            if merge_point is not None:
                if not has_else:
                    branch_edge.else_entry = merge_point
                else:
                    if else_last is not None:
                        edges.append(EdgeIR("seq", from_node=else_last, to_node=merge_point))
        parse_task_json._pending_branches = []

    # ---- Fill missing else_entry for branch edges ----
    for e in edges:
        if e.edge_type == "branch" and e.else_entry is None and e.cond_node is not None:
            fallthrough = None
            for oe in edges:
                if oe.edge_type == "seq" and oe.from_node == e.cond_node:
                    fallthrough = oe.to_node
                    break
            if fallthrough is None:
                for oe in edges:
                    if oe.edge_type == "loopBack" and oe.from_node == e.cond_node:
                        fallthrough = oe.to_node
                        break
            if fallthrough is not None:
                e.else_entry = fallthrough

    sub_map: dict[str, SubmoduleRef] = {}
    for n in nodes:
        if n.submodule_ref is not None and n.submodule_ref.name not in sub_map:
            sub_map[n.submodule_ref.name] = n.submodule_ref

    return WorkflowIR(
        name=wf_name, goal=wf_goal, parameters=params,
        nodes=nodes, edges=edges, entry=0,
        exits=[nodes[-1].id] if nodes else [],
        submodule_map=sub_map if sub_map else None,
    )


# ============================================================================
# 3. LEAN CODE GENERATOR
# ============================================================================

def generate_lean(ir: WorkflowIR, prefix: str) -> str:
    """Emit a Lean verification file for `ir`."""
    lines: list[str] = []

    # Header
    lines.append("import Lean")
    lines.append("import Mathlib")
    lines.append("import AgentVerifier.Basics")
    lines.append("")
    lines.append("namespace AgenticKernel")
    lines.append("")

    # Banner
    lines.append("/-")
    lines.append("=" * 80)
    lines.append(f"STATIC VERIFICATION: {ir.name}")
    lines.append(f"Goal: {ir.goal}")
    lines.append(f"Parameters: {[p.name for p in ir.parameters]}")
    lines.append(f"Nodes: {len(ir.nodes)}, Entry: {ir.entry}, Exits: {ir.exits}")
    lines.append("")
    for n in ir.nodes:
        rstr = ", ".join(r.name for r in n.reads) or "(none)"
        wstr = ", ".join(w.name for w in n.writes) or "(none)"
        tag = "[DET]" if not n.is_llm_node else "[LLM]"
        lines.append(f"  Node {n.id:3d}: {n.step_type:18s} {tag:6s} \"{n.name}\"")
        lines.append(f"          reads:  {rstr}")
        lines.append(f"          writes: {wstr}")
    lines.append("=" * 80)
    lines.append("-/")
    lines.append("")

    # STEP 1: WORKFLOW GRAPH
    lines.append("/-")
    lines.append("=" * 72)
    lines.append("STEP 1: WORKFLOW GRAPH")
    lines.append("=" * 72)
    lines.append("-/")
    lines.append("")
    lines.append("-- Node IDs")
    for n in ir.nodes:
        lines.append(f"def {prefix}_nodeId{n.id} : NodeId := ⟨{n.id}⟩")
    lines.append("")

    for n in ir.nodes:
        ri = ", ".join(v.to_lean_typed() for v in n.reads)
        wi = ", ".join(v.to_lean_typed() for v in n.writes)
        nm = f'some "{n.name}"' if n.name else "none"
        if n.instruction:
            esc = n.instruction.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            ins = f'some "{esc}"'
        else:
            ins = "none"
        lines.append(f"-- Node {n.id}: {n.step_type} \"{n.name}\"")
        lines.append(f"def {prefix}_node{n.id} : WorkflowNode := {{")
        lines.append(f"  id := {prefix}_nodeId{n.id}, name := {nm}")
        lines.append(f"  stepType := .{n.step_type}")
        lines.append(f"  reads := [{ri}], writes := [{wi}]")
        lines.append(f"  llmInstruction := {ins}")
        lines.append("}")
        lines.append("")

    # Graph
    nl = ", ".join(f"{prefix}_node{n.id}" for n in ir.nodes)
    el = ",\n    ".join(e.to_lean(prefix) for e in ir.edges)
    pi = ", ".join(p.to_lean_typed() for p in ir.parameters)
    xi = ", ".join(f"{prefix}_nodeId{x}" for x in ir.exits)
    lines.append(f"def {prefix}Graph : WorkflowGraph := {{")
    lines.append(f"  nodes := [{nl}]")
    lines.append(f"  edges := [\n    {el}\n  ]")
    lines.append(f"  entry := {prefix}_nodeId{ir.entry}")
    lines.append(f"  exits := [{xi}]")
    lines.append(f"  parameters := [{pi}]")
    lines.append("}")
    lines.append("")

    # STEP 2-5: structural checks + theorems
    lines.extend(_gen_structural(ir, prefix))

    lines.append("")
    lines.append("end AgenticKernel")
    return "\n".join(lines)


def _gen_structural(ir: WorkflowIR, prefix: str) -> list[str]:
    """Emit per-node diagnostics, graph-level checks, and structural theorems."""
    lines: list[str] = []
    thm = ir.name.replace("-", "_")
    ns = ", ".join(f"{prefix}_node{n.id}" for n in ir.nodes)
    pl = ", ".join(p.to_lean_typed() for p in ir.parameters)

    # STEP 2: Per-node diagnostics
    lines.append("/-")
    lines.append("=" * 72)
    lines.append("STEP 2: PER-NODE STRUCTURAL DIAGNOSTICS")
    lines.append("=" * 72)
    lines.append("-/")
    lines.append("")
    lines.append("#eval do")
    lines.append(f"  let g := {prefix}Graph")
    lines.append('  for node in g.nodes do')
    lines.append('    let name := node.name.getD "(unnamed)"')
    lines.append('    IO.println s!"\\n--- Node {node.id}: \\"{name}\\" [{repr node.stepType}] ---"')
    lines.append('    IO.println s!"  writesConsistent:   {node.writesConsistent}"')
    lines.append('    IO.println s!"  reachableFromEntry: {g.reachable g.entry node.id}"')
    lines.append('    for rv in node.reads do')
    lines.append('      let fromParam := g.parameters.any (fun p =>')
    lines.append('        p.name == rv.name && p.type.compatible rv.type)')
    lines.append('      let fromPred := g.nodes.any (fun o =>')
    lines.append('        o.id != node.id && g.reachable o.id node.id &&')
    lines.append('        (!g.isParallelScopedNode o.id || g.isParallelScopedNode node.id) &&')
    lines.append('        o.writes.any (fun w => w.name == rv.name && w.type.compatible rv.type))')
    lines.append('      let status := if fromParam || fromPred then "✓" else "✗ UNRESOLVED"')
    lines.append('      IO.println s!"    read  \\"{rv.name}\\" ({repr rv.type}): {status}"')
    lines.append('    for wv in node.writes do')
    lines.append('      IO.println s!"    write \\"{wv.name}\\" ({repr wv.type})"')
    lines.append("")

    # STEP 3: Graph-level checks
    lines.append("/-")
    lines.append("=" * 72)
    lines.append("STEP 3: GRAPH-LEVEL STRUCTURAL CHECKS")
    lines.append("=" * 72)
    lines.append("-/")
    lines.append("")
    for prop in ("allWritesConsistent", "allReadResolvable", "edgesValid",
                 "entryNodeValid", "exitNodesValid", "allExitsReachable", "noOrphanNodes"):
        lines.append(f"#eval {prefix}Graph.{prop}")
    lines.append(f"#eval {prefix}Graph.returnType")
    lines.append("")

    # STEP 4-5: Theorems
    lines.append("/-")
    lines.append("=" * 72)
    lines.append("STEP 4-5: THEOREMS")
    lines.append("=" * 72)
    lines.append("-/")
    lines.append("")
    for s, p in (("writesConsistent", "allWritesConsistent"),
                 ("readsResolvable", "allReadResolvable"),
                 ("edgesValid", "edgesValid"),
                 ("entryValid", "entryNodeValid"),
                 ("exitsValid", "exitNodesValid"),
                 ("exitsReachable", "allExitsReachable"),
                 ("noOrphans", "noOrphanNodes")):
        lines.append(f"theorem {thm}_{s} : {prefix}Graph.{p} = true := by native_decide")
    lines.append("")
    lines.append(f"theorem {thm}_seqPath_typeChecks :")
    lines.append(f"    ∃ ctx, typeCheckSequence [{ns}] [{pl}] = .ok ctx := by exact ⟨_, rfl⟩")
    lines.append("")
    llm = sum(1 for n in ir.nodes if n.is_llm_node)
    lines.append(f"theorem {thm}_llmNodeCount : {prefix}Graph.llmNodes.length = {llm} := by native_decide")
    lines.append("")
    return lines


# ============================================================================
# 4. CLI (direct: parsed_task.json → .lean)
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate a Lean 4 structural verification from parsed_task.json or IR JSON.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json_path", help="Path to parsed_task.json (from yaml_parser)")
    source.add_argument("--from_ir", help="Path to a previously saved IR JSON")
    parser.add_argument("--prefix", default="workflow", help="Lean definition name prefix")
    parser.add_argument("--output", help="Output path for the generated .lean file")
    parser.add_argument("--save_ir", help="Save the WorkflowIR as JSON")
    parser.add_argument("--env_file", action="append", default=[],
                        help="Load env vars from file(s) before parsing (repeatable)")
    args = parser.parse_args()

    if not args.output and not args.save_ir:
        parser.error("At least one of --output or --save_ir is required")

    for ef in args.env_file:
        print(f"Loading env: {ef}")
        _load_env_file(ef)

    if args.from_ir:
        print(f"Loading IR: {args.from_ir}")
        ir = WorkflowIR.load_json(args.from_ir)
    else:
        print(f"Parsing: {args.json_path}")
        ir = parse_task_json(args.json_path)

    print(f"  {len(ir.nodes)} nodes, {len(ir.edges)} edges")
    for n in ir.nodes:
        tag = "DET" if not n.is_llm_node else "LLM"
        print(f"    Node {n.id}: {n.step_type:18s} [{tag}] \"{n.name}\"")


    if args.save_ir:
        ir.save_json(args.save_ir)
        print(f"\nSaved IR: {args.save_ir}")

    if args.output:
        lean_code = generate_lean(ir, args.prefix)
        with open(args.output, "w") as f:
            f.write(lean_code)
        print(f"\nGenerated: {args.output} ({lean_code.count(chr(10))} lines)")
