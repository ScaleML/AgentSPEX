import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from utils import *

EVENT_START = "<<<EVENT>>>"
EVENT_END = "<<</EVENT>>>"

from .client import MCPClient

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
except Exception:  # pragma: no cover
    Console = None  # type: ignore


class Logger:
    # Match scripts/dashboard.py palette
    _PAL_ACCENT = "#8bb5ff"
    _PAL_GREEN = "#8fd19e"
    _PAL_YELLOW = "#e3c07b"
    _PAL_RED = "#f28b82"
    _PAL_ORANGE = "#ffb072"
    _PAL_PURPLE = "#c9a0ff"
    _PAL_CYAN = "#7bd9ff"

    def __init__(
        self,
        mcp_client: MCPClient,
        log_file: str,
        to_stdout: bool = True,
        *,
        host_log_path: Path | None = None,
        event_log_path: str | None = None,
        host_event_log_path: Path | None = None,
        deduplicate: bool = False,
        append_mode: bool = False,
    ):
        """
        Initialize the logger.

        Args:
            log_file (str): Path to the log file.
            to_stdout (bool): If True, also print to stdout.
            host_log_path (Path | None): Optional local path to write logs outside MCP.
            event_log_path (str | None): Optional log path for structured events.
            host_event_log_path (Path | None): Optional local path for structured events.
            deduplicate (bool): If True, skip consecutive duplicate messages.
            append_mode (bool): If True, append to existing log files instead of
                overwriting them. Useful when re-creating the logger during resume
                to preserve previously logged events.
        """
        self.mcp_client = mcp_client
        self.log_path = log_file  # path under MCP fs_write
        self.to_stdout = to_stdout
        self.host_log_path = Path(host_log_path) if host_log_path else None
        self.event_log_path = event_log_path or self.log_path
        self.host_event_log_path = (
            Path(host_event_log_path) if host_event_log_path else self.host_log_path
        )
        self.deduplicate = deduplicate
        self.mcp_available = True
        self._last_message = None

        # Thread lock for thread-safe logging in parallel execution
        self._lock = threading.Lock()

        # Pretty console rendering (optional)
        self.pretty = (
            self._env_bool("CS_PRETTY", default=True)
            and self.to_stdout
            and Console is not None
        )
        self._console = (
            Console(
                highlight=False,
                soft_wrap=True,
                # Force ANSI colors by default to match dashboard semantics.
                # Disable via CS_FORCE_TTY=0 or CS_PRETTY=0 when redirecting to files/CI.
                force_terminal=self._env_bool("CS_FORCE_TTY", default=True),
                color_system="truecolor",
            )
            if self.pretty
            else None
        )
        self._max_panel_chars = int(os.environ.get("CS_PRETTY_MAX_CHARS", "6000"))
        self._workflow_total_steps: int | None = None
        self._current_top_step: int | None = None
        self._total_tokens_used: int = 0

        # Create log file with header (or append if resuming)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"[{timestamp}] Log started\n"
        if append_mode:
            # Append mode: preserve existing log content (used during resume)
            resume_header = f"[{timestamp}] Logger re-initialized (append mode)\n"
            try:
                res = self.mcp_client.invoke(
                    "fs_write",
                    {
                        "path": self.log_path,
                        "content": resume_header,
                        "mode": "text",
                        "append": True,
                    },
                )
                if isinstance(res, dict) and res.get("error"):
                    self.mcp_available = False
            except Exception:
                self.mcp_available = False

            if self.host_log_path:
                self.host_log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.host_log_path.open("a", encoding="utf-8") as f:
                    f.write(resume_header)

            if (
                self.host_event_log_path
                and self.host_event_log_path != self.host_log_path
            ):
                self.host_event_log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.host_event_log_path.open("a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] Event log re-initialized (append mode)\n")
            if self.event_log_path != self.log_path:
                try:
                    res = self.mcp_client.invoke(
                        "fs_write",
                        {
                            "path": self.event_log_path,
                            "content": f"[{timestamp}] Event log re-initialized (append mode)\n",
                            "mode": "text",
                            "append": True,
                        },
                    )
                    if isinstance(res, dict) and res.get("error"):
                        self.mcp_available = False
                except Exception:
                    self.mcp_available = False
        else:
            try:
                res = self.mcp_client.invoke(
                    "fs_write",
                    {
                        "path": self.log_path,
                        "content": header,
                    },
                )
                if isinstance(res, dict) and res.get("error"):
                    self.mcp_available = False
            except Exception:
                self.mcp_available = False

            if self.host_log_path:
                self.host_log_path.parent.mkdir(parents=True, exist_ok=True)
                self.host_log_path.write_text(header, encoding="utf-8")

            if (
                self.host_event_log_path
                and self.host_event_log_path != self.host_log_path
            ):
                self.host_event_log_path.parent.mkdir(parents=True, exist_ok=True)
                self.host_event_log_path.write_text(
                    f"[{timestamp}] Event log started\n", encoding="utf-8"
                )
            if self.event_log_path != self.log_path:
                try:
                    res = self.mcp_client.invoke(
                        "fs_write",
                        {
                            "path": self.event_log_path,
                            "content": f"[{timestamp}] Event log started\n",
                        },
                    )
                    if isinstance(res, dict) and res.get("error"):
                        self.mcp_available = False
                except Exception:
                    self.mcp_available = False

        if self.to_stdout and not self.pretty:
            print(header, end="")

    @staticmethod
    def _env_bool(key: str, *, default: bool) -> bool:
        raw = os.environ.get(key)
        if raw is None:
            return default
        return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}

    def _truncate(self, s: str, limit: int | None = None) -> str:
        limit = int(limit or self._max_panel_chars)
        if not isinstance(s, str):
            s = str(s)
        if len(s) <= limit:
            return s
        head = max(0, int(limit * 0.7))
        tail = max(0, limit - head - 20)
        return f"{s[:head]}\n... (content truncated) ...\n{s[-tail:]}"

    def _syntax_or_text(self, value: Any, *, language: str = "json") -> Any:
        def _wrap(renderable: Any) -> Table:
            """Wrap a renderable in a fold-overflow grid so long lines wrap inside the panel."""
            grid = Table.grid(expand=True)
            grid.add_column(ratio=1, overflow="fold")
            grid.add_row(renderable)
            return grid

        try:
            if isinstance(value, str):
                txt = value.strip()
                if language == "json":
                    parsed = json.loads(txt)
                    pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
                    return _wrap(Syntax(pretty, "json", word_wrap=True))
                return _wrap(Text(self._truncate(value)))
            return _wrap(
                Syntax(
                    json.dumps(value, ensure_ascii=False, indent=2, default=str),
                    "json",
                    word_wrap=True,
                )
            )
        except Exception:
            return _wrap(
                Text(self._truncate(value if isinstance(value, str) else str(value)))
            )

    def _kv_preview_table(self, mapping: dict, *, max_rows: int = 20) -> Table:
        """Compact preview for big dict payloads."""
        t = Table.grid(expand=True)
        t.add_column(no_wrap=True)
        t.add_column(justify="right", no_wrap=True, ratio=1, overflow="fold")
        items = list(mapping.items())
        shown = items[:max_rows]
        for k, v in shown:
            s = (
                v
                if isinstance(v, str)
                else json.dumps(v, ensure_ascii=False, default=str)
            )
            s = s.replace("\n", "\\n")
            if len(s) > 120:
                s = s[:100] + "…"
            t.add_row(Text(str(k), style="bold"), Text(s, style="dim"))
        if len(items) > max_rows:
            t.add_row(
                Text(f"… ({len(items) - max_rows} more keys)", style="dim"),
                Text("", style="dim"),
            )
        return t

    def _maybe_suppress_plain_stdout(self, message: str) -> bool:
        if not self.pretty:
            return False
        # Use full lstrip() so lines with leading spaces still match suppression rules.
        msg = (message or "").lstrip()
        suppress_prefixes = (
            # high-level workflow boilerplate (pretty mode renders this via events)
            "*************",
            "This is a ",
            "Goal:",
            "Config from YAML:",
            "===== YAML Workflow =====",
            "===== tools =====",
            "===== submodule tools =====",
            "Task:",
            "Parameters:",
            "Workflow steps:",
            "Tool:",
            "Submodule tool:",
            # generic section headers used throughout yaml_agent.py
            "==== ",
            "--- ",
            "==== Executing step ",
            "==== Executing task ",
            "==== Executing for_each loop ",
            "==== Executing while loop ",
            "==== Executing gather step ",
            "Max workers:",
            "🚀 Starting ",
            "✓ Progress:",
            "✅ All ",
            "--- [Thread-",
            "--- For-each iteration ",
            "Variable:",
            "In:",
            "Instruction:",
            "==== Input step ",
            "-- While iteration",
            "-- While iteration ",
            # Context dumps and debug separators inside loops
            "Context:",
            "Set context variable:",
            "Saved output:",
            "Saved input to context variable:",
            "Saved sub-module output to parent context:",
            "Sub-module completed successfully.",
            "Returned value:",
            "Return value:",
            "Found '",
            "Saved all gather results to context variable:",
            "Gather step completed:",
            "Total tokens used in gather:",
            "Synthesis output written to",
            "Discover items written to",
            "Saved content to",
            "Evaluation score",
            "Validation passed",
            "Validation failed",
            "Submodule ",
            "Parameters:",
            "Expanded parameters:",
            "Sub-module context initialized:",
            "Executing ",
            "Submodule using custom config:",
            "Submodule inheriting parent config:",
            "Environment variables restored",
            "ERROR:",
            "Traceback:",
            "   --- Tool call iteration",
            "   calling ",
            "   Context:",
            "  Response received",
            "  Now call tools",
            "  Tool calls performed:",
            "  Tool calls result:",
            "Assistant's output for step ",
            "Cross Step Context:",
            # end-of-run summaries (pretty mode shows DONE panel instead)
            "Total steps executed:",
            "Total tokens used:",
            "Output files can be found in",
            "Final output written to",
            "[Manifest]",
            "[Checkpoint]",
        )
        if msg.startswith(suppress_prefixes):
            return True
        # Suppress gather summary bullet lines (generated by engine, not model output)
        if msg.startswith("- result_") or msg.startswith("- gather_result_"):
            return True
        # Duplicate error line; tool_call_end event already renders the error.
        if msg.startswith("Tool ") and " failed with error" in msg:
            return True
        # Common interactive input prints in non-pretty paths; suppress if they slip through.
        if msg.startswith("USER INPUT REQUESTED") or msg.startswith("Your answer:"):
            return True
        if set(msg.strip()) in [{"%"}, {"@"}, {"="}] and len(msg.strip()) >= 10:
            return True
        return False

    def _render_event(self, event_type: str, data: dict, *, timestamp: str):
        if not self.pretty or not self._console:
            return
        try:
            et = event_type
            d = data or {}
            c = self._console

            if et == "workflow_start":
                self._workflow_total_steps = int(d.get("total_steps") or 0) or None
                self._total_tokens_used = 0
                title = f"YAML Workflow: {d.get('task_name', '')}".strip()
                right = f"model={d.get('model', '')}"
                if self._workflow_total_steps:
                    right += f"  steps={self._workflow_total_steps}"

                # Put goal + meta on separate lines to avoid cramped wrapping
                grid = Table.grid(expand=True)
                grid.add_column(ratio=1, overflow="fold")
                goal = str(d.get("goal", "") or "")
                if goal:
                    grid.add_row(Text(goal, style="bold"))
                grid.add_row(Align.right(Text(right, style="dim")))
                c.print(Rule(Text(title, style=f"bold {self._PAL_CYAN}")))
                c.print(Panel(grid, box=box.ROUNDED, border_style=self._PAL_CYAN))
                return

            if et == "step_start":
                step_id = str(d.get("step_id") or d.get("step_number") or "")
                name = str(d.get("name") or "").strip()
                step_type = str(d.get("step_type") or "").strip()
                instr = str(d.get("instruction") or "").strip()
                depth = int(d.get("depth") or 0)

                top_step = None
                if step_id.isdigit():
                    top_step = int(step_id)
                    self._current_top_step = top_step

                header = Table.grid(expand=True)
                header.add_column(ratio=1, overflow="fold")
                header.add_column(justify="right", ratio=1, no_wrap=True)
                left = Text(f"Step {step_id}", style="bold")
                if self._workflow_total_steps and top_step is not None:
                    left = Text(
                        f"Step {top_step}/{self._workflow_total_steps}", style="bold"
                    )
                if name:
                    left.append(f"  {name}", style="bold")
                right_bits = []
                if step_type:
                    right_bits.append(step_type)
                if self._workflow_total_steps and top_step is not None:
                    right_bits.append(
                        f"remaining={max(self._workflow_total_steps - top_step, 0)}"
                    )
                if self._total_tokens_used:
                    right_bits.append(f"tokens={self._total_tokens_used:,}")
                header.add_row(left, Text("  ".join(right_bits), style="dim"))

                border = self._PAL_ACCENT
                c.print(Panel(header, box=box.HEAVY, border_style=border))
                if instr:
                    c.print(
                        Panel(
                            Text(self._truncate(instr), style=""),
                            title="INSTRUCTION",
                            title_align="left",
                            box=box.ROUNDED,
                            border_style=self._PAL_ACCENT,
                        )
                    )
                return

            if et == "agent_iteration":
                step_id = str(d.get("step_id") or "")
                number = d.get("number")
                mx = d.get("max")
                tokens = d.get("tokens")
                limit = d.get("limit")
                util = d.get("utilization")
                line = f"iteration {number}/{mx}" if number and mx else "iteration"
                meta = (
                    f"step={step_id}  ctx={tokens:,}/{limit:,}"
                    if tokens is not None and limit
                    else f"step={step_id}"
                )
                if util is not None:
                    meta += f"  util={float(util):.1f}%"
                c.print(
                    Text(line, style=self._PAL_PURPLE), Text(f"  {meta}", style="dim")
                )
                return

            if et == "llm_response":
                content = str(d.get("content") or "")
                if content.strip():
                    c.print(
                        Panel(
                            Text(self._truncate(content), style=""),
                            title="ASSISTANT",
                            title_align="left",
                            box=box.ROUNDED,
                            border_style=self._PAL_ACCENT,
                        )
                    )
                return

            if et == "tool_call_start":
                tool_name = str(d.get("name") or "")
                args = d.get("args") or ""
                call_idx = d.get("call")
                title = f"ACTION  {tool_name}".strip()
                if call_idx:
                    title += f"  (call {call_idx})"
                c.print(
                    Panel(
                        self._syntax_or_text(args, language="json"),
                        title=title,
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=self._PAL_CYAN,
                    )
                )
                return

            if et == "tool_call_end":
                tool_name = str(d.get("name") or "")
                call_idx = d.get("call")
                raw = d.get("result") or ""
                title = f"OBSERVATION  {tool_name}".strip()
                if call_idx:
                    title += f"  (call {call_idx})"

                # Try to reduce noise: show common tool output fields prominently if present.
                payload: Any = raw
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(parsed, dict):
                        if "output" in parsed and isinstance(parsed["output"], str):
                            payload = parsed["output"]
                        elif "data" in parsed and isinstance(parsed["data"], str):
                            payload = parsed["data"]
                        else:
                            payload = parsed
                except Exception:
                    payload = raw

                border = (
                    self._PAL_RED
                    if isinstance(raw, str) and raw.strip().startswith("error:")
                    else self._PAL_GREEN
                )
                c.print(
                    Panel(
                        self._syntax_or_text(payload, language="json"),
                        title=title,
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=border,
                    )
                )
                return

            if et == "module_start":
                name = str(d.get("name") or d.get("path") or "")
                params = d.get("params") or {}
                step_id = str(d.get("step_id") or "")
                title = "MODULE"
                if step_id:
                    title += f"  step={step_id}"

                body = Table.grid(expand=True)
                body.add_column(ratio=1, overflow="fold")
                body.add_row(Text(name, style="bold"))
                if isinstance(params, dict) and params:
                    try:
                        raw = json.dumps(params, ensure_ascii=False, default=str)
                        if len(raw) > 1500:
                            body.add_row(self._kv_preview_table(params))
                        else:
                            body.add_row(self._syntax_or_text(params))
                    except Exception:
                        body.add_row(self._syntax_or_text(params))

                c.print(
                    Panel(
                        body,
                        title=title,
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=self._PAL_ORANGE,
                    )
                )
                return

            if et == "module_end":
                name = str(d.get("name") or "")
                status = str(d.get("status") or "")
                result = d.get("result") or ""
                tb = str(d.get("traceback") or "")
                step_id = str(d.get("step_id") or "")

                title = "MODULE END"
                if step_id:
                    title += f"  step={step_id}"

                body = Table.grid(expand=True)
                body.add_column(ratio=1, overflow="fold")
                if name:
                    body.add_row(Text(name, style="bold"))
                if status:
                    body.add_row(Text(f"status: {status}", style="dim"))
                if result:
                    body.add_row(Text(self._truncate(str(result)), style=""))
                if status == "error" and tb:
                    # show a short traceback preview only
                    lines = [ln for ln in tb.splitlines() if ln.strip()]
                    preview = "\n".join(lines[:12])
                    body.add_row(Text(self._truncate(preview), style="dim"))
                    body.add_row(
                        Text(
                            "(See agent_run.log / agent_events.log for full stack trace)",
                            style="dim",
                        )
                    )

                border = (
                    self._PAL_GREEN if status and status != "error" else self._PAL_RED
                )
                c.print(
                    Panel(
                        body,
                        title=title,
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=border,
                    )
                )
                return

            if et == "parallel_call_start":
                name = str(d.get("name") or "")
                params = d.get("params") or {}
                call_idx = d.get("call")
                step_id = str(d.get("step_id") or "")
                title = "PARALLEL CALL"
                if call_idx is not None:
                    title += f"  call={call_idx}"
                if step_id:
                    title += f"  step={step_id}"

                body = Table.grid(expand=True)
                body.add_column(ratio=1, overflow="fold")
                if name:
                    body.add_row(Text(name, style="bold"))
                if isinstance(params, dict) and params:
                    try:
                        raw = json.dumps(params, ensure_ascii=False, default=str)
                        if len(raw) > 1500:
                            body.add_row(self._kv_preview_table(params))
                        else:
                            body.add_row(self._syntax_or_text(params))
                    except Exception:
                        body.add_row(self._syntax_or_text(params))

                c.print(
                    Panel(
                        body,
                        title=title,
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=self._PAL_YELLOW,
                    )
                )
                return

            if et == "parallel_call_end":
                name = str(d.get("name") or "")
                call_idx = d.get("call")
                step_id = str(d.get("step_id") or "")
                status = str(d.get("status") or "")
                result = d.get("result") or ""
                title = "PARALLEL RESULT"
                if call_idx is not None:
                    title += f"  call={call_idx}"
                if step_id:
                    title += f"  step={step_id}"

                body = Table.grid(expand=True)
                body.add_column(ratio=1, overflow="fold")
                if name:
                    body.add_row(Text(name, style="bold"))
                if status:
                    body.add_row(Text(f"status: {status}", style="dim"))
                if result:
                    body.add_row(Text(self._truncate(str(result)), style=""))

                border = (
                    self._PAL_GREEN if status and status != "error" else self._PAL_RED
                )
                c.print(
                    Panel(
                        body,
                        title=title,
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=border,
                    )
                )
                return

            if et == "step_end":
                status = str(d.get("status") or "")
                tokens = int(d.get("tokens") or 0)
                if tokens:
                    self._total_tokens_used += tokens
                if status and status != "completed":
                    err = str(d.get("error") or "")
                    c.print(
                        Panel(
                            Text(self._truncate(err) if err else status, style="bold"),
                            title="STEP ERROR",
                            title_align="left",
                            box=box.ROUNDED,
                            border_style=self._PAL_RED,
                        )
                    )
                return

            if et == "workflow_end":
                total = int(d.get("total_tokens") or 0)
                prompt = int(d.get("prompt_tokens") or 0)
                completion = int(d.get("completion_tokens") or 0)
                cost = float(d.get("cost") or 0.0)
                steps = d.get("total_steps")
                output_dir = str(d.get("output_dir") or "").strip()
                final_file = str(d.get("final_file_path") or "").strip()

                grid = Table.grid(expand=True)
                grid.add_column(ratio=1, overflow="fold")
                line1 = (
                    f"tokens={total:,}  prompt={prompt:,}  completion={completion:,}"
                )
                if cost > 0:
                    line1 += f"  cost=${cost:.4f}"
                if steps is not None:
                    try:
                        line1 = f"steps={int(steps)}  " + line1
                    except Exception:
                        line1 = f"steps={steps}  " + line1
                grid.add_row(Text(line1, style=""))
                if output_dir:
                    grid.add_row(Text(f"output_dir: {output_dir}", style=""))
                if final_file:
                    grid.add_row(Text(f"final: {final_file}", style=""))

                c.print(
                    Panel(
                        grid,
                        title="DONE",
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=self._PAL_GREEN,
                    )
                )
                return

            if et in ("info", "warning", "error", "debug"):
                msg = str(d.get("message") or "")
                if not msg.strip():
                    return
                border = {
                    "info": self._PAL_CYAN,
                    "debug": self._PAL_PURPLE,
                    "warning": self._PAL_YELLOW,
                    "error": self._PAL_RED,
                }.get(et, self._PAL_CYAN)

                # Special-case startup INFO to avoid truncation: split Logs/Events on two lines.
                if et == "info" and ("Logs:" in msg and "Events:" in msg):
                    logs_line = msg
                    events_line = ""
                    try:
                        # naive but robust split
                        if "  Events:" in msg:
                            logs_line, events_line = msg.split("  Events:", 1)
                            logs_line = logs_line.strip()
                            events_line = ("Events:" + events_line).strip()
                    except Exception:
                        pass
                    grid = Table.grid(expand=True)
                    grid.add_column(ratio=1, overflow="fold")
                    grid.add_row(Text(self._truncate(logs_line), style=""))
                    if events_line:
                        grid.add_row(Text(self._truncate(events_line), style=""))
                    c.print(
                        Panel(
                            grid,
                            title=et.upper(),
                            title_align="left",
                            box=box.ROUNDED,
                            border_style=border,
                        )
                    )
                    return

                c.print(
                    Panel(
                        Text(self._truncate(msg), style=""),
                        title=et.upper(),
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=border,
                    )
                )
                return

            if et == "loop_start":
                model = str(d.get("model") or "")
                tools_count = d.get("tools_count", 0)
                right = f"model={model}  tools={tools_count}"
                c.print(
                    Rule(
                        Text("AgentSPEX CLI", style=f"bold {self._PAL_CYAN}"),
                        style=self._PAL_CYAN,
                    )
                )
                c.print(Align.right(Text(right, style="dim")))
                return

            if et == "loop_end":
                total = int(d.get("total_tokens") or 0)
                prompt = int(d.get("prompt_tokens") or 0)
                completion = int(d.get("completion_tokens") or 0)
                line = f"tokens={total:,}  prompt={prompt:,}  completion={completion:,}"
                c.print(
                    Panel(
                        Text(line, style=""),
                        title="SESSION END",
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=self._PAL_GREEN,
                    )
                )
                return

            if et == "user_message":
                return  # logged to file only; already visible in terminal

            if et == "input_request":
                prompt = str(d.get("prompt") or "")
                default = str(d.get("default") or "")
                save_as = str(d.get("save_as") or "")
                step_id = str(d.get("step_id") or "")

                grid = Table.grid(expand=True)
                grid.add_column(ratio=1, overflow="fold")
                if step_id:
                    grid.add_row(Text(f"step={step_id}", style="dim"))
                if save_as:
                    grid.add_row(Text(f"save_as: {save_as}", style="dim"))
                grid.add_row(Text(prompt, style="bold"))
                if default:
                    grid.add_row(
                        Text(f"(Enter to use default: {default})", style="dim")
                    )

                c.print(
                    Panel(
                        grid,
                        title="USER INPUT",
                        title_align="left",
                        box=box.ROUNDED,
                        border_style=self._PAL_GREEN,
                    )
                )
                return
        except Exception:
            # Never let rendering break logging
            return

    def _append_line(
        self,
        line: str,
        *,
        log_path: str | None = None,
        host_path: Path | None = None,
        to_stdout: bool = False,
    ):
        target_log_path = log_path or self.log_path
        target_host_path = host_path if host_path is not None else self.host_log_path
        if self.mcp_available:
            try:
                res = self.mcp_client.invoke(
                    "fs_write",
                    {
                        "path": target_log_path,
                        "content": line,
                        "mode": "text",
                        "append": True,  # append to existing content
                    },
                )
                if isinstance(res, dict) and res.get("error"):
                    self.mcp_available = False
            except Exception as e:
                # Silently fail MCP logging if it fails once, but continue host logging.
                self.mcp_available = False

        if target_host_path:
            with target_host_path.open("a", encoding="utf-8") as f:
                f.write(line)

        if to_stdout:
            print(line, end="")

    def __call__(self, message: str):
        """
        Log a message with timestamp, appending to the log file and optionally printing to stdout.
        Thread-safe for parallel execution.

        Args:
            message (str): The message to log.
        """
        with self._lock:
            if self.deduplicate and message == self._last_message:
                return
            self._last_message = message

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full_message = f"[{timestamp}] {message}\n"

            self._append_line(full_message, to_stdout=False)

            if self.to_stdout:
                if not self._maybe_suppress_plain_stdout(message):
                    print(message)

    def rule(self, color: str | None = None) -> None:
        """Print a horizontal rule to the console without logging to file."""
        if self.pretty and self._console:
            self._console.print(Rule(style=color or self._PAL_GREEN))

    def event(
        self,
        event_type: str,
        data: dict,
        *,
        timestamp: str | None = None,
        to_stdout: bool = False,
    ):
        """
        Log a structured event for machine parsing.
        """
        with self._lock:
            payload = {
                "type": event_type,
                "timestamp": timestamp or datetime.now().isoformat(),
                "data": data,
            }
            line = (
                f"{EVENT_START}{json.dumps(payload, ensure_ascii=False)}{EVENT_END}\n"
            )
            self._append_line(
                line,
                log_path=self.event_log_path,
                host_path=self.host_event_log_path,
                to_stdout=to_stdout,
            )
            self._render_event(event_type, data, timestamp=payload["timestamp"])

    def log_event(self, logger, event_type: str, data: Dict[str, Any]):
        event_fn = getattr(logger, "event", None)
        if callable(event_fn):
            event_fn(event_type, data)

    def print_messages(
        self, messages: list[dict[str, any]], max_value_len=80, num_indents: int = 0
    ):
        """
        Print and log messages. Thread-safe for parallel execution.
        """
        with self._lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = shorten_values(messages, max_value_len * 20)
            full_message = f"[{timestamp}] {msg}\n"

            self._append_line(full_message, to_stdout=False)

            if self.to_stdout:
                if self.pretty:
                    # Avoid dumping huge message payloads to stdout in pretty mode.
                    return
                msg = shorten_values(messages, max_value_len)
                print(json.dumps(msg, indent=num_indents, ensure_ascii=False))
            return
