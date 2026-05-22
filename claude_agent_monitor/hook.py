import sys
import json
import time


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    event = data.get("hook_event_name", "")
    session_id = data.get("session_id", "unknown")

    # Session ended: drop its agents so the monitor doesn't show phantoms for
    # sub-agents that were still running when the session closed (their
    # PostToolUse never fired). Does not cover hard SIGKILL — prune_stale is
    # the backstop for that.
    if event == "SessionEnd":
        try:
            from claude_agent_monitor import state

            def _end(s):
                s.pop(session_id, None)
                return s

            state.update(_end)
        except Exception:
            pass
        sys.exit(0)

    if data.get("tool_name") != "Agent":
        sys.exit(0)

    cwd = data.get("cwd", "")
    tool_use_id = data.get("tool_use_id", "")
    now = time.time()

    try:
        from claude_agent_monitor import state

        if event == "PreToolUse":
            tool_input = data.get("tool_input", {})
            desc = tool_input.get("description", "Working…")
            subtype = tool_input.get("subagent_type", "claude")

            def _add(s):
                if session_id not in s:
                    s[session_id] = {"cwd": cwd, "agents": []}
                s[session_id]["last_active"] = now
                s[session_id]["agents"].append({
                    "tool_use_id": tool_use_id,
                    "description": desc,
                    "subagent_type": subtype,
                    "status": "running",
                    "started_at": now,
                })
                return state.prune_stale(s)

            state.update(_add)

        elif event == "PostToolUse":
            def _finish(s):
                if session_id not in s:
                    return s
                agents = s[session_id].get("agents", [])
                # Pair Pre/Post by tool_use_id so parallel Agents don't get swapped.
                target = None
                if tool_use_id:
                    for a in agents:
                        if a.get("tool_use_id") == tool_use_id and a["status"] == "running":
                            target = a
                            break
                if target is None:
                    for a in reversed(agents):
                        if a["status"] == "running":
                            target = a
                            break
                if target is not None:
                    target["status"] = "done"
                    target["finished_at"] = now
                s[session_id]["last_active"] = now
                return s

            state.update(_finish)

    except Exception:
        pass  # never block Claude on our errors

    sys.exit(0)


if __name__ == "__main__":
    main()
