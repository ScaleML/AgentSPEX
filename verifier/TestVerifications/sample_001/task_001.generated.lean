import Lean
import Mathlib
import AgentVerifier.Basics

namespace AgenticKernel

/-
================================================================================
STATIC VERIFICATION: rlhf_verifiable_rewards_search_2025_2026
Goal: Find 12-15 recent (2025-2026) academic papers on 'RLHF with Verifiable Rewards' and produce a structured list with metadata and relevance notes.
Parameters: ['query1', 'query2', 'query3', 'query4', 'start_year', 'end_year', 'per_query_limit', 'arxiv_num_results', 'candidate_min', 'candidate_max']
Nodes: 8, Entry: 0, Exits: [7]

  Node   0: parallel           [DET]  "parallel_fork_0"
          reads:  (none)
          writes: (none)
  Node   1: task               [LLM]  "search_q1"
          reads:  end_year, per_query_limit, query1, start_year
          writes: results_q1
  Node   2: task               [LLM]  "search_q2"
          reads:  end_year, per_query_limit, query2, start_year
          writes: results_q2
  Node   3: task               [LLM]  "search_q3"
          reads:  end_year, per_query_limit, query3, start_year
          writes: results_q3
  Node   4: task               [LLM]  "search_q4"
          reads:  end_year, per_query_limit, query4, start_year
          writes: results_q4
  Node   5: parallel           [DET]  "parallel_join_5"
          reads:  (none)
          writes: (none)
  Node   6: task               [LLM]  "merge_dedupe_select_candidates"
          reads:  candidate_max, candidate_min, end_year, results_q1, results_q2, results_q3, results_q4, start_year
          writes: candidate_list
  Node   7: task               [LLM]  "enrich_with_arxiv_and_score"
          reads:  arxiv_num_results, candidate_list, candidate_max, candidate_min, end_year, start_year
          writes: papers_structured
================================================================================
-/

/-
========================================================================
STEP 1: WORKFLOW GRAPH
========================================================================
-/

-- Node IDs
def rlhfSearch_nodeId0 : NodeId := ⟨0⟩
def rlhfSearch_nodeId1 : NodeId := ⟨1⟩
def rlhfSearch_nodeId2 : NodeId := ⟨2⟩
def rlhfSearch_nodeId3 : NodeId := ⟨3⟩
def rlhfSearch_nodeId4 : NodeId := ⟨4⟩
def rlhfSearch_nodeId5 : NodeId := ⟨5⟩
def rlhfSearch_nodeId6 : NodeId := ⟨6⟩
def rlhfSearch_nodeId7 : NodeId := ⟨7⟩

-- Node 0: parallel "parallel_fork_0"
def rlhfSearch_node0 : WorkflowNode := {
  id := rlhfSearch_nodeId0, name := some "parallel_fork_0"
  stepType := .parallel
  reads := [], writes := []
  llmInstruction := none
}

-- Node 1: task "search_q1"
def rlhfSearch_node1 : WorkflowNode := {
  id := rlhfSearch_nodeId1, name := some "search_q1"
  stepType := .task
  reads := [⟨"end_year", .TInt⟩, ⟨"per_query_limit", .TInt⟩, ⟨"query1", .TString⟩, ⟨"start_year", .TInt⟩], writes := [⟨"results_q1", .TString⟩]
  llmInstruction := some "Use paper_search to run an academic search with this exact query: \"{{query1}}\".\nConstraints:\n- Restrict to publication years between {{start_year}} and {{end_year}} inclusive (apply tool filters if available; otherwise filter after retrieval).\n- Sort by most recent.\n- Set result_limit to {{per_query_limit}} (≤10).\nAfter retrieving results, transform them into a compact JSON array with objects containing ONLY:\n{\n  \"title\": string,\n  \"authors\": [string, ...],\n  \"publication_date\": \"YYYY-MM-DD\" or \"YYYY\",\n  \"abstract\": string or null,\n  \"doi\": string or null,\n  \"arxiv_id\": string or null,\n  \"url\": string\n}\nFilter out any items not in years {{start_year}}-{{end_year}}.\nReturn ONLY the JSON array. Do not include any other text.\n"
}

-- Node 2: task "search_q2"
def rlhfSearch_node2 : WorkflowNode := {
  id := rlhfSearch_nodeId2, name := some "search_q2"
  stepType := .task
  reads := [⟨"end_year", .TInt⟩, ⟨"per_query_limit", .TInt⟩, ⟨"query2", .TString⟩, ⟨"start_year", .TInt⟩], writes := [⟨"results_q2", .TString⟩]
  llmInstruction := some "Use paper_search to run an academic search with this exact query: \"{{query2}}\".\nConstraints:\n- Restrict to publication years between {{start_year}} and {{end_year}} inclusive (apply tool filters if available; otherwise filter after retrieval).\n- Sort by most recent.\n- Set result_limit to {{per_query_limit}} (≤10).\nAfter retrieving results, transform them into a compact JSON array with objects containing ONLY:\n{\n  \"title\": string,\n  \"authors\": [string, ...],\n  \"publication_date\": \"YYYY-MM-DD\" or \"YYYY\",\n  \"abstract\": string or null,\n  \"doi\": string or null,\n  \"arxiv_id\": string or null,\n  \"url\": string\n}\nFilter out any items not in years {{start_year}}-{{end_year}}.\nReturn ONLY the JSON array. Do not include any other text.\n"
}

-- Node 3: task "search_q3"
def rlhfSearch_node3 : WorkflowNode := {
  id := rlhfSearch_nodeId3, name := some "search_q3"
  stepType := .task
  reads := [⟨"end_year", .TInt⟩, ⟨"per_query_limit", .TInt⟩, ⟨"query3", .TString⟩, ⟨"start_year", .TInt⟩], writes := [⟨"results_q3", .TString⟩]
  llmInstruction := some "Use paper_search to run an academic search with this exact query: \"{{query3}}\".\nConstraints:\n- Restrict to publication years between {{start_year}} and {{end_year}} inclusive (apply tool filters if available; otherwise filter after retrieval).\n- Sort by most recent.\n- Set result_limit to {{per_query_limit}} (≤10).\nAfter retrieving results, transform them into a compact JSON array with objects containing ONLY:\n{\n  \"title\": string,\n  \"authors\": [string, ...],\n  \"publication_date\": \"YYYY-MM-DD\" or \"YYYY\",\n  \"abstract\": string or null,\n  \"doi\": string or null,\n  \"arxiv_id\": string or null,\n  \"url\": string\n}\nFilter out any items not in years {{start_year}}-{{end_year}}.\nReturn ONLY the JSON array. Do not include any other text.\n"
}

-- Node 4: task "search_q4"
def rlhfSearch_node4 : WorkflowNode := {
  id := rlhfSearch_nodeId4, name := some "search_q4"
  stepType := .task
  reads := [⟨"end_year", .TInt⟩, ⟨"per_query_limit", .TInt⟩, ⟨"query4", .TString⟩, ⟨"start_year", .TInt⟩], writes := [⟨"results_q4", .TString⟩]
  llmInstruction := some "Use paper_search to run an academic search with this exact query: \"{{query4}}\".\nConstraints:\n- Restrict to publication years between {{start_year}} and {{end_year}} inclusive (apply tool filters if available; otherwise filter after retrieval).\n- Sort by most recent.\n- Set result_limit to {{per_query_limit}} (≤10).\nAfter retrieving results, transform them into a compact JSON array with objects containing ONLY:\n{\n  \"title\": string,\n  \"authors\": [string, ...],\n  \"publication_date\": \"YYYY-MM-DD\" or \"YYYY\",\n  \"abstract\": string or null,\n  \"doi\": string or null,\n  \"arxiv_id\": string or null,\n  \"url\": string\n}\nFilter out any items not in years {{start_year}}-{{end_year}}.\nReturn ONLY the JSON array. Do not include any other text.\n"
}

-- Node 5: parallel "parallel_join_5"
def rlhfSearch_node5 : WorkflowNode := {
  id := rlhfSearch_nodeId5, name := some "parallel_join_5"
  stepType := .parallel
  reads := [], writes := []
  llmInstruction := none
}

-- Node 6: task "merge_dedupe_select_candidates"
def rlhfSearch_node6 : WorkflowNode := {
  id := rlhfSearch_nodeId6, name := some "merge_dedupe_select_candidates"
  stepType := .task
  reads := [⟨"candidate_max", .TInt⟩, ⟨"candidate_min", .TInt⟩, ⟨"end_year", .TInt⟩, ⟨"results_q1", .TString⟩, ⟨"results_q2", .TString⟩, ⟨"results_q3", .TString⟩, ⟨"results_q4", .TString⟩, ⟨"start_year", .TInt⟩], writes := [⟨"candidate_list", .TString⟩]
  llmInstruction := some "You are given four JSON arrays of paper records: {{results_q1}}, {{results_q2}}, {{results_q3}}, {{results_q4}}.\n1) Parse and combine them into a single list.\n2) Deduplicate using this priority:\n   - If DOI matches (case-insensitive), treat as same paper.\n   - Else if arxiv_id matches (case-insensitive), treat as same paper.\n   - Else if normalized title matches (lowercased, remove punctuation/whitespace), treat as same paper.\n   When merging duplicates, keep the most complete metadata (prefer non-null abstract, keep DOI if any, keep arxiv_id if any, keep the most recent publication_date).\n3) Keep only items with publication year in [{{start_year}}, {{end_year}}].\n4) Score preliminary topical relevance (0.0-1.0) favoring presence of these terms/stems in title/abstract: [\"RLHF\", \"reinforcement learning from human feedback\", \"verifiable\", \"verification\", \"verified\", \"verifiable rewards\", \"reward model verification\"].\n5) Sort primarily by publication_date (newest first), secondarily by preliminary relevance (highest first).\n6) Select between {{candidate_min}} and {{candidate_max}} items if available; if fewer exist, return all available.\nOutput ONLY a JSON array of objects with fields:\n{\n  \"title\": string,\n  \"authors\": [string, ...],\n  \"publication_date\": \"YYYY-MM-DD\" or \"YYYY\",\n  \"abstract\": string or null,\n  \"doi\": string or null,\n  \"arxiv_id\": string or null,\n  \"url\": string\n}\nDo not include any other text.\n"
}

-- Node 7: task "enrich_with_arxiv_and_score"
def rlhfSearch_node7 : WorkflowNode := {
  id := rlhfSearch_nodeId7, name := some "enrich_with_arxiv_and_score"
  stepType := .task
  reads := [⟨"arxiv_num_results", .TInt⟩, ⟨"candidate_list", .TString⟩, ⟨"candidate_max", .TInt⟩, ⟨"candidate_min", .TInt⟩, ⟨"end_year", .TInt⟩, ⟨"start_year", .TInt⟩], writes := [⟨"papers_structured", .TString⟩]
  llmInstruction := some "Enrich and score each paper in this JSON array: {{candidate_list}}.\nFor each paper (target total between {{candidate_min}} and {{candidate_max}}):\n- If arxiv_id is present and abstract is non-null, reuse it and SKIP arxiv_search for that paper.\n- Otherwise, attempt to find an exact arXiv entry using arxiv_search:\n  • Query: the paper's title; append the first author surname if available.\n  • Constrain to years {{start_year}}-{{end_year}} by filtering results after retrieval.\n  • Set num_results to {{arxiv_num_results}} (≤5).\n  • Choose the best match by case-insensitive title similarity (ignore punctuation) and author overlap.\n  • If a match is found, extract arxiv_id and full abstract from arXiv.\n- Compose the final record for each paper with:\n  {\n    \"title\": string,\n    \"authors\": [string, ...],\n    \"publication_date\": \"YYYY-MM-DD\" or \"YYYY\",\n    \"abstract\": string (prefer arXiv abstract if found; otherwise use existing; if still missing, use empty string),\n    \"arxiv_id_or_url\": string (prefer \"arXiv:ID\" if found; else use url; if missing, use DOI URL if DOI available),\n    \"doi\": string or null,\n    \"url\": string or null,\n    \"relevance_score\": number between 0.0 and 1.0,\n    \"relevance_notes\": short string explaining why this paper matches \"RLHF with Verifiable Rewards\"\n  }\nRelevance scoring guidance:\n- Higher if title/abstract mention \"RLHF\" or \"reinforcement learning from human feedback\" AND \"verifiable\"/\"verification\"/\"verified\" AND \"reward(s)\" or \"reward model\".\n- Slightly boost for 2026 over 2025, and for explicit evaluation/verification methods for reward models.\n- Penalize if \"verifiable\" relates to unrelated domains (e.g., cryptographic proofs not about reward verification).\nAfter processing all items, sort by:\n  1) publication_date (newest first),\n  2) relevance_score (highest first).\nReturn ONLY a JSON array of the final records described above. Do not include any other text.\n"
}

def rlhfSearchGraph : WorkflowGraph := {
  nodes := [rlhfSearch_node0, rlhfSearch_node1, rlhfSearch_node2, rlhfSearch_node3, rlhfSearch_node4, rlhfSearch_node5, rlhfSearch_node6, rlhfSearch_node7]
  edges := [
    .forkEdge rlhfSearch_nodeId0 [rlhfSearch_nodeId1, rlhfSearch_nodeId2, rlhfSearch_nodeId3, rlhfSearch_nodeId4],
    .joinEdge [rlhfSearch_nodeId1, rlhfSearch_nodeId2, rlhfSearch_nodeId3, rlhfSearch_nodeId4] rlhfSearch_nodeId5,
    .seqEdge rlhfSearch_nodeId5 rlhfSearch_nodeId6,
    .seqEdge rlhfSearch_nodeId6 rlhfSearch_nodeId7
  ]
  entry := rlhfSearch_nodeId0
  exits := [rlhfSearch_nodeId7]
  parameters := [⟨"query1", .TString⟩, ⟨"query2", .TString⟩, ⟨"query3", .TString⟩, ⟨"query4", .TString⟩, ⟨"start_year", .TInt⟩, ⟨"end_year", .TInt⟩, ⟨"per_query_limit", .TInt⟩, ⟨"arxiv_num_results", .TInt⟩, ⟨"candidate_min", .TInt⟩, ⟨"candidate_max", .TInt⟩]
}

/-
========================================================================
STEP 2: PER-NODE STRUCTURAL DIAGNOSTICS
========================================================================
-/

#eval do
  let g := rlhfSearchGraph
  for node in g.nodes do
    let name := node.name.getD "(unnamed)"
    IO.println s!"\n--- Node {node.id}: \"{name}\" [{repr node.stepType}] ---"
    IO.println s!"  writesConsistent:   {node.writesConsistent}"
    IO.println s!"  reachableFromEntry: {g.reachable g.entry node.id}"
    for rv in node.reads do
      let fromParam := g.parameters.any (fun p =>
        p.name == rv.name && p.type.compatible rv.type)
      let fromPred := g.nodes.any (fun o =>
        o.id != node.id && g.reachable o.id node.id &&
        (!g.isParallelScopedNode o.id || g.isParallelScopedNode node.id) &&
        o.writes.any (fun w => w.name == rv.name && w.type.compatible rv.type))
      let status := if fromParam || fromPred then "✓" else "✗ UNRESOLVED"
      IO.println s!"    read  \"{rv.name}\" ({repr rv.type}): {status}"
    for wv in node.writes do
      IO.println s!"    write \"{wv.name}\" ({repr wv.type})"

/-
========================================================================
STEP 3: GRAPH-LEVEL STRUCTURAL CHECKS
========================================================================
-/

#eval rlhfSearchGraph.allWritesConsistent
#eval rlhfSearchGraph.allReadResolvable
#eval rlhfSearchGraph.edgesValid
#eval rlhfSearchGraph.entryNodeValid
#eval rlhfSearchGraph.exitNodesValid
#eval rlhfSearchGraph.allExitsReachable
#eval rlhfSearchGraph.noOrphanNodes
#eval rlhfSearchGraph.returnType

/-
========================================================================
STEP 4-5: THEOREMS
========================================================================
-/

theorem rlhf_verifiable_rewards_search_2025_2026_writesConsistent : rlhfSearchGraph.allWritesConsistent = true := by native_decide
theorem rlhf_verifiable_rewards_search_2025_2026_readsResolvable : rlhfSearchGraph.allReadResolvable = true := by native_decide
theorem rlhf_verifiable_rewards_search_2025_2026_edgesValid : rlhfSearchGraph.edgesValid = true := by native_decide
theorem rlhf_verifiable_rewards_search_2025_2026_entryValid : rlhfSearchGraph.entryNodeValid = true := by native_decide
theorem rlhf_verifiable_rewards_search_2025_2026_exitsValid : rlhfSearchGraph.exitNodesValid = true := by native_decide
theorem rlhf_verifiable_rewards_search_2025_2026_exitsReachable : rlhfSearchGraph.allExitsReachable = true := by native_decide
theorem rlhf_verifiable_rewards_search_2025_2026_noOrphans : rlhfSearchGraph.noOrphanNodes = true := by native_decide

theorem rlhf_verifiable_rewards_search_2025_2026_seqPath_typeChecks :
    ∃ ctx, typeCheckSequence [rlhfSearch_node0, rlhfSearch_node1, rlhfSearch_node2, rlhfSearch_node3, rlhfSearch_node4, rlhfSearch_node5, rlhfSearch_node6, rlhfSearch_node7] [⟨"query1", .TString⟩, ⟨"query2", .TString⟩, ⟨"query3", .TString⟩, ⟨"query4", .TString⟩, ⟨"start_year", .TInt⟩, ⟨"end_year", .TInt⟩, ⟨"per_query_limit", .TInt⟩, ⟨"arxiv_num_results", .TInt⟩, ⟨"candidate_min", .TInt⟩, ⟨"candidate_max", .TInt⟩] = .ok ctx := by exact ⟨_, rfl⟩

theorem rlhf_verifiable_rewards_search_2025_2026_llmNodeCount : rlhfSearchGraph.llmNodes.length = 6 := by native_decide


end AgenticKernel