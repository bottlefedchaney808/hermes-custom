#!/usr/bin/env python3
"""local_model.py — see, unload, and stop the managed llama-server.

Why this exists
---------------
Hermes runs local models behind a managed `llama-server` router (default
127.0.0.1:18434). Two facts make it feel like the model is "always on":

1. **The idle-unloader is not independent.** `hermes_cli/local_runtime/
   bootstrap.py::_start_idle_sweeper` runs the 15-minute idle unload as a daemon
   thread *inside the process that spawned the server*, looping
   `while sup.proc is not None`. Kill or restart that process (a gateway
   restart does exactly this) and the server keeps running with the weights
   resident and NOTHING left that will ever unload them.
2. **A stopped server gets respawned on demand.** Any Hermes process routed at a
   local model starts one - most often a running gateway for a profile whose
   model is local. Killing the process without stopping that gateway just means
   it comes back the next time something asks for the model.

So: `unload` frees the card and keeps the router warm; `stop` also ends the
process. Neither stops whatever will ask for the model again — see `status`,
which names the likely respawner.

Stdlib only, so it runs under any Python. psutil is used when present (it is, in
the Hermes venv) for a clean process-tree kill.

Usage
-----
    local-model            status  (default)
    local-model unload     free VRAM, leave the router listening
    local-model stop       unload, then terminate the router + children
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
RUNTIMES = HERMES_HOME / "runtimes"
STATE = RUNTIMES / "server.json"
KEY_FILE = RUNTIMES / ".api_key"
DEFAULT_PORT = 18434
# Statuses that mean "weights are on the card" (supervisor._RESIDENT).
RESIDENT = ("loaded", "ready")


# A Windows console is cp1252; reconfiguring means output can never raise
# UnicodeEncodeError and take the whole command down mid-unload.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _api_key() -> str:
    try:
        return KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _psutil():
    try:
        import psutil
        return psutil
    except Exception:
        return None


def _server_procs() -> list:
    """Every running llama-server, newest last. Uses psutil when available and
    falls back to WMIC-free PowerShell so this still works outside the venv."""
    ps = _psutil()
    out = []
    if ps:
        for p in ps.process_iter(["name", "exe", "cmdline", "ppid", "create_time"]):
            try:
                name = (p.info.get("name") or "").lower()
                if "llama-server" in name:
                    out.append(p)
            except Exception:
                continue
        out.sort(key=lambda p: p.info.get("create_time") or 0)
        return out
    return []


def _port_from(proc) -> int:
    """The port the router actually bound. _stable_port() falls back to an
    ephemeral port when 18434 is taken, so never assume the default."""
    try:
        cmd = proc.info.get("cmdline") or []
        if "--port" in cmd:
            return int(cmd[cmd.index("--port") + 1])
    except Exception:
        pass
    return DEFAULT_PORT


def _key_from(proc) -> str:
    """The key this router was actually STARTED with, off its own argv.

    `runtimes/.api_key` is written by _stable_api_key(), but it can be absent or
    rotated relative to a long-running server (on this box the file was gone
    entirely while the server still enforced its key) — and then every call gets
    a 401. The process's own --api-key is the only source that cannot disagree
    with the process. The file is the fallback for anything argv doesn't show.
    """
    try:
        cmd = proc.info.get("cmdline") or []
        if "--api-key" in cmd:
            return cmd[cmd.index("--api-key") + 1]
    except Exception:
        pass
    return _api_key()


def _request(port: int, route: str, body: dict | None = None, timeout: int = 30,
             key: str = "") -> dict:
    url = f"http://127.0.0.1:{port}{route}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


def _models(port: int, key: str = "") -> dict:
    try:
        data = _request(port, "/models", key=key).get("data", [])
    except Exception as e:
        print(f"  could not query the router on :{port} — {e}")
        return {}
    return {m["id"]: (m.get("status") or {}).get("value", "unknown") for m in data}


def _running_gateways() -> list[str]:
    """Profiles whose gateway is up — these are what respawn the server."""
    ps = _psutil()
    if not ps:
        return []
    names = []
    for p in ps.process_iter(["name", "cmdline"]):
        try:
            cmd = p.info.get("cmdline") or []
            if "gateway" not in cmd or "run" not in cmd:
                continue
            names.append(cmd[cmd.index("--profile") + 1] if "--profile" in cmd else "default")
        except Exception:
            continue
    return sorted(set(names))


def cmd_status() -> int:
    procs = _server_procs()
    print(f"HERMES_HOME : {HERMES_HOME}")

    if not procs:
        print("llama-server: not running. Your card is free.")
        print("")
        print("It starts ON DEMAND the next time something routes a request at a")
        print("local model. It was not seen to respawn on its own while idle, but a")
        print("running gateway will start it again as soon as a request needs it.")
        return 0
    ps = _psutil()
    print(f"state file  : {STATE}  {'(present — managed)' if STATE.is_file() else '(MISSING — unmanaged/orphaned)'}")
    for p in procs:
        port = _port_from(p)
        ppid = p.info.get("ppid") or 0
        parent_alive = bool(ppid and ps and ps.pid_exists(ppid))
        print(f"\nllama-server pid={p.pid} port={port}")
        print(f"  parent pid={ppid} {'(alive)' if parent_alive else '(GONE — orphaned)'}")
        if not parent_alive:
            print("  !! orphaned: its idle-unload sweeper died with the parent, so these")
            print("    weights will stay resident forever. `stop` is the only way out.")
        models = _models(port, _key_from(p))
        if models:
            for mid, status in models.items():
                flag = "  <== ON THE CARD" if status in RESIDENT else ""
                print(f"  model {mid}: {status}{flag}")
        else:
            print("  (no model list — router not answering)")
    gws = _running_gateways()
    if gws:
        print(f"\nrunning gateways: {', '.join(gws)}")
        print("  A gateway for a profile whose model is LOCAL will respawn the server")
        print("  on demand. To stop that too:  hermes -p <profile> gateway stop")
        print("  (note: '-p default' targets the ACTIVE profile, not the one named")
        print("   'default' — switch to it with `hermes profile use default` instead.)")
    return 0


def cmd_unload() -> int:
    procs = _server_procs()
    if not procs:
        print("llama-server is not running — nothing to unload.")
        return 0
    freed = 0
    for p in procs:
        port = _port_from(p)
        key = _key_from(p)
        for mid, status in _models(port, key).items():
            if status not in RESIDENT:
                continue
            try:
                _request(port, "/models/unload", {"model": mid}, timeout=120, key=key)
                print(f"unloaded {mid} (pid {p.pid}, port {port})")
                freed += 1
            except Exception as e:
                print(f"could not unload {mid}: {e}")
    if not freed:
        print("no resident models — the card is already free (router still listening).")
    return 0


def cmd_stop() -> int:
    cmd_unload()
    procs = _server_procs()
    if not procs:
        return 0
    ps = _psutil()
    for p in procs:
        # Children hold the VRAM; terminating only the router orphans them with
        # the weights still resident (supervisor._terminate_tree makes the same point).
        children = []
        if ps:
            try:
                children = p.children(recursive=True)
            except Exception:
                children = []
        for c in children + [p]:
            try:
                c.terminate()
            except Exception:
                pass
        try:
            p.wait(timeout=15)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        for c in children:
            try:
                if c.is_running():
                    c.kill()
            except Exception:
                pass
        print(f"stopped llama-server pid={p.pid} (+{len(children)} child process(es))")
    # A stale state file would point other processes at a dead endpoint.
    try:
        STATE.unlink(missing_ok=True)
    except OSError:
        pass
    return 0


def main() -> int:
    action = (sys.argv[1] if len(sys.argv) > 1 else "status").lower().lstrip("-")
    if action in ("status", "s"):
        return cmd_status()
    if action in ("unload", "u", "free"):
        return cmd_unload()
    if action in ("stop", "kill", "x"):
        return cmd_stop()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
