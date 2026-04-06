"""FS Sync Daemon — keeps local folder structure in sync with server state.

Polls server /api/pchat/view, serializes channels + messages into root/pchat/ folders.
Each node = folder + _meta.json + _data.json.

Usage:
    python tools/fs_sync.py [--interval 5] [--root root] [--server http://127.0.0.1:5002]
"""

import argparse
import json
import time
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError


def fetch_json(url: str, method: str = "GET", body: dict | None = None) -> dict:
    """Simple HTTP JSON fetch without dependencies."""
    if body is not None:
        data = json.dumps(body).encode()
        req = Request(url, data=data)
        req.add_header("Content-Type", "application/json")
    else:
        req = Request(url)
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def write_json(path: Path, data: dict):
    """Write JSON file, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def sync_node(node_dir: Path, meta: dict, data: dict | None = None):
    """Ensure a node folder exists with _meta.json and _data.json."""
    node_dir.mkdir(parents=True, exist_ok=True)
    write_json(node_dir / "_meta.json", meta)
    write_json(node_dir / "_data.json", data or {})


def sync_channels(root: Path, channels: list[dict]):
    """Sync channel list to root/pchat/channels/."""
    channels_dir = root / "pchat" / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)

    # Ensure channels container meta
    if not (channels_dir / "_meta.json").exists():
        write_json(channels_dir / "_meta.json", {"type": "channels", "name": "channels"})
        write_json(channels_dir / "_data.json", {})

    # Sync each channel
    existing = {d.name for d in channels_dir.iterdir() if d.is_dir() and not d.name.startswith("_")}
    server_names = set()

    for ch in channels:
        name = ch.get("name", ch.get("meta", {}).get("name", ""))
        if not name:
            continue
        server_names.add(name)
        ch_dir = channels_dir / name
        meta = ch.get("meta", {"type": "channel", "name": name})
        sync_node(ch_dir, meta)

    return server_names


def sync_messages(root: Path, channel_name: str, messages: list[dict]):
    """Sync messages into root/pchat/channels/{channel}/."""
    ch_dir = root / "pchat" / "channels" / channel_name
    ch_dir.mkdir(parents=True, exist_ok=True)

    for msg in messages:
        msg_name = msg.get("name", "")
        if not msg_name:
            continue
        msg_dir = ch_dir / msg_name
        meta = msg.get("meta", {"type": "message"})
        data = msg.get("data", {})
        sync_node(msg_dir, meta, data)


def do_sync(server: str, root: Path, verbose: bool = False):
    """One sync cycle: fetch state from server, write to FS."""
    # Get channel list
    try:
        state = fetch_json(f"{server}/api/pchat/view", method="POST",
                           body={"channel": None, "msg_limit": 0, "user": "sync"})
    except URLError as e:
        if verbose:
            print(f"  [!] Server unreachable: {e}")
        return False

    channels = state.get("channels", [])
    server_names = sync_channels(root, channels)

    if verbose:
        print(f"  channels: {sorted(server_names)}")

    # For each channel, fetch messages
    for ch_name in sorted(server_names):
        try:
            ch_state = fetch_json(f"{server}/api/pchat/view", method="POST",
                                  body={"channel": ch_name, "msg_limit": 200, "user": "sync"})
            messages = ch_state.get("messages", [])
            sync_messages(root, ch_name, messages)
            if verbose:
                print(f"    {ch_name}: {len(messages)} msgs")
        except URLError:
            pass

    return True


def main():
    parser = argparse.ArgumentParser(description="FS Sync Daemon")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds (0 = once)")
    parser.add_argument("--root", type=str, default="root", help="Root directory path")
    parser.add_argument("--server", type=str, default="http://127.0.0.1:5002", help="Server URL")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    print(f"FS Sync -> {root}")
    print(f"Server  -> {args.server}")
    print(f"Interval: {args.interval}s" if args.interval > 0 else "Mode: once")
    print()

    # Ensure root structure
    (root / "pchat").mkdir(parents=True, exist_ok=True)
    if not (root / "_meta.json").exists():
        write_json(root / "_meta.json", {"type": "root"})
    if not (root / "pchat" / "_meta.json").exists():
        write_json(root / "pchat" / "_meta.json", {"type": "pchat", "name": "pchat"})
        write_json(root / "pchat" / "_data.json", {})

    if args.interval == 0:
        # One-shot
        print("[sync]")
        ok = do_sync(args.server, root, verbose=args.verbose)
        print("  done." if ok else "  failed.")
        return

    # Loop
    print("Running... (Ctrl+C to stop)\n")
    while True:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] sync", end="", flush=True)
        ok = do_sync(args.server, root, verbose=args.verbose)
        if not args.verbose:
            print(" ok" if ok else " fail")
        else:
            print()
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
