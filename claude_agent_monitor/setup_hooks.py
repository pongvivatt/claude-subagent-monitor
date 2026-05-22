"""Register/unregister the Agent hooks in Claude Code's settings.json.

Idempotent and backup-first: safe to run repeatedly. Kept free of any GTK
imports so it can run in headless/install contexts.
"""

import json
import shlex
import shutil
import sys
import time
from pathlib import Path

HOOK_COMMAND = "claude-agent-monitor-hook"
MATCHER = "Agent"
# (event, matcher). PreToolUse/PostToolUse track agent spawn/finish; SessionEnd
# has no matcher so it fires on every end reason, clearing a session's agents
# when it closes (otherwise agents still running at close would linger).
REGISTRATIONS = (("PreToolUse", MATCHER), ("PostToolUse", MATCHER), ("SessionEnd", None))


def default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _resolved_command() -> str:
    """Best path to the hook binary, quoted for safe shell execution.

    Prefer the hook sitting next to the running entry-point script — this
    handles venv/source installs whose bin dir isn't on PATH. Fall back to
    PATH, then the bare name (correct once the package is installed normally).
    """
    sibling = Path(sys.argv[0]).resolve().parent / HOOK_COMMAND
    path = str(sibling) if sibling.exists() else (shutil.which(HOOK_COMMAND) or HOOK_COMMAND)
    return shlex.quote(path)


def _is_ours(hook: object) -> bool:
    return isinstance(hook, dict) and HOOK_COMMAND in str(hook.get("command", ""))


def _add(hooks: dict, command: str) -> None:
    for event, matcher in REGISTRATIONS:
        arr = hooks.get(event)
        if not isinstance(arr, list):
            arr = []
        already = any(
            isinstance(e, dict) and any(_is_ours(h) for h in e.get("hooks", []))
            for e in arr
        )
        if not already:
            hook_def = {"type": "command", "command": command}
            entry = {"matcher": matcher, "hooks": [hook_def]} if matcher else {"hooks": [hook_def]}
            arr = arr + [entry]
        hooks[event] = arr


def _remove(hooks: dict) -> None:
    for event, _matcher in REGISTRATIONS:
        arr = hooks.get(event)
        if not isinstance(arr, list):
            continue
        new_arr = []
        for e in arr:
            if isinstance(e, dict):
                orig = e.get("hooks", [])
                kept = [h for h in orig if not _is_ours(h)]
                if kept:
                    new_arr.append({**e, "hooks": kept})
                elif not orig:
                    new_arr.append(e)  # nothing of ours to strip; leave it
                # else: every hook in this entry was ours -> drop the entry
            else:
                new_arr.append(e)
        if new_arr:
            hooks[event] = new_arr
        else:
            hooks.pop(event, None)


def install_hooks(uninstall: bool = False, settings_path: Path | None = None) -> bool:
    """Add or remove the Agent hooks. Returns True if the file was changed."""
    path = settings_path or default_settings_path()
    command = _resolved_command()

    settings: dict = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as e:
            print(f"  {path} is not valid JSON ({e}); refusing to modify it.")
            return False
        if not isinstance(settings, dict):
            print(f"  {path} does not contain a JSON object; aborting.")
            return False

    before = json.dumps(settings, sort_keys=True)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}

    if uninstall:
        _remove(hooks)
    else:
        _add(hooks, command)

    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)

    if json.dumps(settings, sort_keys=True) == before:
        where = "present in" if not uninstall else "absent from"
        print(f"  hooks already {where} {path}; nothing to do.")
        return False

    if path.exists():
        backup = path.parent / f"{path.name}.bak.{int(time.time())}"
        backup.write_text(path.read_text())
        print(f"  backed up existing settings -> {backup.name}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")

    if uninstall:
        print(f"  removed claude-agent-monitor hooks from {path}")
    else:
        print(f"  added PreToolUse + PostToolUse (matcher {MATCHER!r}) and SessionEnd hooks (command {command}) to {path}")
        print("  restart your Claude Code sessions for the hooks to take effect.")
    return True
