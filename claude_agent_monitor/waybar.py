import json
from claude_agent_monitor import state as state_mod


def main():
    data = state_mod.prune_stale(state_mod.load())

    running = total = 0
    for sess in data.values():
        for a in sess.get("agents", []):
            total += 1
            if a["status"] == "running":
                running += 1

    text = f"  Active Sub Agent: {running}"
    if running:
        tooltip = f"{running} agent{'s' if running > 1 else ''} running"
        if total > running:
            tooltip += f" ({total - running} done)"
        cls = "active"
    else:
        tooltip = "No active agents"
        cls = "idle"

    print(json.dumps({"text": text, "tooltip": tooltip, "class": cls}))


if __name__ == "__main__":
    main()
