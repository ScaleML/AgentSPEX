import json
import time
from pathlib import Path

from mcp_client.client import MCPClient


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def test_mcpclient_replay_applies_fs_write_side_effect(tmp_path: Path):
    out_file = tmp_path / "out.txt"
    trace_path = tmp_path / "trace.jsonl"

    events = [
        {
            "type": "tool",
            "seq": 1,
            "ts": time.time(),
            "session_id": None,
            "name": "fs_write",
            "arguments": {
                "path": str(out_file),
                "content": "hello",
                "mode": "text",
                "append": False,
            },
            "result": {"path": str(out_file)},
        },
        {
            "type": "tool",
            "seq": 2,
            "ts": time.time(),
            "session_id": None,
            "name": "fs_read",
            "arguments": {"path": str(out_file), "max_bytes": 1024},
            "result": {"text": "hello"},
        },
    ]
    _write_jsonl(trace_path, events)

    client = MCPClient(connect=False, replay_trace_path=str(trace_path))

    res1 = client.invoke(
        "fs_write",
        {"path": str(out_file), "content": "hello", "mode": "text", "append": False},
    )
    assert "error" not in res1
    assert out_file.read_text(encoding="utf-8") == "hello"

    res2 = client.invoke("fs_read", {"path": str(out_file), "max_bytes": 1024})
    assert "error" not in res2
    assert res2.get("text") == "hello"


def test_mcpclient_replay_detects_mismatch(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    _write_jsonl(
        trace_path,
        [
            {
                "type": "tool",
                "seq": 1,
                "ts": time.time(),
                "session_id": None,
                "name": "fs_write",
                "arguments": {
                    "path": str(tmp_path / "a.txt"),
                    "content": "x",
                    "mode": "text",
                    "append": False,
                },
                "result": {},
            }
        ],
    )

    client = MCPClient(connect=False, replay_trace_path=str(trace_path))
    res = client.invoke("fs_read", {"path": "anything", "max_bytes": 1})
    assert "error" in res
