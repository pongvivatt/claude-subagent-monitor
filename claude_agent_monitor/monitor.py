import sys
import time
import math
import shutil
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GLib, Gdk, Pango, GdkPixbuf

from claude_agent_monitor import state as state_mod

RESOURCES = Path(__file__).parent / "resources"

ICON_SIZE = 140  # px — SVG mascot width per row (height scales by aspect ratio)

# Color-coded mascots by agent type
MASCOT_COLORS = {
    "Explore": "blue",
    "Plan": "cyan",
    "claude": "terracotta",
    "general-purpose": "mint",
}

# Fallback color cycle for unknown types
COLOR_FALLBACKS = ["magenta", "rose", "violet", "mustard", "forest-green"]


def _get_mascot_svg(subagent_type: str) -> str:
    """Get the appropriate colored mascot SVG for an agent type."""
    color = MASCOT_COLORS.get(subagent_type)
    if not color:
        # Cycle through fallback colors based on type hash
        idx = hash(subagent_type) % len(COLOR_FALLBACKS)
        color = COLOR_FALLBACKS[idx]
    return str(RESOURCES / f"claude-mascot-{color}.svg")

CSS = """
* {
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
    font-size: 12px;
}

window {
    background-color: #FFFCF0;
    color: #100F0F;
}

.stats-bar {
    background-color: #F2F0E5;
    border-bottom: 1px solid rgba(16, 15, 15, 0.12);
    padding: 7px 14px;
}

.monitor-title {
    color: #CC785C;
    font-weight: bold;
    font-size: 13px;
    letter-spacing: 1px;
}

.stat-key   { color: rgba(16, 15, 15, 0.45); }
.stat-val   { color: rgba(16, 15, 15, 0.70); }
.stat-val.active { color: #CC785C; font-weight: bold; }

.session-panel {
    background-color: #F2F0E5;
    border: 1px solid rgba(16, 15, 15, 0.12);
    border-radius: 4px;
}

.panel-header {
    background-color: #E6E4D9;
    border-bottom: 1px solid rgba(16, 15, 15, 0.12);
    padding: 4px 10px;
}

.panel-cwd   { color: #205EA6; }
.panel-sid   { color: rgba(16, 15, 15, 0.35); }
.panel-badge { color: #CC785C; font-weight: bold; }

.agent-row {
    padding: 2px 10px;
    border-bottom: 1px solid rgba(16, 15, 15, 0.06);
}

.agent-row:last-child { border-bottom: none; }

.agent-row { background-color: #FFFCF0; }

.type-label {
    color: rgba(16, 15, 15, 0.62);
    min-width: 100px;
}

.desc-label { color: rgba(16, 15, 15, 0.82); }

.time-label {
    color: rgba(16, 15, 15, 0.45);
    font-size: 11px;
}

.empty {
    color: rgba(16, 15, 15, 0.30);
    font-size: 13px;
    padding: 48px;
}
"""


def _fmt_time(secs: float) -> str:
    if secs < 60:
        return f"{secs:.0f}s"
    if secs < 3600:
        m, s = divmod(int(secs), 60)
        return f"{m}m {s}s"
    return f"{secs / 3600:.1f}h"


def _load_icon(svg_path: str, size: int) -> GdkPixbuf.Pixbuf:
    return GdkPixbuf.Pixbuf.new_from_file_at_size(svg_path, size, size)


class AgentRow(Gtk.Box):
    def __init__(self, agent: dict):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.agent = agent

        self.add_css_class("agent-row")
        self.set_margin_top(0)
        self.set_margin_bottom(0)

        # Colored Claude mascot icon (based on agent type)
        subagent_type = agent.get("subagent_type", "claude")
        svg_path = _get_mascot_svg(subagent_type)
        try:
            pb = _load_icon(svg_path, ICON_SIZE)
            self.image = Gtk.Image.new_from_pixbuf(pb)
        except Exception:
            self.image = Gtk.Image.new_from_icon_name("dialog-question")
        self.image.set_valign(Gtk.Align.CENTER)
        self.append(self.image)

        # Agent type
        subtype = agent.get("subagent_type", "claude")
        type_lbl = Gtk.Label(label=subtype)
        type_lbl.add_css_class("type-label")
        type_lbl.set_xalign(0)
        type_lbl.set_valign(Gtk.Align.CENTER)
        self.append(type_lbl)

        # Description — expands, ellipsizes
        desc = agent.get("description", "Working…")
        desc_lbl = Gtk.Label(label=desc)
        desc_lbl.add_css_class("desc-label")
        desc_lbl.set_xalign(0)
        desc_lbl.set_hexpand(True)
        desc_lbl.set_valign(Gtk.Align.CENTER)
        desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(desc_lbl)

        # Elapsed / done time — right-aligned
        self.time_lbl = Gtk.Label()
        self.time_lbl.add_css_class("time-label")
        self.time_lbl.set_xalign(1)
        self.time_lbl.set_width_chars(12)
        self.time_lbl.set_valign(Gtk.Align.CENTER)
        self.append(self.time_lbl)

        self._update_time()

        self._phase = 0.0
        GLib.timeout_add(60, self._pulse)

    def _update_time(self):
        started = self.agent.get("started_at", time.time())
        self.time_lbl.set_label(_fmt_time(time.time() - started))

    def _pulse(self) -> bool:
        if not self.get_parent():
            return GLib.SOURCE_REMOVE
        self._phase = (self._phase + 0.07) % (2 * math.pi)
        opacity = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._phase))
        self.image.set_opacity(opacity)
        self._update_time()
        return GLib.SOURCE_CONTINUE


class SessionPanel(Gtk.Box):
    def __init__(self, session_id: str, session: dict):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("session-panel")

        cwd = session.get("cwd", "").replace(str(Path.home()), "~")
        agents = session.get("agents", [])
        running = sum(1 for a in agents if a["status"] == "running")

        # ── panel header ─────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("panel-header")

        cwd_lbl = Gtk.Label(label=f" {cwd}")
        cwd_lbl.add_css_class("panel-cwd")
        cwd_lbl.set_xalign(0)
        header.append(cwd_lbl)

        sid_lbl = Gtk.Label(label=f"  ·  {session_id[:8]}")
        sid_lbl.add_css_class("panel-sid")
        sid_lbl.set_xalign(0)
        sid_lbl.set_hexpand(True)
        header.append(sid_lbl)

        if running:
            badge = Gtk.Label(label=f"{running} running  ")
            badge.add_css_class("panel-badge")
            header.append(badge)

        self.append(header)

        # ── agent rows ───────────────────────────
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for agent in agents:
            if agent.get("status") == "running":
                rows.append(AgentRow(agent))
        self.append(rows)


class MonitorWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Claude Agent Monitor")
        self.set_default_size(760, 480)

        css = Gtk.CssProvider()
        css.load_from_data(CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        # ── stats bar ────────────────────────────
        stats_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        stats_bar.add_css_class("stats-bar")

        title_lbl = Gtk.Label(label="◈ CLAUDE AGENT MONITOR")
        title_lbl.add_css_class("monitor-title")
        title_lbl.set_xalign(0)
        stats_bar.append(title_lbl)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        stats_bar.append(spacer)

        self._stat_sessions = self._stat_widget(stats_bar, "Sessions")
        self._stat_running  = self._stat_widget(stats_bar, "Running", active=True)

        root.append(stats_bar)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        root.append(sep)

        # ── scrollable content ───────────────────
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._content.set_margin_top(8)
        self._content.set_margin_bottom(8)
        self._content.set_margin_start(8)
        self._content.set_margin_end(8)

        scroll.set_child(self._content)
        root.append(scroll)

        GLib.timeout_add(1000, self._refresh)
        self._refresh()

    def _stat_widget(self, parent: Gtk.Box, key: str, active: bool = False) -> Gtk.Label:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.set_margin_start(20)

        key_lbl = Gtk.Label(label=f"{key}:")
        key_lbl.add_css_class("stat-key")
        box.append(key_lbl)

        val_lbl = Gtk.Label(label="0")
        val_lbl.add_css_class("stat-val")
        if active:
            val_lbl.add_css_class("active")
        box.append(val_lbl)

        parent.append(box)
        return val_lbl

    def _refresh(self) -> bool:
        data = state_mod.prune_stale(state_mod.load())

        active = {
            sid: sess for sid, sess in data.items()
            if any(a["status"] == "running" for a in sess.get("agents", []))
        }
        n_running = sum(1 for s in active.values() for a in s.get("agents", []) if a["status"] == "running")

        self._stat_sessions.set_label(str(len(active)))
        self._stat_running.set_label(str(n_running))

        while child := self._content.get_first_child():
            self._content.remove(child)

        if not active:
            lbl = Gtk.Label(label="No active sessions\nStart a Claude Code session to see agents here.")
            lbl.add_css_class("empty")
            lbl.set_justify(Gtk.Justification.CENTER)
            self._content.append(lbl)
        else:
            for sid, sess in sorted(active.items()):
                self._content.append(SessionPanel(sid, sess))

        return GLib.SOURCE_CONTINUE


class MonitorApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.claude.agentmonitor")

    def do_activate(self):
        MonitorWindow(self).present()


def _print_setup() -> None:
    hook_cmd    = shutil.which("claude-agent-monitor-hook")    or "claude-agent-monitor-hook"
    waybar_cmd  = shutil.which("claude-agent-monitor-waybar")  or "claude-agent-monitor-waybar"
    monitor_cmd = shutil.which("claude-agent-monitor")         or "claude-agent-monitor"

    print(f"""
Claude Agent Monitor — setup
============================

1. Register the hook (recommended):

   claude-agent-monitor install-hooks

   …or add it to ~/.claude/settings.json manually:

{{
  "hooks": {{
    "PreToolUse": [
      {{"matcher": "Agent", "hooks": [{{"type": "command", "command": "{hook_cmd}"}}]}}
    ],
    "PostToolUse": [
      {{"matcher": "Agent", "hooks": [{{"type": "command", "command": "{hook_cmd}"}}]}}
    ],
    "SessionEnd": [
      {{"hooks": [{{"type": "command", "command": "{hook_cmd}"}}]}}
    ]
  }}
}}

2. Waybar — add the module to your modules-left/right/center list:

   "custom/claude-agent-monitor"

   Then add the module definition anywhere in config.jsonc:

   "custom/claude-agent-monitor": {{
       "exec": "{waybar_cmd}",
       "return-type": "json",
       "interval": 2,
       "on-click": "{monitor_cmd}",
       "tooltip": true
   }}

3. Waybar style.css — add #custom-claude-agent-monitor to your existing
   button selector, then append these rules:

   #custom-claude-agent-monitor {{ color: #CC785C; }}

   #custom-claude-agent-monitor.active {{
       background: #CC785C;
       color: #FFFCF0;
       border-color: #CC785C;
   }}

4. Hyprland window rules (hyprland.conf):

   windowrulev2 = float,  title:^(Claude Agent Monitor)$
   windowrulev2 = size 760 480, title:^(Claude Agent Monitor)$
   windowrulev2 = move 100%-780 60, title:^(Claude Agent Monitor)$
""")


def _seed_state() -> None:
    """Populate state.json with sample sessions for visual testing."""
    now = time.time()
    sample = {
        "demo-session-alpha": {
            "cwd": str(Path.home() / "Projects" / "alpha"),
            "last_active": now,
            "agents": [
                {"tool_use_id": "seed-1", "description": "Investigate flaky integration test",
                 "subagent_type": "Explore", "status": "running", "started_at": now - 42},
                {"tool_use_id": "seed-2", "description": "Draft migration plan for auth rewrite",
                 "subagent_type": "Plan", "status": "running", "started_at": now - 17},
                {"tool_use_id": "seed-3", "description": "Summarize PR feedback",
                 "subagent_type": "general-purpose", "status": "done",
                 "started_at": now - 300, "finished_at": now - 180},
            ],
        },
        "demo-session-beta": {
            "cwd": str(Path.home() / "Projects" / "beta"),
            "last_active": now,
            "agents": [
                {"tool_use_id": "seed-4", "description": "Refactor billing module",
                 "subagent_type": "claude", "status": "running", "started_at": now - 5},
                {"tool_use_id": "seed-5", "description": "Custom workflow check",
                 "subagent_type": "my-custom-agent", "status": "running", "started_at": now - 90},
            ],
        },
    }
    state_mod.update(lambda _: sample)
    print(f"Seeded {state_mod.STATE_FILE} with 2 sessions, 5 agents (4 running, 1 done).")


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "setup":
        _print_setup()
        return
    if arg == "seed":
        _seed_state()
        return
    if arg in ("install-hooks", "uninstall-hooks"):
        from claude_agent_monitor.setup_hooks import install_hooks
        install_hooks(uninstall=(arg == "uninstall-hooks"))
        return
    MonitorApp().run(None)


if __name__ == "__main__":
    main()
