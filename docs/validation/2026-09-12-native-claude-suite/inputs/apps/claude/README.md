# Claude for uOS

Claude is a native C128 app in the uOS suite. Select **Claude** on the desktop,
or press **A**. It uses the 80-column VDC as a terminal and the 40-column VIC
screen for session information. Claude Code runs on your Linux host, using
that host's login, project directory and normal Claude permissions.

Build the suite with `python3 -B build-native-desktop.py`. This requires cc65
(`cl65` and `ld65`) in addition to Python 3, 64tass and VICE's `c1541`.
Both `target/native-desktop/uos128.d64` and
`target/native-desktop/workspace.d64` contain the native `CLAUDE` app.

On the Linux host, install the bridge dependency in a virtual environment:

```sh
python3 -m venv .venv-claude
.venv-claude/bin/python -m pip install -r apps/claude/requirements.txt
.venv-claude/bin/python apps/claude/run.py --connect C128_ADDRESS:3000 --cwd /path/to/project
```

Replace `C128_ADDRESS` with the Ultimate's address. Install and sign in to
Claude Code on that host first; its `claude` command must be on PATH. The bridge
starts that command in an 80×25 PTY. `--command` selects another terminal
program when diagnosing the connection. The protocol sends terminal cells
and keystrokes; the client does not store an API key on the C128.

Configure the Ultimate modem for **DE00/NMI**, **38400 baud**, TCP port **3000**,
and dropping the connection when DTR goes low. Launch the app from the running
uOS desktop and press **Return** to connect. The app refuses an already active
serial port and reports an unavailable port on its launch page.

| Key | Action |
|---|---|
| Return on the launch page | Open the configured serial connection |
| F8 | End the terminal session and return to the desktop |
| Escape on the launch page | Return to the desktop |
| Escape during a session | Send Escape to Claude |
| Help during a session | Request a full repaint and rearm modem answering |

Returning closes the host PTY session. Start the bridge again for a new
session; the launcher does not run a host service automatically. The supplied
bridge uses only its selected serial TCP connection. It does not mount disks,
reset the C128 or change Ultimate settings.

The native port saves and restores the borrowed lowercase VDC font, affected
display registers, console selection, border, cc65 zero page and NMI vector.
It uses uOS keyboard accounting and releases its entire app allocation on
return. Bells flash the VIC border. Screen runs are clipped before touching
VDC RAM, and serial transmission waits are bounded.

This port is based on [marc-shade/claude-c128](https://github.com/marc-shade/claude-c128)
at `b2941591f0caee460dfbfbec7d490a8af00c71a5`. [UPSTREAM.json](UPSTREAM.json)
records original file hashes; [LICENSE](LICENSE) retains Marc Shade's MIT
notice. Native adaptations live in `src/native/claude/`; host adaptations
live in this directory's `host/`. [PROTOCOL.md](PROTOCOL.md) describes the wire
format. The upstream BASIC-started client and reset/bootstrap helpers are
not part of the native launch path.

Native qualification is tracked separately from upstream hardware claims.
The earlier uOS ABI 1.9 physical pass does not qualify this ABI 1.10 serial app.

The [software qualification](../../docs/validation/2026-09-12-native-claude-suite/README.md)
passes 30 native CPU suites, 34 host checks and four VICE workflows. Both F8
and host-process exit return to the desktop with the original font and NMI
state restored. Native physical modem qualification remains pending.
