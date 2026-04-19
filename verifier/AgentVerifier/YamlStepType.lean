import Lean
import Mathlib
import AgentVerifier.BaseTypes


namespace AgenticKernel

/-
========================================================================
2. STEP EXECUTION TYPES
========================================================================

The fundamental classification: does the step involve LLM inference?
If yes, is the output structured or unstructured?

This is NOT just a label — it determines what the verifier can and
cannot say about this step's output.
-/

inductive ExecType where
  -- No LLM involved, behavior is fully determined by the YAML structure.
  | deterministic
  -- LLM involved in the process, but the output is expected to be structured and the format can be determined prior to execution.
  | structured
  -- LLM involved, output is free-form text, the format cannot be determined prior to execution.
  | unstructured
  -- The composition of a submodule; makes the execution type of the composition the same as the submodule's execution type, which can be any of the above three.
  | composition
  deriving Repr, BEq, Inhabited


/-
========================================================================
3. STEP TAG — THE 13 YAML STEP TYPES
========================================================================

These match exactly the 13 keys dispatched by
`src/harness/execution/interpreter.py::_STEP_TYPE_KEYS`:
  step, task, for_each, if, parallel, while, switch, increment,
  set_variable, input, call, gather, return
-/

inductive StepType where
  -- Pure YAML structure, no LLM involved.
  | forEachLoop         -- Loop over a list (YAML: for_each)
  | whileLoop           -- Loop with a condition (YAML: while)
  | conditional         -- Conditional branch (YAML: if)
  | switchBranch        -- Switch/case statement (YAML: switch)
  | setVariable         -- Set a context variable (YAML: set_variable)
  | incrementVariable   -- Increment a numeric variable (YAML: increment)
  | returnValue         -- Return the value from a submodule to the parent workflow (YAML: return)
  | input               -- Collect user input → TString (YAML: input)
  | parallel            -- Parallel execution of sub-steps (YAML: parallel)
  | gather              -- Parallel heterogeneous sub-module calls (YAML: gather)
  -- LLM steps with unstructured output
  | step                -- Stateful agent action; preserves workflow-level conversation history across steps (YAML: step)
  | task                -- Stateless agent action; each execution starts with a fresh conversation (YAML: task)
  -- Composition
  | call                -- Call a sub-module synchronously (YAML: call)
  deriving Repr, BEq, Inhabited

/-- Map each StepType to its corresponding ExecType --/
def StepType.execType : StepType -> ExecType
  -- Deterministic (no LLM involved)
  | .forEachLoop | .whileLoop | .conditional | .switchBranch
  | .setVariable | .incrementVariable | .returnValue | .input
  | .parallel | .gather => .deterministic
  -- LLM with free-form output
  | .step | .task => .unstructured
  -- Submodule composition; execution type deferred to the submodule
  | .call => .composition

/-
========================================================================
4. TYPED VARIABLE BINDING
========================================================================
-/

structure TypedVar where
  name : String
  type : BaseType
deriving Repr, BEq, Hashable, Inhabited

abbrev TypedContext := List TypedVar

def TypedContext.lookup (context : TypedContext) (name : String) : Option BaseType :=
  match context.find? (fun v => v.name == name) with
  | some v => some v.type
  | none   => none

def TypedContext.contains (context : TypedContext) (name : String) : Bool :=
  context.any (fun v => v.name == name)

def TypedContext.extend (context : TypedContext) (newVars : List TypedVar) : TypedContext :=
  let filtered := context.filter (fun v => !newVars.any (fun nv => nv.name == v.name))
  filtered ++ newVars

/-
========================================================================
6. STEP-TYPE-SPECIFIC OUTPUT TYPE RULES
========================================================================

For each of the 13 step types, define what output type is expected.

Pure steps: output type is fully determined
LLM + unstructured: output type defaults to TString
Composition (call): output type is TUnknown until resolved
-/

/-- The default output type for a step tag (when save_as is used).
Returns none if the step doesn't produce a context variable. -/
def StepType.defaultOutputType : StepType -> Option BaseType
  -- Pure steps that don't produce a context variable
  | .forEachLoop | .whileLoop | .conditional | .switchBranch | .setVariable => none
  | .returnValue => none  -- return flows to the caller; no local var written
  -- Pure steps that do produce a context variable
  | .incrementVariable => some .TInt
  | .input => some .TString
  | .parallel => some (.TList .TUnknown)  -- list of sub-step results
  | .gather => some (.TList .TUnknown)    -- list of heterogeneous sub-module results
  -- LLM + unstructured output (free-form text)
  | .step | .task => some .TString
  -- Composition (output type depends on the sub-module)
  | .call => some .TUnknown

end AgenticKernel
