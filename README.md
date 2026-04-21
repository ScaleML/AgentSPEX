# AgentSPEX: An Agent SPecification and EXecution Language

A declarative workflow language for LLM-agent pipelines with explicit control flow, modular structure, and a customizable execution harness.

This is the official implementation accompanying the paper [*AgentSPEX: An Agent SPecification and EXecution Language*](https://arxiv.org/abs/2604.13346v1). Visit the official website at [agentspex.ai](https://agentspex.ai/) to try free demos.

See the [Workflow Language Guide](docs/workflow-language.md) for full syntax, step types, and examples.

## Quick start

### 1. Install dependencies

Create a conda environment and install the package:

```bash
conda create -n agentspex python=3.11 -y
conda activate agentspex
pip install -r requirements.txt
pip install -e .
```

### 2. Set up API keys

```bash
cp example.env .env
```

### 3. Quickstart

Run:
```bash
agentspex
```

Arrow-key navigation lets you run workflows, write task plans, browse docs, manage integrations, and control the sandbox VM — all without remembering CLI flags.

Or run directly:

```bash
agentspex run workflows/quickstart.yaml
agentspex run workflows/quickstart.yaml --model claude-opus-4-6
agentspex run --help
```

Each `agentspex run` spins up an isolated container for the duration of the workflow and tears it down on exit.

For repeated runs or a **persistent VM**:

```bash
docker build -t agentspex-sandbox:latest -f config/Dockerfile .
bash ./scripts/run_vm.sh start
bash ./scripts/run_agent.sh workflows/quickstart.yaml
```

Default VNC and MCP endpoints are printed on start. Stop with `bash ./scripts/run_vm.sh stop`.

## Writing workflows

Workflows are YAML files that define a sequence of steps. A minimal example:

```yaml
name: "hello_world"
goal: "A simple task to demonstrate the basics"

workflow:
  - step:
      name: "greet"
      instruction: "Say hello in a friendly way"
```

Workflows support parameters, template variables, loops, conditionals, parallel execution, sub-workflows, and more. See the [Workflow Language Guide](docs/workflow-language.md) for the complete reference. Example workflows are in `workflows/`.

## Where runs land

Every run — whether via `agentspex`, `agentspex run`, `agentspex cli`, or `bash scripts/run_agent.sh` — writes all logs, checkpoints, traces, step outputs, and reproducibility snapshots to:

```
workspace_persistent/outputs/<task_name>_<YYYYMMDD-HHMMSS>/
```

`workspace/` is the host directory mounted as `/workspace` inside the container; it holds the agent's live working files. `workspace_persistent/` is host-only and gitignored. Paths are derived from the project root, so the default works from any cwd without extra setup. Re-running the same workflow creates a new timestamped directory; `--resume` picks up the most recent one.

### Writing a run-scoped workflow

Before parsing any workflow YAML, the harness exports these env vars:

| Variable | Example |
|---|---|
| `AGENTSPEX_RUN_ID` | `GUIDE_fast_demo_20260418-091530` |
| `AGENTSPEX_RUN_SANDBOX_DIR` | `outputs/GUIDE_fast_demo_20260418-091530` |
| `AGENTSPEX_RUN_SANDBOX_DIR_ABS` | `/workspace/outputs/GUIDE_fast_demo_20260418-091530` |
| `AGENTSPEX_RUN_HOST_DIR` | `<project>/workspace_persistent/outputs/GUIDE_fast_demo_20260418-091530` |

Reference them directly in YAML so each run gets its own dir:

```yaml
parameters:
  output_dir: "${AGENTSPEX_RUN_SANDBOX_DIR_ABS}"
  memory_file: "${AGENTSPEX_RUN_SANDBOX_DIR_ABS}/memory.json"
```

This makes memory files, downloaded artifacts, and any run-specific outputs land inside the same timestamped directory as the logs and checkpoints — no `.env` file required.

## Options

### Custom output directory

```bash
agentspex run workflows/quickstart.yaml --output_dir /path/to/output
# or with the persistent VM:
bash ./scripts/run_agent.sh workflows/quickstart.yaml --output_dir /path/to/output
```

### Resume from checkpoint

```bash
agentspex run workflows/quickstart.yaml --resume
```

### Replay from trace (no real tool calls)

```bash
bash ./scripts/run_agent.sh workflows/quickstart.yaml --replay_trace /path/to/trace.jsonl
```

## Live dashboard

The agent streams structured events to a live dashboard that opens automatically when using `run_agent.sh`. To open it manually against any event log:

```bash
python scripts/dashboard.py /path/to/agent_events.log
```

Options: `--port 5050`, `--host 127.0.0.1`, `--no-browser`, `--no-auto-close`.

## Sandbox VM

The sandbox VM provides the tools that workflows interact with. Source code is in `src/sandbox_vm/`.

### Adding custom tools

1. Add tool functions under `src/sandbox_vm/tools/`
2. Register in `src/sandbox_vm/tools/mcp_server_tool_config.yaml`
3. Public functions (not `_`-prefixed) are auto-registered as MCP tools

### Environment variables

Set in `config/vm.env`. `$HOST_WORKSPACE` is mounted at `$VM_WORKSPACE` inside the VM.

## Project structure

```
workflows/           Workflow definitions (YAML)
src/harness/         Workflow execution engine
src/sandbox_vm/      Sandbox VM and MCP server
src/mcp_client/      MCP client library
docs/                Documentation
scripts/             Shell scripts and dashboard
config/              Environment and Docker configuration
```

## License

The code included in this project is licensed under the [Apache 2.0 license](LICENSE).
