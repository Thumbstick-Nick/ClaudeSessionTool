"""Claude Code session-limit app — Eagle Point Software branded.

Single-page modal showing tokens used in the rolling 5-hour session window
and the rolling 7-day weekly window, with per-model breakdown and a live
countdown to session reset. Theme follows Windows by default; user can
override to light/dark.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk
import pystray

IS_FROZEN = getattr(sys, "frozen", False)


def _resource_dir() -> Path:
    """Read-only assets (logo, icon). Bundled by PyInstaller into _MEIPASS;
    in dev it's the script folder."""
    if IS_FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


def _user_data_dir() -> Path:
    """User-writable storage. %APPDATA%\\ClaudeUsageMonitor when bundled;
    script folder in dev for convenience."""
    if IS_FROZEN:
        base = Path(os.environ.get("APPDATA", Path.home()))
        d = base / "ClaudeUsageMonitor"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"

RESOURCE_DIR = _resource_dir()
USER_DATA_DIR = _user_data_dir()

LOGO_PATH = RESOURCE_DIR / "logo.png"
ICON_PATH = RESOURCE_DIR / "icon.png"
CONFIG_PATH = USER_DATA_DIR / "config.json"
ICO_PATH = USER_DATA_DIR / "icon.ico"

APP_USER_MODEL_ID = "eaglepoint.claude-usage-monitor"
HOOK_TAG = APP_USER_MODEL_ID  # marker so we can find/remove our own hook
SESSION_HOURS = 5
WEEK_DAYS = 7

SUBTITLE = (
    "Live view of your Claude Code token usage, read from your local "
    "session logs and refreshed every 5 seconds."
)

SESSION_CAPS = {
    "pro":   7_000_000,
    "max5":  35_000_000,
    "max20": 140_000_000,
}
WEEKLY_CAPS = {
    "pro":   70_000_000,
    "max5":  280_000_000,
    "max20": 1_120_000_000,
}

LIGHT_THEME = {
    "bg":         "#FFFFFF",
    "panel_bg":   "#F4F6F9",
    "border":     "#DFE3EA",
    "fg":         "#1B3A5C",
    "muted_fg":   "#6B7480",
    "accent":     "#2E8FD0",
    "navy":       "#1B3A5C",
    "trough":     "#E1E5EB",
}
DARK_THEME = {
    "bg":         "#1E2227",
    "panel_bg":   "#262B31",
    "border":     "#363C44",
    "fg":         "#E6ECF2",
    "muted_fg":   "#8B95A1",
    "accent":     "#4AA8E5",
    "navy":       "#7FB8E0",
    "trough":     "#363C44",
}


def _launch_command_for_hook() -> str:
    """Shell command Claude Code's SessionStart hook should run.

    Bundled: directly invokes the installed exe.
    Dev: invokes run.bat next to the source.
    Either way we wrap with `start ""` so the hook returns immediately
    instead of blocking the Claude Code session.
    """
    if IS_FROZEN:
        target = sys.executable
    else:
        target = str(Path(__file__).parent / "run.bat")
    return f'start "" "{target}"  :: tag={HOOK_TAG}'


def _is_our_hook(cmd: str) -> bool:
    cmd = cmd or ""
    return (
        HOOK_TAG in cmd
        or "ClaudeUsageMonitor" in cmd          # bundled exe filename
        or "claude-usage-monitor" in cmd        # dev folder name (legacy)
    )


def install_session_hook() -> tuple[bool, str]:
    """Add our SessionStart hook to ~/.claude/settings.json.

    Returns (ok, message). Replaces any prior hook of ours so a reinstall
    to a different path always points at the current exe.
    """
    if not SETTINGS_PATH.exists():
        return False, "Claude Code settings.json not found."
    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except Exception as e:
        return False, f"Could not parse settings.json: {e}"

    sess = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    sess[:] = [
        entry for entry in sess
        if not any(_is_our_hook(h.get("command", ""))
                   for h in entry.get("hooks", []))
    ]
    sess.append({
        "matcher": "startup|resume|compact",
        "hooks": [{
            "type": "command",
            "command": _launch_command_for_hook(),
            "shell": "powershell",
        }],
    })
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    except Exception as e:
        return False, f"Could not write settings.json: {e}"
    return True, "Hook installed."


def uninstall_session_hook() -> tuple[bool, str]:
    if not SETTINGS_PATH.exists():
        return True, "No settings.json — nothing to remove."
    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except Exception as e:
        return False, f"Could not parse settings.json: {e}"

    sess = data.get("hooks", {}).get("SessionStart")
    if not sess:
        return True, "No SessionStart hook present."
    before = len(sess)
    sess[:] = [
        entry for entry in sess
        if not any(_is_our_hook(h.get("command", ""))
                   for h in entry.get("hooks", []))
    ]
    # Tidy: drop empty containers so we leave settings clean.
    if not sess:
        data["hooks"].pop("SessionStart", None)
    if not data.get("hooks"):
        data.pop("hooks", None)
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    except Exception as e:
        return False, f"Could not write settings.json: {e}"
    removed = before - len(sess)
    return True, f"Removed {removed} hook entry(ies)."


def detect_windows_theme() -> str:
    try:
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            apps_light, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return "light" if apps_light == 1 else "dark"
    except Exception:
        return "light"


@dataclass
class Window:
    start: datetime
    end: datetime
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    messages: int = 0
    by_model: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return (self.input_tokens + self.output_tokens
                + self.cache_read + self.cache_creation)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {"plan": "max5", "theme": "windows"}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def iter_recent_jsonls(since: datetime) -> list[Path]:
    if not PROJECTS_DIR.exists():
        return []
    cutoff = since.timestamp()
    out: list[Path] = []
    for p in PROJECTS_DIR.rglob("*.jsonl"):
        try:
            if p.stat().st_mtime >= cutoff:
                out.append(p)
        except OSError:
            continue
    return out


def _collect_rows(since: datetime) -> list[tuple[datetime, dict, str]]:
    rows: list[tuple[datetime, dict, str]] = []
    for f in iter_recent_jsonls(since):
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = rec.get("message") or {}
                    if msg.get("role") != "assistant":
                        continue
                    usage = msg.get("usage") or {}
                    ts_raw = rec.get("timestamp")
                    if not ts_raw:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if ts < since:
                        continue
                    rows.append((ts, usage, msg.get("model") or "unknown"))
        except OSError:
            continue
    return rows


def _accumulate(rows, start: datetime, end: datetime) -> Window:
    win = Window(start=start, end=end)
    for ts, usage, model in rows:
        if ts < start or ts > end:
            continue
        i = int(usage.get("input_tokens", 0) or 0)
        o = int(usage.get("output_tokens", 0) or 0)
        cr = int(usage.get("cache_read_input_tokens", 0) or 0)
        cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
        win.input_tokens += i
        win.output_tokens += o
        win.cache_read += cr
        win.cache_creation += cw
        win.messages += 1
        win.by_model[model] = win.by_model.get(model, 0) + i + o + cr + cw
    return win


def parse_windows(now: datetime) -> tuple[Window, Window]:
    week_horizon = now - timedelta(days=WEEK_DAYS)
    rows = _collect_rows(week_horizon)

    session_horizon = now - timedelta(hours=SESSION_HOURS)
    session_rows = [r for r in rows if r[0] >= session_horizon]
    if session_rows:
        first = min(r[0] for r in session_rows)
        session = _accumulate(session_rows, first,
                              first + timedelta(hours=SESSION_HOURS))
    else:
        session = Window(start=now, end=now + timedelta(hours=SESSION_HOURS))

    weekly = _accumulate(rows, week_horizon, now)
    weekly.end = week_horizon + timedelta(days=WEEK_DAYS)
    return session, weekly


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_countdown(end: datetime, now: datetime) -> str:
    """HH:MM:SS countdown to `end`. Returns '00:00:00' once expired."""
    secs = int((end - now).total_seconds())
    if secs <= 0:
        return "00:00:00"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ---------- UI ----------

class WindowPanel(tk.Frame):
    """One section in the modal — session OR weekly."""

    def __init__(self, parent, theme: dict, title: str, rolling: bool = False):
        super().__init__(
            parent, bg=theme["panel_bg"],
            highlightbackground=theme["border"], highlightthickness=1,
            bd=0,
        )
        self.theme = theme
        self.rolling = rolling
        self.end: datetime | None = None

        inner = tk.Frame(self, bg=theme["panel_bg"])
        inner.pack(fill="both", expand=True, padx=16, pady=14)

        tk.Label(
            inner, text=title.upper(),
            fg=theme["muted_fg"], bg=theme["panel_bg"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        self.total_var = tk.StringVar()
        tk.Label(
            inner, textvariable=self.total_var,
            fg=theme["fg"], bg=theme["panel_bg"],
            font=("Segoe UI", 28, "bold"),
        ).pack(anchor="w", pady=(2, 4))

        self.bar = ttk.Progressbar(
            inner, maximum=100,
            style="Usage.Horizontal.TProgressbar",
        )
        self.bar.pack(fill="x", pady=(0, 4))

        self.pct_var = tk.StringVar()
        tk.Label(
            inner, textvariable=self.pct_var,
            fg=theme["muted_fg"], bg=theme["panel_bg"],
            font=("Segoe UI", 11),
        ).pack(anchor="w")

        self.reset_var = tk.StringVar()
        tk.Label(
            inner, textvariable=self.reset_var,
            fg=theme["muted_fg"], bg=theme["panel_bg"],
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(2, 0))

        # Prominent countdown — session panels only.
        if not rolling:
            self.countdown_var = tk.StringVar(value="--:--:--")
            cd_frame = tk.Frame(inner, bg=theme["panel_bg"])
            cd_frame.pack(anchor="w", pady=(6, 4))
            tk.Label(
                cd_frame, text="RESETS IN",
                fg=theme["muted_fg"], bg=theme["panel_bg"],
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left", padx=(0, 8))
            tk.Label(
                cd_frame, textvariable=self.countdown_var,
                fg=theme["accent"], bg=theme["panel_bg"],
                font=("Consolas", 22, "bold"),
            ).pack(side="left")
        else:
            self.countdown_var = None

        tk.Label(
            inner, text="BY MODEL",
            fg=theme["muted_fg"], bg=theme["panel_bg"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(8, 2))

        self.model_frame = tk.Frame(inner, bg=theme["panel_bg"])
        self.model_frame.pack(fill="x", pady=(2, 0))

    def update(self, win: Window, cap: int, plan: str, now: datetime):
        pct = (win.total / cap) * 100 if cap else 0
        self.total_var.set(fmt_tokens(win.total))
        self.pct_var.set(f"{pct:.1f}% of {fmt_tokens(cap)} ({plan})")
        self.bar["value"] = min(pct, 100)
        self.end = win.end

        if self.rolling:
            self.reset_var.set(
                f"Rolling 7-day window  ·  {win.messages} messages"
            )
        else:
            self.reset_var.set(
                f"Resets {win.end.astimezone():%a %b %d, %H:%M}"
                f"  ·  {win.messages} messages"
            )
            self.update_countdown(now)

        for child in self.model_frame.winfo_children():
            child.destroy()

        if not win.by_model:
            tk.Label(
                self.model_frame, text="no usage in this window",
                fg=self.theme["muted_fg"], bg=self.theme["panel_bg"],
                font=("Segoe UI", 11, "italic"),
            ).pack(anchor="w")
            return

        for model, tokens in sorted(win.by_model.items(), key=lambda kv: -kv[1]):
            row = tk.Frame(self.model_frame, bg=self.theme["panel_bg"])
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=model,
                fg=self.theme["fg"], bg=self.theme["panel_bg"],
                font=("Segoe UI", 11),
            ).pack(side="left")
            tk.Label(
                row, text=fmt_tokens(tokens),
                fg=self.theme["fg"], bg=self.theme["panel_bg"],
                font=("Consolas", 11, "bold"),
            ).pack(side="right")

    def update_countdown(self, now: datetime):
        if self.countdown_var is None or self.end is None:
            return
        self.countdown_var.set(fmt_countdown(self.end, now))


class Modal:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.cfg = cfg
        self.root = root
        self._tick_scheduled = False
        self._countdown_scheduled = False
        self._logo_img = None

        root.title("Claude Session Usage")
        root.geometry("560x820")
        root.minsize(520, 780)
        root.protocol("WM_DELETE_WINDOW", self.hide)

        # Taskbar / window icon — Windows requires an actual .ico file
        # for the taskbar to pick it up. PNG via iconphoto only covers
        # the title-bar.
        ico = ensure_ico()
        if ico is not None:
            try:
                root.iconbitmap(default=str(ico))
            except tk.TclError:
                pass
        try:
            self._taskbar_icon = ImageTk.PhotoImage(make_icon_image(64))
            root.iconphoto(True, self._taskbar_icon)
        except Exception:
            pass

        self._build_all()

    # -- theme handling --

    def _resolve_theme(self) -> dict:
        pref = self.cfg.get("theme", "windows")
        if pref == "light":
            return LIGHT_THEME
        if pref == "dark":
            return DARK_THEME
        return LIGHT_THEME if detect_windows_theme() == "light" else DARK_THEME

    def _build_all(self):
        self.theme = self._resolve_theme()
        self.root.configure(bg=self.theme["bg"])
        self._configure_styles()
        # Pack order matters: header (top), then bottom (claims its strip),
        # then panels fill what's left. If panels were packed before bottom,
        # an oversized panel could squeeze the bottom row off-screen.
        self._build_header()
        self._build_bottom()
        self._build_panels()

    def _rebuild(self):
        for child in self.root.winfo_children():
            child.destroy()
        self._build_all()
        self.refresh()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Usage.Horizontal.TProgressbar",
            thickness=10,
            background=self.theme["accent"],
            troughcolor=self.theme["trough"],
            bordercolor=self.theme["border"],
            lightcolor=self.theme["accent"],
            darkcolor=self.theme["accent"],
        )
        for combo_style in ("Plan.TCombobox", "Theme.TCombobox"):
            style.configure(
                combo_style,
                fieldbackground=self.theme["panel_bg"],
                background=self.theme["panel_bg"],
                foreground=self.theme["fg"],
                arrowcolor=self.theme["fg"],
                bordercolor=self.theme["border"],
            )
            style.map(
                combo_style,
                fieldbackground=[("readonly", self.theme["panel_bg"])],
                foreground=[("readonly", self.theme["fg"])],
            )

    # -- sections --

    def _build_header(self):
        header = tk.Frame(self.root, bg=self.theme["bg"])
        header.pack(fill="x", padx=24, pady=(20, 4))

        if LOGO_PATH.exists():
            try:
                img = Image.open(LOGO_PATH).convert("RGBA")
                ratio = 64 / img.height
                img = img.resize(
                    (int(img.width * ratio), 64), Image.LANCZOS
                )
                self._logo_img = ImageTk.PhotoImage(img)
                tk.Label(
                    header, image=self._logo_img, bg=self.theme["bg"],
                ).pack(anchor="w")
            except Exception:
                self._logo_text(header)
        else:
            self._logo_text(header)

        tk.Label(
            self.root, text=SUBTITLE,
            fg=self.theme["muted_fg"], bg=self.theme["bg"],
            font=("Segoe UI", 10), wraplength=510, justify="left",
        ).pack(anchor="w", padx=24, pady=(0, 12))

    def _logo_text(self, parent):
        wm = tk.Frame(parent, bg=self.theme["bg"])
        wm.pack(anchor="w")
        tk.Label(
            wm, text="EAGLE POINT",
            fg=self.theme["navy"], bg=self.theme["bg"],
            font=("Segoe UI", 22, "bold"),
        ).pack(side="left")
        tk.Label(
            wm, text="  SOFTWARE",
            fg=self.theme["muted_fg"], bg=self.theme["bg"],
            font=("Segoe UI", 13),
        ).pack(side="left")

    def _build_panels(self):
        self.session_panel = WindowPanel(
            self.root, self.theme, "Session  ·  5-hour window",
        )
        self.session_panel.pack(fill="x", padx=20, pady=8)

        self.weekly_panel = WindowPanel(
            self.root, self.theme, "Weekly  ·  7-day window", rolling=True,
        )
        self.weekly_panel.pack(fill="x", padx=20, pady=8)

    def _build_bottom(self):
        bottom = tk.Frame(self.root, bg=self.theme["bg"])
        bottom.pack(side="bottom", fill="x", padx=24, pady=16)

        tk.Label(
            bottom, text="Plan",
            fg=self.theme["muted_fg"], bg=self.theme["bg"],
            font=("Segoe UI", 11),
        ).pack(side="left")

        self.plan_var = tk.StringVar(value=self.cfg.get("plan", "max5"))
        plan_box = ttk.Combobox(
            bottom, textvariable=self.plan_var,
            values=list(SESSION_CAPS.keys()), state="readonly",
            width=8, style="Plan.TCombobox",
            font=("Segoe UI", 11),
        )
        plan_box.pack(side="left", padx=(8, 18))
        plan_box.bind("<<ComboboxSelected>>", self._on_plan_change)

        tk.Label(
            bottom, text="Theme",
            fg=self.theme["muted_fg"], bg=self.theme["bg"],
            font=("Segoe UI", 11),
        ).pack(side="left")

        self.theme_var = tk.StringVar(value=self.cfg.get("theme", "windows"))
        theme_box = ttk.Combobox(
            bottom, textvariable=self.theme_var,
            values=["windows", "light", "dark"], state="readonly",
            width=9, style="Theme.TCombobox",
            font=("Segoe UI", 11),
        )
        theme_box.pack(side="left", padx=8)
        theme_box.bind("<<ComboboxSelected>>", self._on_theme_change)

    # -- events / ticks --

    def _on_plan_change(self, _evt):
        self.cfg["plan"] = self.plan_var.get()
        save_config(self.cfg)
        self.refresh()

    def _on_theme_change(self, _evt):
        self.cfg["theme"] = self.theme_var.get()
        save_config(self.cfg)
        self._rebuild()

    def _data_tick(self):
        if self.root.state() == "normal":
            self.refresh()
        self.root.after(5000, self._data_tick)

    def _countdown_tick(self):
        if self.root.state() == "normal":
            now = datetime.now(timezone.utc)
            self.session_panel.update_countdown(now)
        self.root.after(1000, self._countdown_tick)

    def refresh(self):
        now = datetime.now(timezone.utc)
        session, weekly = parse_windows(now)
        plan = self.cfg.get("plan", "max5")
        self.session_panel.update(session, SESSION_CAPS.get(plan, 0), plan, now)
        self.weekly_panel.update(weekly, WEEKLY_CAPS.get(plan, 0), plan, now)

    def show(self):
        self.refresh()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if not self._tick_scheduled:
            self._tick_scheduled = True
            self.root.after(5000, self._data_tick)
        if not self._countdown_scheduled:
            self._countdown_scheduled = True
            self.root.after(1000, self._countdown_tick)

    def hide(self):
        self.root.withdraw()


def ensure_ico() -> Path | None:
    """Build a multi-size .ico from icon.png so Windows taskbar/title-bar
    pick it up. Returns the path, or None if generation failed.

    Re-uses an existing icon.ico when it's newer than icon.png.
    """
    try:
        src_img = make_icon_image(256)
        if (ICO_PATH.exists()
                and ICON_PATH.exists()
                and ICO_PATH.stat().st_mtime >= ICON_PATH.stat().st_mtime):
            return ICO_PATH
        src_img.save(
            ICO_PATH, format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)],
        )
        return ICO_PATH
    except Exception:
        return None


def set_app_user_model_id():
    """Tell Windows we're a distinct app, not just pythonw.exe — required
    for the taskbar to use our icon and group windows correctly.
    No-op on non-Windows platforms.
    """
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        pass


def make_icon_image(size: int = 64) -> Image.Image:
    """Square icon used for the system tray and the window/taskbar.

    If `icon.png` exists in the script folder, it's used directly so
    the user can drop in the official Eagle Point mark for pixel-perfect
    branding. Otherwise we draw an approximation: a navy wing-banner
    with a brighter blue arc beneath, on a transparent background so
    the OS / theme provides the surrounding color.
    """
    if ICON_PATH.exists():
        try:
            img = Image.open(ICON_PATH).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.LANCZOS)
            return img
        except Exception:
            pass

    navy = (27, 58, 92, 255)
    blue = (46, 143, 208, 255)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64.0  # scale factor — coords below were tuned at 64px

    # Upper navy banner (sloped parallelogram with a notched corner).
    d.polygon(
        [(4 * s,  20 * s), (50 * s,  6 * s), (60 * s, 12 * s),
         (52 * s, 18 * s), (12 * s, 30 * s)],
        fill=navy,
    )
    # Lower navy chevron (small triangular wedge).
    d.polygon(
        [(20 * s, 30 * s), (46 * s, 22 * s), (32 * s, 40 * s)],
        fill=navy,
    )
    # Light-blue arc at the bottom — bottom half of an ellipse.
    d.pieslice(
        [(12 * s, 30 * s), (58 * s, 58 * s)],
        start=0, end=180, fill=blue,
    )
    return img


_LOCK_PORT = 53792
_lock_socket: socket.socket | None = None


def acquire_single_instance(on_show) -> bool:
    """Bind a localhost socket as a process-wide lock.

    Returns True if we got the lock (we're the leader). If another
    instance owns it, we send a 'show' ping so the leader's window pops
    forward, then return False so the caller can exit cleanly.
    """
    global _lock_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
        s.listen(4)
    except OSError:
        s.close()
        try:
            with socket.create_connection(
                ("127.0.0.1", _LOCK_PORT), timeout=1
            ) as c:
                c.sendall(b"show")
        except OSError:
            pass
        return False

    _lock_socket = s

    def listener():
        while True:
            try:
                conn, _ = s.accept()
            except OSError:
                return
            try:
                data = conn.recv(16)
                if data == b"show":
                    on_show()
            finally:
                conn.close()

    threading.Thread(target=listener, daemon=True).start()
    return True


def maybe_prompt_for_hook(cfg: dict, root: tk.Tk):
    """First-run wizard: ask whether to register our SessionStart hook so
    the app opens automatically with Claude Code. Saves the answer so we
    only ever ask once."""
    if cfg.get("hook_choice") in ("yes", "never"):
        return
    if not SETTINGS_PATH.exists():
        # Claude Code not installed (or not initialized) — silently skip.
        return

    answer = messagebox.askyesnocancel(
        "Open with Claude Code?",
        "Open Claude Usage Monitor automatically whenever Claude Code "
        "starts a session?\n\n"
        "Yes  — set it up now\n"
        "No   — never ask again\n"
        "Cancel — ask me next launch",
        parent=root,
    )
    if answer is True:
        ok, msg = install_session_hook()
        if ok:
            cfg["hook_choice"] = "yes"
            save_config(cfg)
            messagebox.showinfo(
                "Set up",
                "Claude Usage Monitor will now open whenever Claude Code "
                "starts a session.",
                parent=root,
            )
        else:
            messagebox.showerror("Setup failed", msg, parent=root)
    elif answer is False:
        cfg["hook_choice"] = "never"
        save_config(cfg)


def _handle_cli_flags() -> bool:
    """Returns True if a CLI flag was handled and the process should exit."""
    if "--install-hook" in sys.argv:
        ok, msg = install_session_hook()
        print(msg)
        sys.exit(0 if ok else 1)
    if "--uninstall-hook" in sys.argv:
        ok, msg = uninstall_session_hook()
        print(msg)
        sys.exit(0 if ok else 1)
    return False


def main():
    _handle_cli_flags()  # exits if a flag is present

    set_app_user_model_id()  # must run BEFORE creating any window
    ensure_ico()
    cfg = load_config()
    root = tk.Tk()
    modal = Modal(root, cfg)

    if not acquire_single_instance(lambda: root.after(0, modal.show)):
        # Another instance owns the lock; we already pinged it.
        root.destroy()
        sys.exit(0)

    modal.show()
    # Defer the prompt so the main window paints first.
    root.after(600, lambda: maybe_prompt_for_hook(cfg, root))

    def show_modal(_icon=None, _item=None):
        root.after(0, modal.show)

    def quit_app(icon, _item=None):
        icon.stop()
        root.after(0, root.destroy)

    icon = pystray.Icon(
        "claude-usage",
        make_icon_image(),
        "Claude Session Usage",
        menu=pystray.Menu(
            pystray.MenuItem("Show usage", show_modal, default=True),
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    threading.Thread(target=icon.run, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
