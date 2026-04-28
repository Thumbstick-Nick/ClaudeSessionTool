# Claude Session Tool

A lightweight Windows app that shows your Claude Code token usage at a glance — current **5-hour session** window and rolling **7-day weekly** window, with a live countdown to reset and a per-model breakdown.

Built by **Eagle Point Software** for internal use; free to fork and adapt.

---

## Install

1. Grab the latest installer from the [Releases page](https://github.com/Thumbstick-Nick/ClaudeSessionTool/releases) — `ClaudeUsageMonitor-Setup-X.Y.Z.exe`.
2. Run it. Per-user install, **no admin rights needed**. Defaults to `%LOCALAPPDATA%\Programs\ClaudeUsageMonitor`.
3. Optional checkboxes during install: Desktop shortcut, Launch at Windows sign-in.

On first launch the app asks whether you'd like it to **open automatically every time you start a Claude Code session**. Yes / No (never ask) / Cancel (ask next launch). Yes adds a `SessionStart` hook to your `~/.claude/settings.json`. Uninstalling the app removes the hook.

---

## What it shows

- **SESSION · 5-HOUR WINDOW** — tokens used in your current rolling 5-hour Claude Code window, with a live `HH:MM:SS` countdown to reset.
- **WEEKLY · 7-DAY WINDOW** — rolling 7-day total.
- **BY MODEL** — token totals per model (e.g. `claude-opus-4-7`, `claude-sonnet-4-6`).
- **Plan dropdown** — `pro`, `max5`, `max20`. Drives the % cap shown.
- **Theme dropdown** — `windows` (follows OS), `light`, `dark`.

Data is read directly from `~/.claude/projects/**/*.jsonl`. No network calls, no auth.

---

## Caveats

- **Plan caps are community estimates** — Anthropic doesn't publish exact token limits, so the % values are approximate. Use the dropdown to match your actual plan.
- **Only Claude Code usage is tracked.** Cowork, the Claude in Chrome extension, and claude.ai chat don't expose local data, so they can't be aggregated.
- **Theme is read once at startup.** If you flip Windows light/dark while the app is open, restart it to pick up the change. (Or pick `light`/`dark` explicitly.)

---

## Build from source

Requires:

- Windows 10/11
- Python 3.11+ ([install](https://www.python.org/downloads/))
- [Inno Setup 6](https://jrsoftware.org/isdl.php) — only needed for the installer step; PyInstaller alone produces a runnable folder.

```powershell
git clone https://github.com/Thumbstick-Nick/ClaudeSessionTool.git
cd ClaudeSessionTool
py -m pip install -r requirements.txt
py build.py
```

Outputs:

- `dist\ClaudeUsageMonitor\` — unpackaged exe + libs (runnable directly).
- `dist-installer\ClaudeUsageMonitor-Setup-<version>.exe` — Inno Setup installer.

If Inno Setup isn't installed, `build.py` skips the installer step and prints a download link.

---

## Develop

For fast iteration without rebuilding the exe:

```powershell
py app.pyw
```

Or double-click `run.bat` (launches headless via `pythonw.exe`).

---

## CLI flags

The bundled exe accepts a couple of one-shot flags useful for scripting / installer hooks:

| Flag | Effect |
|---|---|
| `--install-hook` | Register the Claude Code `SessionStart` hook so the app opens with each session. Same thing the first-run prompt does. |
| `--uninstall-hook` | Remove the hook from `~/.claude/settings.json`. Runs automatically on uninstall. |

---

## Where data lives

| Path | Contents |
|---|---|
| `%APPDATA%\ClaudeUsageMonitor\config.json` | Plan, theme, first-run prompt answer. |
| `%APPDATA%\ClaudeUsageMonitor\icon.ico` | Generated from `icon.png` on first launch. |
| `%LOCALAPPDATA%\Programs\ClaudeUsageMonitor\` | Installed app files. |
| `~\.claude\projects\<slug>\<session-id>.jsonl` | Read-only — your Claude Code session logs. |
| `~\.claude\settings.json` | Modified only when you opt into the hook; the app's entry is tagged so it can be cleanly removed. |

---

## Branding

The Eagle Point Software logo and mark used for the title bar / tray / taskbar are checked into the repo as `logo.png` and `icon.png`. Replace them in a fork to rebrand — `build.py` regenerates the multi-size `.ico` automatically.
