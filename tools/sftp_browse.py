#!/usr/bin/env python3
"""Browse the Protek Cyber SFTP webspace.

Credentials come from environment variables (never hard-code them):
    SFTP_HOST, SFTP_PORT (default 22), SFTP_USER, SFTP_PASS

Usage:
    python3 tools/sftp_browse.py ls   [PATH] [--depth N]
    python3 tools/sftp_browse.py find PATTERN [PATH] [--depth N]
    python3 tools/sftp_browse.py cat  REMOTE_FILE
    python3 tools/sftp_browse.py get  REMOTE_PATH LOCAL_DIR   (file or dir, recursive)
"""
import argparse
import fnmatch
import os
import stat
import sys

import paramiko

SKIP_DIRS = {"node_modules", ".git", "vendor", "cache", ".cache"}


def connect():
    host = os.environ["SFTP_HOST"]
    port = int(os.environ.get("SFTP_PORT", "22"))
    transport = paramiko.Transport((host, port))
    transport.connect(username=os.environ["SFTP_USER"], password=os.environ["SFTP_PASS"])
    return transport, paramiko.SFTPClient.from_transport(transport)


def fmt_size(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def walk(sftp, path, depth, max_depth):
    try:
        entries = sorted(sftp.listdir_attr(path), key=lambda e: (not stat.S_ISDIR(e.st_mode), e.filename))
    except IOError as exc:
        yield depth, path, None, f"<error: {exc}>"
        return
    for e in entries:
        full = f"{path.rstrip('/')}/{e.filename}"
        yield depth, full, e, None
        if stat.S_ISDIR(e.st_mode) and depth < max_depth and e.filename not in SKIP_DIRS:
            yield from walk(sftp, full, depth + 1, max_depth)


def cmd_ls(sftp, path, max_depth):
    for depth, full, e, err in walk(sftp, path, 0, max_depth):
        indent = "  " * depth
        if err:
            print(f"{indent}{err}")
        elif stat.S_ISDIR(e.st_mode):
            print(f"{indent}{os.path.basename(full)}/")
        else:
            print(f"{indent}{os.path.basename(full)}  ({fmt_size(e.st_size)})")


def cmd_find(sftp, pattern, path, max_depth):
    for _, full, e, _err in walk(sftp, path, 0, max_depth):
        if e and fnmatch.fnmatch(e.filename.lower(), pattern.lower()):
            print(full + ("/" if stat.S_ISDIR(e.st_mode) else ""))


def cmd_get(sftp, remote, local):
    attr = sftp.stat(remote)
    target = os.path.join(local, os.path.basename(remote.rstrip("/")))
    if stat.S_ISDIR(attr.st_mode):
        os.makedirs(target, exist_ok=True)
        for e in sftp.listdir_attr(remote):
            cmd_get(sftp, f"{remote.rstrip('/')}/{e.filename}", target)
    else:
        os.makedirs(local, exist_ok=True)
        sftp.get(remote, target)
        print(f"downloaded {remote} -> {target}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("ls"); ls.add_argument("path", nargs="?", default="."); ls.add_argument("--depth", type=int, default=0)
    fd = sub.add_parser("find"); fd.add_argument("pattern"); fd.add_argument("path", nargs="?", default="."); fd.add_argument("--depth", type=int, default=6)
    ct = sub.add_parser("cat"); ct.add_argument("path")
    gt = sub.add_parser("get"); gt.add_argument("path"); gt.add_argument("local")
    args = p.parse_args()

    transport, sftp = connect()
    try:
        if args.cmd == "ls":
            cmd_ls(sftp, args.path, args.depth)
        elif args.cmd == "find":
            cmd_find(sftp, args.pattern, args.path, args.depth)
        elif args.cmd == "cat":
            with sftp.open(args.path) as fh:
                sys.stdout.write(fh.read().decode("utf-8", errors="replace"))
        elif args.cmd == "get":
            cmd_get(sftp, args.path, args.local)
    finally:
        sftp.close()
        transport.close()


if __name__ == "__main__":
    main()
