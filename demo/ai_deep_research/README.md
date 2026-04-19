# AI Deep Research

AI Deep Research is an AI-powered pipeline for conducting comprehensive web-based research on any topic. It combines **interactive clarification**, **parallel deep exploration**, and **report synthesis** into an end-to-end automated research workflow.

The pipeline uses a breadth-first search (BFS) strategy to explore topics at configurable depth and breadth, with parallel processing at multiple levels for efficient research.

---

## Pipeline Overview

The research pipeline operates in three phases:

1. **Interactive Clarification**: Generates follow-up questions to clarify the research direction, then combines user answers with the initial query
2. **Parallel Deep Research**: BFS-style exploration with parallel SERP queries and content processing at each depth level
3. **Final Report Generation**: Synthesizes all accumulated learnings into a comprehensive markdown report (4000+ words)

```
User Query
    |
    v
[Phase 1: Interactive Clarification]
    |-- Generate clarification questions
    |-- Collect user answers
    |-- Create enhanced combined query
    |
    v
[Phase 2: Parallel Deep Research] (BFS Tree)
    |
    |-- Depth 1: Process user queries in parallel
    |       |-- Generate SERP queries (breadth=4)
    |       |-- Parallel web search
    |       |-- Parallel content learning extraction
    |       |-- Generate follow-up questions
    |
    |-- Depth 2: Process follow-ups in parallel
    |       |-- (breadth=2, halved from previous)
    |       |-- ...
    |
    v
[Phase 3: Final Report Generation]
    |-- Aggregate all learnings
    |-- Generate comprehensive markdown report
    |-- Include all source URLs
```

---

## Performance Summary

| Model | Avg. Time | Tokens | Est. Cost | Sample Output |               |
|---------------|-------|-----------|--------|-----------|---------------|
| o3-mini | ~15 min | ~500K | ~$0.10 | [final_report.md](assets/final_report.md) |

*Cost and token counts are approximate and depend on API pricing, topic complexity, and search results.*

---

## Quick Start

### Prerequisites

1. **Start the VM** (required for all workflows):
   ```bash
   bash ./scripts/run_vm.sh start
   ```

2. **Set your API keys** in `config/vm.env` (at the AgentSPEX project root):
   - **OPENAI_API_KEY** — Required for LLM calls
   - **FIRECRAWL_API_KEY** — Required for web search. Get one at [Firecrawl](https://firecrawl.dev)

### Run the Demo

From the project root:

```bash
bash ./scripts/run_agent.sh demo/ai_deep_research/deep_research_main.yaml
```

- **Typical runtime**: 15-20 minutes (with o3-mini)
- **Output**: Comprehensive research report at `workspace/outputs/deep_research_parallel_comprehensive_report/final_report.md`
- **Sample output**: [Sample final report](assets/final_report.md)

---

## Parameters and Configuration

### Where to Set Parameters

Parameters are defined in `deep_research_main.yaml`.

| Setting | Where to Set | Description |
|---------|--------------|-------------|
| **model** | YAML `config.model` | The LLM used for the workflow (default: `o3-mini`) |
| **topic** | YAML `parameters.topic` | The research topic/query |
| **initial_breadth** | YAML `parameters.initial_breadth` | Number of SERP queries per user query at depth 1 (default: 4) |
| **max_depth** | YAML `parameters.max_depth` | Maximum depth of BFS exploration (default: 2) |
| **memory_file** | YAML `parameters.memory_file` | Path to episodic memory JSON file |
| **max_user_query_workers** | YAML `parameters.max_user_query_workers` | Parallel workers for user queries (default: 8) |
| **max_serp_workers** | YAML `parameters.max_serp_workers` | Parallel workers for SERP queries (default: 4) |
| **max_content_workers** | YAML `parameters.max_content_workers` | Parallel workers for content processing (default: 5) |

### Example: Custom Topic

Edit `deep_research_main.yaml`:

```yaml
parameters:
    topic: "quantum computing applications in drug discovery"
    initial_breadth: 4    # More breadth for broader coverage
    max_depth: 3          # Deeper exploration
```

### Parallelism Configuration

The pipeline supports three levels of parallelism:

1. **User Query Level**: Multiple user queries processed simultaneously
2. **SERP Query Level**: Multiple search queries per user query
3. **Content Level**: Multiple web pages processed in parallel

Adjust `max_*_workers` parameters based on your API rate limits and system resources.

---

## Output Files and Structure

```
workspace/outputs/deep_research_parallel_comprehensive_report/
├── agent_run.log                 # Main workflow log
├── step-*-output.txt             # Step outputs
├── submodule-*/                   # Submodule outputs dir
├── final-output.txt              # Final step output
├── episodic.json                 # Memory file with all learnings
└── final_report.md               # Generated comprehensive report
```

### Key Output Files

| File | Description |
|------|-------------|
| `final_report.md` | The comprehensive research report (4000+ words) |
| `episodic.json` | Memory file containing all learnings and sources |
| `agent_run.log` | Detailed execution log |

---

## Module Architecture

The pipeline consists of 4 YAML modules:

| Module | Purpose |
|--------|---------|
| `deep_research_main.yaml` | Main orchestration: clarification, BFS loop, report generation |
| `modules/process_user_query.yaml` | Process a single user query, generate SERP queries |
| `modules/process_serp_query.yaml` | Execute web search, extract learnings, generate follow-ups |
| `modules/extract_content_learnings.yaml` | Extract learnings from a single web page content |
| `modules/web_search.yaml` | Firecrawl web search wrapper |

---

## Troubleshooting

### VM not running

Ensure the VM is started before running the agent:

```bash
bash ./scripts/run_vm.sh start
```

### Firecrawl API errors

- Verify your `FIRECRAWL_API_KEY` is set correctly in `config/vm.env`
- Check your Firecrawl API quota and rate limits

### Memory file errors

- Ensure the output directory exists and is writable
- Check that `memory_file` path in the YAML is correct

### Report generation fails

- Check the Logging Dashboard or `agent_run.log` for detailed error messages
- Ensure all search queries returned results
- Try reducing `initial_breadth` or `max_depth` for smaller runs