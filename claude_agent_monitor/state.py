import json
import fcntl
import time
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "share" / "claude-agent-monitor"
STATE_FILE = STATE_DIR / "state.json"
_LOCK_FILE = STATE_DIR / ".state.lock"

STALE_AFTER = 600        # seconds — sessions idle this long are pruned
MAX_AGENT_RUNTIME = 900  # seconds — running agents older than this are auto-closed


def load() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)  # atomic rename avoids partial reads


def update(fn) -> None:
    """Read-modify-write with exclusive file lock."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_FILE, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            s = load()
            s = fn(s)
            _save(s)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def prune_stale(state: dict) -> dict:
    now = time.time()
    session_cutoff = now - STALE_AFTER
    agent_cutoff = now - MAX_AGENT_RUNTIME
    result = {}
    for sid, sess in state.items():
        if sess.get("last_active", 0) <= session_cutoff:
            continue
        for a in sess.get("agents", []):
            if a["status"] == "running" and a.get("started_at", now) < agent_cutoff:
                a["status"] = "done"
                a["finished_at"] = agent_cutoff
        result[sid] = sess
    return result
