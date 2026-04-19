# OptimalScale AIScientist — Web UI

A chat-style web interface for the AI Scientist proposal generation pipeline. Users interact through a multi-turn conversation: provide a research domain and intent, and the system generates a full scientific proposal with downloadable PDF and source files.

---

## Prerequisites

Before deploying the Web UI, make sure:

1. **The sandbox VM is running** (provides the MCP tools used by the agent):
   ```bash
   cd /path/to/controllable-sandbox
   bash ./scripts/run_vm.sh start
   ```

2. **API keys are configured** in `config/vm.env` (at the `controllable-sandbox` project root):
   - `OPENAI_API_KEY` — Required for LLM calls (proposal generation + domain/intent extraction).
   - `FIRECRAWL_API_KEY` — Required for citation search. Get one at [firecrawl.dev](https://firecrawl.dev).

3. **Conda environment `yaml_agent` exists** with the base project dependencies installed:
   ```bash
   conda activate yaml_agent
   pip install -e .   # install controllable-sandbox in dev mode (from project root)
   ```

---

## Installation

All commands below assume you are in the `controllable-sandbox` project root and using the `yaml_agent` conda environment.

### 1. Python Dependencies

```bash
conda activate yaml_agent

# Flask (web framework)
pip install flask

# LiteLLM (used to extract domain & intent from user messages)
pip install litellm
```

### 2. LaTeX Toolchain (for PDF compilation)

The Web UI automatically compiles the generated `.tex` sources into a PDF. This requires a working LaTeX installation:

```bash
sudo apt update

# Base LaTeX + pdflatex/bibtex
sudo apt install -y texlive-latex-base texlive-latex-recommended

# Fonts (PRIMEarxiv.sty requires Times)
sudo apt install -y texlive-fonts-recommended

# Extra packages (algorithm, natbib, booktabs, etc. used by the full pipeline)
sudo apt install -y texlive-science texlive-latex-extra
```

> **Note:** If PDF compilation fails with missing `.sty` or font errors, you may need additional TeX Live packages. Check the server log output for the specific missing package name and install it with `sudo apt install texlive-<package-name>`.

### 3. Verify LaTeX Installation

```bash
pdflatex --version
bibtex --version
```

Both commands should print version information without errors.

---

## Quick Start

### Start the Web UI

From the `controllable-sandbox` project root:

```bash
conda activate yaml_agent
python demo/ai_scientists/web/app.py
```

The server starts at **http://localhost:5001**.

Alternatively, to ensure the correct conda environment is used:

```bash
conda run -n yaml_agent --no-capture-output python demo/ai_scientists/web/app.py
```

### Access the Web UI

Open your browser and navigate to:

```
http://localhost:5001
```

You will see a disclaimer page. After accepting the terms, you can start a conversation to generate a proposal.

---

## How It Works

The Web UI follows a multi-turn chat flow:

| Turn | Role | Action |
|------|------|--------|
| — | Assistant | Greeting: "Hello! I'm OptimalScale AIScientist..." |
| 1 | User | Sends any message |
| 1 | Assistant | Asks for Research Domain and Research Intent |
| 2 | User | Provides domain and intent details |
| 2 | Assistant | Uses LLM to extract domain & intent, confirms, and starts generation |
| — | System | Runs the agent pipeline in background (~25 min for full pipeline) |
| — | Assistant | Shows real-time step-by-step progress |
| — | Assistant | Offers download links for PDF and source ZIP |

---

## Configuration

### Switching Workflows

The Web UI uses the full pipeline by default. To switch, edit `demo/ai_scientists/web/app.py`:

```python
# Full pipeline (~25 min)
BASE_YAML = DEMO_DIR / "ai_scientists.yaml"

# Fast pipeline (~5 min, short proposal)
BASE_YAML = DEMO_DIR / "ai_scientists_fast.yaml"
```

### API Keys

API keys are loaded from `config/vm.env`. The Web UI reads this file at startup. If you update the keys, restart the server.

| Key | Purpose |
|-----|---------|
| `OPENAI_API_KEY` | LLM calls for proposal generation and domain/intent extraction |
| `FIRECRAWL_API_KEY` | Web search for citations and related work |

---

## Output Structure

Each run creates a unique output directory:

```
workspace/outputs/ai_scientists_web_<run_id>/
├── config.txt               # Run configuration
├── agent_run.log            # Detailed execution log
├── agent_events.log         # Structured event log (for progress tracking)
├── thinker/                 # Idea generation outputs
│   ├── step-2-final-ideas.json
│   └── ...
├── writer/                  # Proposal writing outputs
│   └── sections/
│       ├── main.tex
│       ├── abstract.tex
│       ├── introduction.tex
│       ├── related_work.tex
│       ├── method.tex
│       ├── experimental_setup.tex
│       ├── references.bib
│       └── *.json           # Citation metadata
└── artefacts/               # Downloadable files (created by Web UI)
    ├── proposal_sources.zip  # All source files + PRIMEarxiv.sty
    └── proposal.pdf          # Compiled PDF
```

---

## Troubleshooting

### VM not running

```
Error: connection refused on MCP port
```

Make sure the sandbox VM is started:

```bash
bash ./scripts/run_vm.sh start
```

### `firecrawl_search` returns empty results

The Firecrawl search tool writes downloaded content to `/workspace/browser/url_downloads/` inside the sandbox container. If this directory has incorrect permissions, the search will silently return empty results.

**Fix:**

```bash
docker exec -u root sandbox chown -R agent:agent /workspace/browser/url_downloads
```

### PDF compilation fails

- **Missing fonts**: Install `texlive-fonts-recommended`.
- **Missing packages**: Install `texlive-science` and `texlive-latex-extra`.
- **Check logs**: The server prints `[PDF]` prefixed messages showing `pdflatex` and `bibtex` exit codes and output.

### `ModuleNotFoundError: No module named 'flask'`

Install Flask in the active environment:

```bash
conda activate yaml_agent
pip install flask
```

### `litellm.AuthenticationError`

Make sure `OPENAI_API_KEY` is set in `config/vm.env` and restart the server.

### Port 5001 already in use

Kill the existing process:

```bash
lsof -ti:5001 | xargs kill -9
```

Then restart the server.

---

## Dependencies Summary

| Category | Package / Tool | Purpose |
|----------|---------------|---------|
| Python | `flask` | Web framework |
| Python | `litellm` | LLM abstraction for domain/intent extraction |
| Python | `controllable-sandbox` (this project) | Agent runner, MCP client |
| System | `texlive-latex-base` | `pdflatex`, `bibtex` |
| System | `texlive-latex-recommended` | Standard LaTeX packages |
| System | `texlive-fonts-recommended` | Times and other standard fonts |
| System | `texlive-science` | `algorithm`, `algorithmicx` packages |
| System | `texlive-latex-extra` | `natbib`, `booktabs`, and other extras |
| Service | Sandbox VM (Docker) | MCP tools (file system, web search, etc.) |
