#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-platform installer, uninstaller, and release packager for Antigravity Usage Monitor.
Uses Python 3.9+ stdlib only (works on macOS, Linux, and Windows).
"""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
PLUGIN_ASSETS_DIR = os.path.join(REPO_ROOT, "plugin")
SIDECAR_NAME = "usage_monitor_daemon"
HOOK_KEY = "antigravity-quota-tracker"


def _read_version():
    manifest = os.path.join(PLUGIN_ASSETS_DIR, "plugin.json")
    try:
        with open(manifest, "r", encoding="utf-8") as f:
            return str(json.load(f).get("version") or "0.2.0")
    except Exception:
        return "0.2.0"


def default_plugin_dir():
    return os.path.expanduser(os.path.join("~", ".gemini", "config", "plugins", "usage-monitor"))


def default_data_dir():
    env_dir = os.environ.get("AGY_USAGE_DATA_DIR")
    if env_dir:
        return os.path.expanduser(env_dir)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "agy-usage")
    xdg_data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(xdg_data, "agy-usage")


def default_cli_path():
    if os.name == "nt":
        return os.path.join(default_data_dir(), "bin", "agy-usage.cmd")
    return os.path.expanduser(os.path.join("~", ".local", "bin", "agy-usage"))


def _quote_cmd(parts):
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return " ".join(shlex.quote(p) for p in parts)


def _check_python_version(py_exe):
    if py_exe == sys.executable:
        if sys.version_info < (3, 9):
            raise RuntimeError(f"Python >= 3.9 required, got {sys.version.split()[0]}")
        return
    proc = subprocess.run(
        [py_exe, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
        capture_output=True,
        text=True,
        check=True,
    )
    ver = tuple(int(x) for x in proc.stdout.strip().split(".")[:2])
    if ver < (3, 9):
        raise RuntimeError(f"Python >= 3.9 required ({py_exe} is {proc.stdout.strip()})")


def _preserve_hook_enabled(hooks_path):
    if not os.path.isfile(hooks_path):
        return True
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        hk = cfg.get(HOOK_KEY)
        if isinstance(hk, dict) and "enabled" in hk:
            return bool(hk["enabled"])
    except Exception:
        pass
    return True


def install_plugin(plugin_dir=None, python_exe=None, with_cli=False, cli_path=None):
    py_exe = os.path.abspath(python_exe or sys.executable)
    _check_python_version(py_exe)

    target_dir = os.path.abspath(os.path.expanduser(plugin_dir or default_plugin_dir()))
    sidecar_dir = os.path.join(target_dir, "sidecars", SIDECAR_NAME)
    skills_dst = os.path.join(target_dir, "skills")
    hooks_path = os.path.join(target_dir, "hooks.json")

    os.makedirs(sidecar_dir, exist_ok=True)
    hook_enabled = _preserve_hook_enabled(hooks_path)

    # 1. Copy plugin metadata & assets
    for fname in ("plugin.json", "logo.svg"):
        src_f = os.path.join(PLUGIN_ASSETS_DIR, fname)
        if os.path.isfile(src_f):
            shutil.copy2(src_f, os.path.join(target_dir, fname))

    skills_src = os.path.join(PLUGIN_ASSETS_DIR, "skills")
    if os.path.isdir(skills_src):
        if os.path.isdir(skills_dst):
            shutil.rmtree(skills_dst)
        shutil.copytree(skills_src, skills_dst)

    # 2. Sync self-contained src/*.py into sidecars/usage_monitor_daemon/ and prune stale .py
    copied_py = set()
    for name in sorted(os.listdir(SRC_DIR)):
        if not name.endswith(".py"):
            continue
        src_p = os.path.join(SRC_DIR, name)
        if os.path.isfile(src_p):
            shutil.copy2(src_p, os.path.join(sidecar_dir, name))
            copied_py.add(name)

    for existing in os.listdir(sidecar_dir):
        if existing.endswith(".py") and existing not in copied_py:
            try:
                os.unlink(os.path.join(sidecar_dir, existing))
            except OSError:
                pass

    # 3. Generate self-contained sidecar.json
    sidecar_script = os.path.join(sidecar_dir, "sidecar_daemon.py")
    sidecar_cfg = {
        "command": py_exe,
        "args": [sidecar_script],
        "display_name": "UsageMonitor",
        "description": "Local Antigravity quota ledger, 1-minute shared-pool monitor, SVG watermark chart, model calibration, and diagnostics.",
        "has_web_ui": True,
        "restart_policy": "always",
        "ui_config": {
            "display_name": "UsageMonitor",
            "views": [
                {
                    "entrypoint": "SIDECAR_UI_ENTRYPOINT_AUX_PANE",
                    "path": "/",
                    "title": "UsageMonitor",
                }
            ],
        },
    }
    with open(os.path.join(sidecar_dir, "sidecar.json"), "w", encoding="utf-8") as f:
        json.dump(sidecar_cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # 4. Generate self-contained hooks.json (preserving enabled state across upgrades)
    hook_cmd = _quote_cmd([py_exe, os.path.join(sidecar_dir, "hook.py")])
    hooks_cfg = {
        HOOK_KEY: {
            "enabled": hook_enabled,
            "PreInvocation": [{"type": "command", "command": hook_cmd, "timeout": 8}],
            "Stop": [{"type": "command", "command": hook_cmd, "timeout": 10}],
        }
    }
    with open(hooks_path, "w", encoding="utf-8") as f:
        json.dump(hooks_cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # 5. Optional CLI wrapper
    installed_cli = None
    if with_cli:
        usage_script = os.path.join(sidecar_dir, "agy_usage.py")
        cli_dst = os.path.abspath(os.path.expanduser(cli_path or default_cli_path()))
        os.makedirs(os.path.dirname(cli_dst), exist_ok=True)
        if os.name == "nt" or cli_dst.lower().endswith(".cmd"):
            content = f'@echo off\r\n"{py_exe}" "{usage_script}" %*\r\n'
            with open(cli_dst, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            content = f"#!/bin/sh\nexec {shlex.quote(py_exe)} {shlex.quote(usage_script)} \"$@\"\n"
            with open(cli_dst, "w", encoding="utf-8") as f:
                f.write(content)
            st = os.stat(cli_dst)
            os.chmod(cli_dst, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed_cli = cli_dst

    return {
        "pluginDir": target_dir,
        "sidecarDir": sidecar_dir,
        "python": py_exe,
        "hookEnabled": hook_enabled,
        "cliPath": installed_cli,
    }


def uninstall_plugin(plugin_dir=None, purge_data=False, cli_path=None):
    target_dir = os.path.abspath(os.path.expanduser(plugin_dir or default_plugin_dir()))
    removed_plugin = False
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)
        removed_plugin = True

    cli_dst = os.path.abspath(os.path.expanduser(cli_path or default_cli_path()))
    removed_cli = False
    if os.path.isfile(cli_dst) or os.path.islink(cli_dst):
        os.unlink(cli_dst)
        removed_cli = True

    removed_data = False
    if purge_data:
        dd = os.path.abspath(default_data_dir())
        if os.path.isdir(dd):
            shutil.rmtree(dd)
            removed_data = True

    return {
        "removedPlugin": removed_plugin,
        "removedCli": removed_cli,
        "removedData": removed_data,
        "pluginDir": target_dir,
    }


def package_release(out_dir=None):
    version = _read_version()
    target_out = os.path.abspath(os.path.expanduser(out_dir or os.path.join(REPO_ROOT, "dist")))
    os.makedirs(target_out, exist_ok=True)
    archive_name = f"agy-usagemonitor-{version}.zip"
    zip_path = os.path.join(target_out, archive_name)
    sha_path = zip_path + ".sha256"

    include_roots = (
        "src",
        "plugin",
        "scripts",
        "tests",
        "install.sh",
        "uninstall.sh",
        "install.ps1",
        "uninstall.ps1",
        "install.bat",
        "uninstall.bat",
        "README.md",
        "README.zh-CN.md",
        "CHANGELOG.md",
        "LICENSE",
    )
    skip_dirs = {"__pycache__", ".git", ".pytest_cache", "dist", ".venv"}
    skip_files = {".DS_Store", "Thumbs.db"}

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in include_roots:
            full = os.path.join(REPO_ROOT, entry)
            if os.path.isfile(full):
                arc = f"agy-usagemonitor-{version}/{entry}"
                zf.write(full, arc)
            elif os.path.isdir(full):
                for root, dirs, files in os.walk(full):
                    dirs[:] = sorted(d for d in dirs if d not in skip_dirs)
                    for fn in sorted(files):
                        if fn in skip_files or fn.endswith((".pyc", ".pyo")):
                            continue
                        fp = os.path.join(root, fn)
                        rel = os.path.relpath(fp, REPO_ROOT).replace(os.sep, "/")
                        zf.write(fp, f"agy-usagemonitor-{version}/{rel}")

    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    digest = h.hexdigest()
    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{digest}  {archive_name}\n")

    return {"zipPath": zip_path, "sha256Path": sha_path, "sha256": digest, "version": version}


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(description="Manage Antigravity Usage Monitor plugin")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inst = sub.add_parser("install", help="Install self-contained plugin into Antigravity")
    p_inst.add_argument("--plugin-dir", default=None, help="Override plugin target directory")
    p_inst.add_argument("--python", dest="python_exe", default=None, help="Explicit Python >=3.9 path")
    p_inst.add_argument("--with-cli", action="store_true", help="Also install agy-usage CLI wrapper")
    p_inst.add_argument("--cli-path", default=None, help="Override CLI wrapper destination")

    p_un = sub.add_parser("uninstall", help="Uninstall plugin from Antigravity")
    p_un.add_argument("--plugin-dir", default=None, help="Override plugin directory")
    p_un.add_argument("--purge-data", action="store_true", help="Also delete runtime ledger/monitor data")
    p_un.add_argument("--cli-path", default=None, help="Override CLI wrapper path")

    p_pkg = sub.add_parser("package", help="Build release zip + sha256 archive")
    p_pkg.add_argument("--out", default=None, help="Output directory (default: dist/)")

    args = parser.parse_args()
    if args.cmd == "install":
        info = install_plugin(
            plugin_dir=args.plugin_dir,
            python_exe=args.python_exe,
            with_cli=args.with_cli,
            cli_path=args.cli_path,
        )
        print(f"Installed Antigravity Usage Monitor v{_read_version()}")
        print(f"  Plugin dir : {info['pluginDir']}")
        print(f"  Sidecar    : {info['sidecarDir']}")
        print(f"  Python     : {info['python']}")
        print(f"  Hook state : {'ON' if info['hookEnabled'] else 'OFF'}")
        if info["cliPath"]:
            print(f"  CLI wrapper: {info['cliPath']}")
        print("\nNext: Enable 'usage-monitor' in Antigravity -> Extensions / Plugins.")
    elif args.cmd == "uninstall":
        info = uninstall_plugin(
            plugin_dir=args.plugin_dir,
            purge_data=args.purge_data,
            cli_path=args.cli_path,
        )
        print(f"Uninstalled plugin dir ({info['pluginDir']}): removed={info['removedPlugin']}")
        if info["removedCli"]:
            print("Removed CLI wrapper.")
        if info["removedData"]:
            print("Purged runtime ledger and monitor data.")
        else:
            print("Runtime ledger & monitor logs were preserved.")
    elif args.cmd == "package":
        info = package_release(out_dir=args.out)
        print(f"Packaged {info['zipPath']}")
        print(f"SHA-256 : {info['sha256']}")


if __name__ == "__main__":
    main()
