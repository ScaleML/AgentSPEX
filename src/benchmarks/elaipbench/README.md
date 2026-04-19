# ELAIPBench Benchmark

Evaluates agents on academic paper question answering -- 403 multiple-choice questions grounded in research paper passages. Based on [ELAIPBench](https://huggingface.co/datasets/KangKang625/ELAIPBench), the dataset for the CCKS 2025 Academic Paper Question Answering Challenge.

## Quick Start

```bash
# Setup API KEY (for OpenAI models)
export OPENAI_API_KEY="YOUR_API_KEY"

# Run all 403 questions (uses model from workflow YAML, default: gpt-5)
python src/benchmarks/elaipbench/run.py

# Run 10 questions
python src/benchmarks/elaipbench/run.py --limit 10

# Run only single-answer questions (88 questions)
python src/benchmarks/elaipbench/run.py --question-type SA-MCQ

# Run only multi-answer questions (315 questions)
python src/benchmarks/elaipbench/run.py --question-type MA-MCQ

# Run with 8 parallel workers
python src/benchmarks/elaipbench/run.py --max-parallel 8

# Run specific questions by ID
python src/benchmarks/elaipbench/run.py --question-ids 0 5 10
```

To change the model used for this benchmark, edit the `config.model` field in the workflow YAML file (`elaipbench_agent.yaml` by default). The YAML config is the authoritative source for model selection -- each workflow file (and its sub-modules) controls its own model independently.

## Pipeline

1. **Load** -- Downloads questions from HuggingFace (`KangKang625/ELAIPBench`). Each question includes the full paper content and a relevant passage as context. When `--limit` is set, questions are randomly sampled (not sliced).

2. **Agent Workflow** -- For each question, a YAML-driven agentic workflow runs through multiple phases:
   - **Skim Paper Structure** -- Identifies title, abstract summary, and section headings from the paper
   - **Analyze Question** -- Extracts keywords, core claim, and question type (single/multi-answer) from the question stem without looking at options
   - **Extract Evidence** -- Locates up to 5 verbatim evidence snippets from the paper relevant to the claim
   - **Evaluate Options** -- Independently judges each option (A/B/C/D) as supported, contradicted, or not established based on the evidence
   - **Recheck (MA-MCQ only)** -- If fewer than 2 options were selected for a multi-answer question, reconsiders with a more lenient standard (up to 2 retries)
   - **Finalize** -- Produces the final answer in the required format

3. **Evaluate** -- Parses the agent's answer letter(s) via regex and compares to ground truth via exact match. Reports accuracy overall and per question type.

## Question Types

| Type | Count | Description | Answer Format |
|------|-------|-------------|---------------|
| SA-MCQ | 88 | Single-answer multiple choice | Single letter, e.g. `B` |
| MA-MCQ | 315 | Multi-answer multiple choice | Multiple letters, e.g. `ABC` |

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | workflow config | Fallback model if the YAML workflow has no `config.model`. To change the model, edit the `config.model` field in the workflow YAML file instead. |
| `--output-dir` | `outputs/elaipbench_<timestamp>` | Results directory |
| `--max-parallel` | `1` | Parallel query workers |
| `--limit` | all | Max questions to process (randomly sampled) |
| `--question-ids` | all | Specific question indices to run |
| `--question-type` | all | Filter by `SA-MCQ` or `MA-MCQ` |
| `--workflow-file` | `elaipbench_agent.yaml` | Agent YAML workflow |
| `--skip-eval` | `false` | Skip evaluation after running queries |

## Output Structure

```
outputs/elaipbench_<timestamp>/
├── runs/
│   ├── 0.json                        # Per-question result (answer, correctness, usage)
│   ├── 1.json
│   ├── ...
│   ├── question_0.yaml               # Per-question YAML config (auto-generated)
│   ├── question_1.yaml
│   ├── ...
│   └── logs/
│       ├── question_0/
│       │   ├── agent_run.log         # Full agent log
│       │   ├── agent_events.log      # Structured agent events
│       │   ├── trace.jsonl           # Agent trace (structured events in JSONL)
│       │   ├── checkpoint.json       # Agent checkpoint state
│       │   ├── final-output.txt      # Final agent output
│       │   ├── step-1-output.txt     # Skim paper structure output
│       │   ├── step-2-output.txt     # Analyze question output
│       │   ├── step-3-output.txt     # Extract evidence output
│       │   ├── step-4-output.txt     # Evaluate options output
│       │   ├── submodule_4.else.1/   # Conditional branch logs (SA-MCQ/MA-MCQ)
│       │   │   ├── step-1-output.txt
│       │   │   └── ...
│       │   └── reproducibility/      # Snapshot for reproducing the run
│       │       ├── workflow_snapshot.yaml
│       │       ├── run_config.env
│       │       ├── git_HEAD.txt
│       │       ├── git_diff.patch
│       │       └── ...
│       ├── question_1/
│       └── ...
└── evals/
    └── evaluation_summary.json       # Aggregated accuracy + per-type breakdown
```

Each `<id>.json` result file contains:
- `question_id`, `question`, `question_type`, `paper_id`
- `correct_answer` -- ground truth (e.g. `"B"` or `"ABC"`)
- `parsed_answer` -- extracted answer from agent response
- `is_correct` -- whether parsed answer matches ground truth
- `response` -- full agent response text
- `status` -- `"completed"` or `"failed"`
- `usage` -- token usage statistics

## Evaluation Metrics

The evaluation summary (`evaluation_summary.json`) contains:

- `accuracy` -- Fraction of correctly answered questions (exact match)
- `type_accuracy` -- Per-type accuracy breakdown (SA-MCQ vs MA-MCQ)
- `total_completed` / `total_failed` -- Question counts by status
- `correct` -- Number of correct answers
- `correct_ids` / `wrong_ids` / `failed_ids` -- Question ID lists for each category
- `usage` -- Aggregated token usage (`input_tokens`, `output_tokens`, `reasoning_tokens`, `cost`)
- `evaluation_date` -- Date of the evaluation run

## Environment Variables

- `OPENAI_API_KEY` -- Required if using OpenAI models
- `ANTHROPIC_API_KEY` -- Required if using Anthropic models (Claude)