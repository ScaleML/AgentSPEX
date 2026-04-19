# SWE-Bench-Verified

This directory contains the benchmark runner for SWE-Bench-Verified. The agent runs inside official pre-built SWE-bench Docker images, with the repo pre-installed at `/testbed`.

## Files

- **run.py** — Main entry point; orchestrates parallel instance processing
- **config.py** — Argument parsing and shared dataclasses (`InstanceResult`, `AgentArgs`)
- **instance.py** — Per-instance logic: customizes the YAML plan, runs the agent, extracts the patch
- **docker_exec_client.py** — `DockerExecClient`: routes `shell_run`/`fs_read`/`fs_write` tool calls through `docker exec`
- **shell_utils.py** — `execute_command_via_shell_run`: wraps the `shell_run` MCP tool with exit-code extraction
- **swe_bench_agent.yaml** — YAML workflow template used by the agent (3-step: reproduce → fix+submit → regression test)

## Prerequisites

- Docker installed and running
- SWE-bench Docker images available (pulled on demand): `swebench/sweb.eval.x86_64.<instance_id>:latest`
- `sb-cli` installed for evaluation: `pip install sb-cli`
- Python dependencies: `pip install -r requirements.txt && pip install -e .`

## Quick Start

Run on a single instance:
```bash
python src/benchmarks/swe_bench_verified/run.py \
    --instance-ids django__django-10880 \
    --model claude-opus-4-6 \
    --save-logs \
    --output-dir outputs/swe_bench_results
```

Run on multiple instances in parallel:
```bash
python src/benchmarks/swe_bench_verified/run.py \
    --instance-ids django__django-10880 django__django-13406 django__django-13410 \
    --model claude-opus-4-6 \
    --max-parallel 4 \
    --save-logs \
    --output-dir outputs/swe_bench_results
```

Run a full dataset split:
```bash
python src/benchmarks/swe_bench_verified/run.py \
    --dataset princeton-nlp/SWE-bench_Verified \
    --model claude-opus-4-6 \
    --max-parallel 8 \
    --no-exclude \
    --save-logs \
    --output-dir outputs/swe_bench_results
```

## How It Works

### 1. Container startup
For each instance, `DockerExecClient` pulls and starts the official SWE-bench image:
```
swebench/sweb.eval.x86_64.<instance_id>:latest
```
The container has the repo pre-installed at `/testbed` with conda env `testbed` active.

### 2. Agent execution
An instance-specific YAML file is created from `swe_bench_agent.yaml` with the following parameters injected:
- `code_path` — `/testbed`
- `problem_statement` — the GitHub issue text from the dataset
- `conda_env_name` — `testbed`
- `instance_id` — for logging and output naming
- `regression_test_cmd` — the repo's pytest command for regression checks

The YAML agent then runs a 3-step workflow:
1. **reproduce** — explores the codebase and creates a minimal reproduction script
2. **fix_and_submit** — implements the fix using shell commands
3. **regression_test** — runs the repo's existing pytest suite and repairs any regressions

### 3. Patch extraction
After the agent finishes, the runner extracts the patch via:
```bash
git reset HEAD . && git add -u && git diff --cached
```
This captures only modifications to tracked files, which is what the SWE-bench evaluation harness expects.

### 4. Output
- `predictions.jsonl` — patches in SWE-bench submission format (one JSON object per line)
- `{instance_id}.diff` — individual patch file per instance
- `{instance_id}_agent_events.log` — structured agent event log (viewable in the dashboard)
- `{instance_id}_full.log` — full console output per instance (with `--save-logs`)

## Evaluating with sb-cli

After a run completes, submit `predictions.jsonl` to the SWE-bench leaderboard using `sb-cli`.

### Install sb-cli
```bash
pip install sb-cli
```

### Submit predictions
```bash
sb-cli submit swe-bench_verified test \
    --predictions_path outputs/swe_bench_results/predictions.jsonl \
    --run_id <your-run-id>
```

The `run_id` is a label you choose to identify this submission (e.g. `claude-opus-4-6-run-1`).

### Check status and list runs
```bash
sb-cli list-runs swe-bench_verified test
```

### Download the report
```bash
sb-cli get-report swe-bench_verified test <your-run-id> -o ./reports
```

The report directory will contain a JSON summary with per-instance pass/fail results and an overall resolve rate.

## Command Line Options

| Flag | Default | Description |
|---|---|---|
| `--dataset` | `princeton-nlp/SWE-bench_Verified` | HuggingFace dataset to use |
| `--split` | `test` | Dataset split |
| `--instance-ids` | _(all)_ | One or more specific instance IDs to run |
| `--model` | `gpt-5` | Model name passed to the YAML agent |
| `--workflow-file` | `swe_bench_agent.yaml` | Path to the YAML workflow template |
| `--output-dir` | `outputs/swe_bench_results` | Directory for predictions, diffs, and logs |
| `--max-parallel` | `1` | Number of instances to run concurrently |
| `--limit` | _(none)_ | Cap the number of instances processed |
| `--no-exclude` | `false` | Ignore `excluded_instances.txt` |
| `--exclude-file` | `excluded_instances.txt` | Path to exclusion list |
| `--save-logs` | `false` | Save full console output per instance |
| `--dashboard` | `false` | Launch the live agent dashboard |
| `--dashboard-port` | `5050` | Dashboard port |
| `--dashboard-no-browser` | `false` | Don't auto-open the dashboard in a browser |
| `--dashboard-keep` | `false` | Keep dashboard running after the run completes |

## See Also

- [SWE-Bench GitHub](https://github.com/SWE-bench/SWE-bench)
- [SWE-Bench-Verified Dataset](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified)
