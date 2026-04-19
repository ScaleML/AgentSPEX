"""AI Scientists Web UI — Flask backend.

A chat-style web interface that wraps the controllable-sandbox agent runner.
Users interact via a multi-turn conversation: the assistant asks for domain
and intent, uses an LLM to extract them, then runs the fast pipeline.
On completion, a .zip of sources and a compiled .pdf are offered for download.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request, send_file

# ---------------------------------------------------------------------------
# Load environment from config/vm.env (so OPENAI_API_KEY etc. are available)
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> None:
    """Source a KEY=VALUE env file into os.environ (skip comments/blanks)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and not os.environ.get(key):
            os.environ[key] = value


# Pre-resolve PROJECT_ROOT so we can find vm.env
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT_EARLY = _THIS_DIR.parent.parent.parent
_load_env_file(_PROJECT_ROOT_EARLY / "config" / "vm.env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WEB_DIR = Path(__file__).resolve().parent
DEMO_DIR = WEB_DIR.parent                             # demo/ai_scientists/
PROJECT_ROOT = DEMO_DIR.parent.parent                  # controllable-sandbox/
BASE_YAML = DEMO_DIR / "ai_scientists.yaml"
PRIMEARXIV_STY = DEMO_DIR / "PRIMEarxiv.sty"
RUN_AGENT_SH = PROJECT_ROOT / "scripts" / "run_agent.sh"

HOST_OUTPUTS_DIR = PROJECT_ROOT / "outputs"
WORKSPACE_OUTPUTS_DIR = PROJECT_ROOT / "workspace" / "outputs"

# ---------------------------------------------------------------------------
# LLM helper — extract domain & intent from free-form user text
# ---------------------------------------------------------------------------

RELEVANCE_SYSTEM_PROMPT = (
    "You are OptimalScale AI Scientist, a tool that generates scientific research proposals. "
    "The user just sent you a message. Determine if the message is related to requesting "
    "a research proposal, discussing a research topic, or expressing intent to use this tool.\n\n"
    "Return ONLY valid JSON with one key:\n"
    '  "relevant": true or false\n\n'
    "Examples of RELEVANT messages: \"I want to write a proposal about NLP\", "
    "\"bioinformatics\", \"help me generate a proposal\", \"hello\", \"hi\", \"let's start\", "
    "\"I need a research proposal\", \"yes\", \"sure\", \"ok\".\n"
    "Examples of IRRELEVANT messages: \"I had a bad day\", \"what's the weather\", "
    "\"tell me a joke\", \"who won the game\", \"how do I cook pasta\".\n\n"
    "Simple greetings and affirmatives are RELEVANT."
)

EXTRACT_SYSTEM_PROMPT = (
    "You are a helpful assistant. The user will describe a research topic in "
    "natural language. Your job is to extract exactly two fields:\n"
    '  1. "domain" — a short research domain label (e.g. "bioinformatics", "NLP", "computer vision")\n'
    '  2. "intent" — a one-sentence research intent describing the goal\n\n'
    "Return ONLY valid JSON with these two keys, no markdown, no explanation.\n"
    'Example: {"domain": "bioinformatics", "intent": "Develop generative models for de novo molecular design"}'
)


def _extract_domain_intent(user_text: str) -> Dict[str, str]:
    """Call the LLM to extract domain and intent from user text.

    Returns {"domain": "...", "intent": "..."} or raises on failure.
    Uses litellm (already available in the project environment).
    """
    import litellm

    resp = litellm.completion(
        model="openai/gpt-4.1-mini",
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        temperature=0.0,
        timeout=30,
    )
    raw = (resp.choices[0].message.content or "").strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    data = json.loads(raw)
    domain = (data.get("domain") or "").strip()
    intent = (data.get("intent") or "").strip()
    if not domain or not intent:
        raise ValueError("LLM returned empty domain or intent")
    return {"domain": domain, "intent": intent}


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

@dataclass
class RunState:
    """Tracks one agent run."""
    run_id: str
    domain: str
    intent: str
    task_name: str
    yaml_path: str
    process: Optional[subprocess.Popen] = None
    event_log_path: Optional[str] = None
    workspace_output_dir: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "starting"
    error: Optional[str] = None
    started_at: float = 0.0
    # Paths to downloadable artefacts (set after completion)
    zip_path: Optional[str] = None
    pdf_path: Optional[str] = None


RUNS: Dict[str, RunState] = {}

# ---------------------------------------------------------------------------
# YAML templating
# ---------------------------------------------------------------------------

def _create_run_yaml(run_id: str, domain: str, intent: str) -> tuple[str, str]:
    """Create a per-run YAML from the base template, patching domain, intent & paths."""
    base_text = BASE_YAML.read_text(encoding="utf-8")

    task_name = f"ai_scientists_web_{run_id[:8]}"
    output_dir = f"/workspace/outputs/{task_name}"

    patched = re.sub(
        r'^(name:\s*)".+"', f'\\1"{task_name}"',
        base_text, count=1, flags=re.MULTILINE,
    )
    patched = re.sub(
        r'^(\s*domain:\s*)".+"', f'\\1"{domain}"',
        patched, count=1, flags=re.MULTILINE,
    )
    patched = re.sub(
        r'^(\s*intent:\s*)".+"', f'\\1"{intent}"',
        patched, count=1, flags=re.MULTILINE,
    )
    patched = re.sub(
        r'^(\s*output_dir:\s*)".+"', f'\\1"{output_dir}"',
        patched, count=1, flags=re.MULTILINE,
    )
    # Patch memory_file to use the run-specific output dir (full YAML only)
    patched = re.sub(
        r'^(\s*memory_file:\s*)".+"',
        f'\\1"{output_dir}/writer/memory.json"',
        patched, count=1, flags=re.MULTILINE,
    )

    run_dir = PROJECT_ROOT / "outputs" / "_ui_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = run_dir / f"{task_name}.yaml"
    yaml_path.write_text(patched, encoding="utf-8")
    return str(yaml_path), task_name


# ---------------------------------------------------------------------------
# Event-log parser
# ---------------------------------------------------------------------------

FRIENDLY_NAMES: Dict[str, str] = {
    "setup_environment": "Setting up environment",
    "check_idea_generation": "Verifying generated ideas",
    "skip_paper_writing": "Proposal writing skipped",
}

MODULE_FRIENDLY: List[tuple[str, str]] = [
    ("thinker_fast", "Generating ideas (fast mode)"),
    ("thinker", "Running safety check & idea generation"),
    ("writer_costefficiency", "Writing proposal (cost-efficient)"),
    ("writer_fast", "Writing proposal (fast mode)"),
    ("writer", "Writing proposal"),
]

WRITER_STEP_FRIENDLY: Dict[str, str] = {
    "write_abstract": "Writing Abstract",
    "write_introduction": "Writing Introduction",
    "write_related_work": "Writing Related Work",
    "write_method": "Writing Method",
    "write_experimental_setup": "Writing Experimental Setup",
    "search_citations": "Searching citations",
    "extract_single_citation": "Extracting citation",
    "save_references": "Saving references",
    "compile_latex": "Compiling LaTeX",
}

EVENT_RE = re.compile(r"<<<EVENT>>>(.*?)<<</EVENT>>>")
RUN_LOG_STEP_RE = re.compile(
    r"==== (?:Executing(?:\s+\w+)? step|Calling sub-module)\s+([\d.]+(?:\.then\.\d+)?)\s*:\s*(.+?)\s*===="
)


def _friendly_step_name(raw_name: str, module_path: str = "") -> str:
    if raw_name in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[raw_name]
    if raw_name in WRITER_STEP_FRIENDLY:
        return WRITER_STEP_FRIENDLY[raw_name]
    if module_path:
        for fragment, label in MODULE_FRIENDLY:
            if fragment in module_path:
                return label
    return raw_name.replace("_", " ").title()


def _build_step_name_map(run_log_path: str) -> Dict[str, str]:
    name_map: Dict[str, str] = {}
    if not os.path.isfile(run_log_path):
        return name_map
    try:
        with open(run_log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                m = RUN_LOG_STEP_RE.search(line)
                if m:
                    name_map[m.group(1).strip()] = m.group(2).strip()
    except Exception:
        pass
    return name_map


def _parse_events(event_log_path: str) -> tuple[str, List[Dict[str, Any]]]:
    if not os.path.isfile(event_log_path):
        return "starting", []

    run_log_path = os.path.join(os.path.dirname(event_log_path), "agent_run.log")
    name_map = _build_step_name_map(run_log_path)

    steps: Dict[str, Dict[str, Any]] = {}
    overall_status = "running"

    try:
        with open(event_log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                for m in EVENT_RE.finditer(line):
                    try:
                        ev = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        continue
                    etype = ev.get("type", "")
                    data = ev.get("data", {})

                    if etype == "step_start":
                        sid = data.get("step_id", "")
                        name = data.get("name", "") or name_map.get(sid, "") or f"Step {sid}"
                        steps[sid] = {
                            "id": sid, "name": name,
                            "friendly_name": _friendly_step_name(name),
                            "status": "running",
                            "depth": data.get("depth", 0),
                        }
                    elif etype == "module_start":
                        sid = data.get("step_id", "")
                        mod_path = data.get("path", "")
                        if sid in steps:
                            if not steps[sid]["name"] or steps[sid]["name"].startswith("Step "):
                                steps[sid]["name"] = name_map.get(sid, mod_path)
                            steps[sid]["friendly_name"] = _friendly_step_name(
                                steps[sid]["name"], mod_path)
                    elif etype == "step_end":
                        sid = data.get("step_id", "")
                        if sid in steps:
                            steps[sid]["status"] = data.get("status", "completed")
                    elif etype == "workflow_end":
                        overall_status = "completed"
                    elif etype == "error":
                        overall_status = "failed"
    except Exception:
        pass

    ordered = sorted(steps.values(), key=lambda s: s["id"])
    visible = [s for s in ordered if s.get("depth", 0) <= 1]
    return overall_status, visible


# ---------------------------------------------------------------------------
# Post-processing: zip + pdf
# ---------------------------------------------------------------------------

def _build_zip(sections_dir: Path, dest_path: Path) -> None:
    """Create a zip of writer/sections/ contents plus PRIMEarxiv.sty.

    Does NOT modify the original sections directory (which may be
    read-only / owned by the sandbox VM user).
    """
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if sections_dir.is_dir():
            for f in sorted(sections_dir.iterdir()):
                if f.is_file():
                    zf.write(f, f.name)
        # Always include PRIMEarxiv.sty from the demo source
        if PRIMEARXIV_STY.is_file():
            zf.write(PRIMEARXIV_STY, PRIMEARXIV_STY.name)


def _compile_pdf(sections_dir: Path) -> Optional[Path]:
    """Compile main.tex to PDF using pdflatex + bibtex.

    main.tex typically references ``\\input{sections/abstract}`` etc., so we
    recreate the expected directory layout inside a temp folder:

        tmp/
          main.tex
          PRIMEarxiv.sty
          *.bib            (if any, at top level)
          sections/
            abstract.tex
            ...

    Returns the path to the resulting PDF (or None on failure).
    """
    main_tex = sections_dir / "main.tex"
    if not main_tex.is_file():
        print(f"[PDF] No main.tex found in {sections_dir}")
        return None

    tmp = Path(tempfile.mkdtemp(prefix="aiscientists_pdf_"))
    try:
        # main.tex and .sty go at the top level
        shutil.copy2(main_tex, tmp / "main.tex")
        # Always use PRIMEarxiv.sty from demo source (sections dir may be read-only)
        if PRIMEARXIV_STY.is_file():
            shutil.copy2(PRIMEARXIV_STY, tmp / "PRIMEarxiv.sty")

        # Everything else goes into sections/ (matching \input{sections/...})
        sub = tmp / "sections"
        sub.mkdir()
        for f in sections_dir.iterdir():
            if f.is_file() and f.name != "main.tex":
                shutil.copy2(f, sub / f.name)

        # Also copy .bib files to top level as fallback for bibtex
        for bib in sections_dir.glob("*.bib"):
            shutil.copy2(bib, tmp / bib.name)

        def _run(cmd: list[str]) -> subprocess.CompletedProcess:
            r = subprocess.run(
                cmd, cwd=str(tmp),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
            )
            return r

        # pdflatex pass 1
        r1 = _run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
        print(f"[PDF] pdflatex pass 1 exit={r1.returncode}")

        # bibtex (if any .bib exists at top level or in sections/)
        bib_files = list(tmp.glob("*.bib")) + list(sub.glob("*.bib"))
        if bib_files:
            rb = _run(["bibtex", "main"])
            print(f"[PDF] bibtex exit={rb.returncode}")

        # pdflatex pass 2 & 3
        _run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
        _run(["pdflatex", "-interaction=nonstopmode", "main.tex"])

        pdf = tmp / "main.pdf"
        if pdf.is_file():
            print(f"[PDF] Success: {pdf} ({pdf.stat().st_size} bytes)")
            return pdf
        else:
            # Log last 500 chars of pdflatex output for debugging
            out_tail = (r1.stdout or b"").decode("utf-8", errors="replace")[-500:]
            print(f"[PDF] main.pdf not produced. pdflatex tail:\n{out_tail}")
    except Exception as exc:
        print(f"[PDF] Exception during compilation: {exc}")
    return None


def _post_process(run: RunState) -> None:
    """Prepare sections, build zip, and compile PDF after a successful run."""
    sections_dir = Path(run.workspace_output_dir) / "writer" / "sections"
    artefact_dir = HOST_OUTPUTS_DIR / run.task_name / "artefacts"
    artefact_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Zip the sections directory + PRIMEarxiv.sty
    zip_path = artefact_dir / "proposal_sources.zip"
    _build_zip(sections_dir, zip_path)
    run.zip_path = str(zip_path)
    print(f"[POST] ZIP created: {zip_path}")

    # Step 2: Compile PDF
    pdf_tmp = _compile_pdf(sections_dir)
    if pdf_tmp:
        pdf_dest = artefact_dir / "proposal.pdf"
        shutil.copy2(pdf_tmp, pdf_dest)
        run.pdf_path = str(pdf_dest)
        print(f"[POST] PDF saved: {pdf_dest}")
        try:
            shutil.rmtree(pdf_tmp.parent, ignore_errors=True)
        except Exception:
            pass
    else:
        print("[POST] PDF compilation failed or main.tex missing.")


# ---------------------------------------------------------------------------
# (Section-level result collection removed — frontend only offers downloads)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

def _detect_conda_env() -> Optional[str]:
    return os.environ.get("CONDA_DEFAULT_ENV") or None


_CONDA_ENV: Optional[str] = _detect_conda_env()


def _run_agent_background(run: RunState) -> None:
    env = os.environ.copy()
    env["CS_DASHBOARD_NO_BROWSER"] = "1"
    src_dir = str(PROJECT_ROOT / "src")
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")

    agent_cmd = f"bash {RUN_AGENT_SH} {run.yaml_path} --no_dashboard"
    if _CONDA_ENV:
        shell_cmd = f"conda run -n {_CONDA_ENV} --no-capture-output {agent_cmd}"
    else:
        shell_cmd = agent_cmd

    try:
        proc = subprocess.Popen(
            shell_cmd, shell=True, cwd=str(PROJECT_ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        run.process = proc

        host_log_dir = HOST_OUTPUTS_DIR / run.task_name
        run.event_log_path = str(host_log_dir / "agent_events.log")
        run.workspace_output_dir = str(WORKSPACE_OUTPUTS_DIR / run.task_name)
        run.status = "running"

        stdout_lines: list[str] = []
        if proc.stdout:
            for raw_line in proc.stdout:
                stdout_lines.append(raw_line.decode("utf-8", errors="replace"))

        proc.wait()
        final_status, _ = _parse_events(run.event_log_path)

        if final_status == "completed":
            # Keep status as "running" while post-processing so the frontend
            # does not fetch results before artefacts are ready.
            run.status = "post_processing"
            try:
                _post_process(run)
            except Exception as post_exc:
                import traceback
                traceback.print_exc()
                print(f"[POST] Post-processing error: {post_exc}")
            # Mark completed only AFTER zip/pdf are built
            run.status = "completed"
        elif proc.returncode != 0:
            run.status = "failed"
            tail = "".join(stdout_lines[-20:]).strip()
            run.error = f"Agent exited with code {proc.returncode}.\n{tail}"
        else:
            if final_status == "running":
                run.status = "failed"
                run.error = "Agent exited without completing the workflow."
            else:
                run.status = "failed"
                tail = "".join(stdout_lines[-20:]).strip()
                run.error = f"Agent produced no output.\n{tail}" if tail else "Agent produced no output."

    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/check_relevance", methods=["POST"])
def api_check_relevance():
    """Check if user's first message is relevant to proposal generation."""
    body = request.get_json(force=True)
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        return jsonify({"relevant": True})

    try:
        import litellm
        resp = litellm.completion(
            model="openai/gpt-4.1-mini",
            messages=[
                {"role": "system", "content": RELEVANCE_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            timeout=15,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        return jsonify({"relevant": bool(data.get("relevant", True))})
    except Exception:
        return jsonify({"relevant": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """LLM-powered chat endpoint to extract domain & intent.

    Expects ``{"message": "user text"}``.
    Returns ``{"reply": "...", "domain": "...", "intent": "..."}``
    where domain/intent are non-empty only when extraction succeeds.
    """
    body = request.get_json(force=True)
    user_msg = (body.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "message is required"}), 400

    try:
        extracted = _extract_domain_intent(user_msg)
        domain = extracted["domain"]
        intent = extracted["intent"]
        reply = (
            f'Great! I will generate the proposal with domain **"{domain}"** '
            f'and intent **"{intent}"**.\n\n'
            "Starting generation now..."
        )
        return jsonify({"reply": reply, "domain": domain, "intent": intent})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"[CHAT] Extraction failed: {exc}", flush=True)
        return jsonify({
            "reply": (
                "I couldn't extract the domain and intent from your message. "
                "Could you please provide them more clearly?\n\n"
                "For example:\n"
                '- Domain: "bioinformatics"\n'
                '- Intent: "Develop generative models for de novo molecular design '
                'with desired pharmacological properties"'
            ),
            "domain": "",
            "intent": "",
        })


@app.route("/api/generate", methods=["POST"])
def api_generate():
    body = request.get_json(force=True)
    domain = (body.get("domain") or "").strip()
    intent = (body.get("intent") or "").strip()
    if not domain or not intent:
        return jsonify({"error": "domain and intent are required"}), 400

    run_id = uuid.uuid4().hex[:12]
    yaml_path, task_name = _create_run_yaml(run_id, domain, intent)

    run = RunState(
        run_id=run_id, domain=domain, intent=intent,
        task_name=task_name, yaml_path=yaml_path, started_at=time.time(),
    )
    RUNS[run_id] = run

    t = threading.Thread(target=_run_agent_background, args=(run,), daemon=True)
    t.start()
    return jsonify({"run_id": run_id, "task_name": task_name})


@app.route("/api/status/<run_id>")
def api_status(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return jsonify({"error": "run not found"}), 404

    # Parse events for step-level progress display, but do NOT let the
    # event-parser's overall status override run.status.  The background
    # thread is the sole authority for the run lifecycle:
    #   starting → running → post_processing → completed / failed
    # This avoids a race where the event log shows "completed" (workflow_end)
    # before _post_process has finished building the zip/pdf.
    if run.event_log_path:
        _overall, steps = _parse_events(run.event_log_path)
    else:
        steps = []

    elapsed = time.time() - run.started_at if run.started_at else 0
    return jsonify({
        "run_id": run.run_id, "status": run.status,
        "domain": run.domain, "intent": run.intent,
        "steps": steps, "elapsed_seconds": round(elapsed, 1),
        "error": run.error,
        "has_zip": run.zip_path is not None,
        "has_pdf": run.pdf_path is not None,
    })


@app.route("/api/result/<run_id>")
def api_result(run_id: str):
    """Return download availability for a completed run."""
    run = RUNS.get(run_id)
    if not run:
        return jsonify({"error": "run not found"}), 404
    if run.status != "completed":
        return jsonify({"error": f"run not completed (status={run.status})"}), 409
    return jsonify({
        "has_zip": run.zip_path is not None,
        "has_pdf": run.pdf_path is not None,
    })


@app.route("/api/download/<run_id>/<filetype>")
def api_download(run_id: str, filetype: str):
    """Download zip or pdf for a completed run."""
    run = RUNS.get(run_id)
    if not run:
        return jsonify({"error": "run not found"}), 404

    if filetype == "zip" and run.zip_path and os.path.isfile(run.zip_path):
        return send_file(run.zip_path, as_attachment=True,
                         download_name=f"proposal_{run_id[:8]}.zip")
    elif filetype == "pdf" and run.pdf_path and os.path.isfile(run.pdf_path):
        return send_file(run.pdf_path, as_attachment=True,
                         download_name=f"proposal_{run_id[:8]}.pdf")
    else:
        return jsonify({"error": f"{filetype} not available"}), 404


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("WEB_PORT", "5001"))
    print(f"AI Scientists Web UI running at http://localhost:{port}")
    print(f"Project root:  {PROJECT_ROOT}")
    print(f"Base YAML:     {BASE_YAML}")
    print(f"Conda env:     {_CONDA_ENV or '(none — using current Python)'}")
    if _CONDA_ENV:
        print(f"  Subprocess:  conda run -n {_CONDA_ENV}")
    app.run(host="0.0.0.0", port=port, debug=False)
