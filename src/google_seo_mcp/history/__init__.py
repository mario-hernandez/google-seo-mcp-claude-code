"""Persistent history of tool outputs — turns the MCP from one-shot queries
into a longitudinal monitoring system.

Snapshots live in ``~/.google-seo-mcp/history/{client_id}/{tool_name}/{date}.json``
by default. Override the root with ``GOOGLE_SEO_HISTORY_DIR``.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _root() -> Path:
    """Where snapshots are stored. Defaults to ``~/.google-seo-mcp/history``."""
    raw = os.getenv("GOOGLE_SEO_HISTORY_DIR")
    if raw:
        p = Path(raw).expanduser()
    else:
        p = Path.home() / ".google-seo-mcp" / "history"
    p.mkdir(parents=True, exist_ok=True)
    return p


_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe(name: str) -> str:
    """Coerce a client_id / tool_name into a filesystem-safe segment."""
    return _SAFE_RE.sub("-", (name or "unknown").strip()).strip("-") or "unknown"


def snapshot_path(client_id: str, tool_name: str, day: str | None = None) -> Path:
    """Path of the snapshot file for a given client + tool + day (default: today)."""
    day = day or date.today().isoformat()
    return _root() / _safe(client_id) / _safe(tool_name) / f"{day}.json"


def save_snapshot(client_id: str, tool_name: str, result: Any) -> Path:
    """Persist a tool result. One file per (client, tool, day) — overwrites if
    you re-run on the same day. Returns the absolute path."""
    p = snapshot_path(client_id, tool_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return p


def load_snapshot(client_id: str, tool_name: str, day: str) -> dict[str, Any] | None:
    """Read back a snapshot. Returns None if it doesn't exist."""
    p = snapshot_path(client_id, tool_name, day)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def list_snapshots(client_id: str, tool_name: str | None = None) -> list[dict[str, Any]]:
    """List all snapshots for a client (optionally filtered by tool)."""
    base = _root() / _safe(client_id)
    if not base.exists():
        return []
    out = []
    if tool_name:
        target = base / _safe(tool_name)
        if target.exists():
            for f in sorted(target.glob("*.json")):
                out.append({
                    "tool": tool_name,
                    "date": f.stem,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                })
    else:
        for tool_dir in sorted(base.iterdir()):
            if not tool_dir.is_dir():
                continue
            for f in sorted(tool_dir.glob("*.json")):
                out.append({
                    "tool": tool_dir.name,
                    "date": f.stem,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                })
    return out


def diff_snapshots(
    client_id: str,
    tool_name: str,
    date_from: str,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Compare two snapshots of the same tool at two dates.

    Returns a structured diff for the common shapes our tools emit:
    ``{"data": <list-or-dict>, "_meta": {...}}``. For lists keyed by ``url``,
    ``query`` or ``page``, computes added / removed / changed by key. For
    dicts of scalars, computes per-field deltas.
    """
    a = load_snapshot(client_id, tool_name, date_from)
    if a is None:
        return {"error": f"No snapshot for {client_id}/{tool_name} on {date_from}"}
    if date_to is None:
        date_to = date.today().isoformat()
    b = load_snapshot(client_id, tool_name, date_to)
    if b is None:
        return {"error": f"No snapshot for {client_id}/{tool_name} on {date_to}"}

    data_a = a.get("data") if isinstance(a, dict) else a
    data_b = b.get("data") if isinstance(b, dict) else b

    out: dict[str, Any] = {
        "client_id": client_id,
        "tool_name": tool_name,
        "from_date": date_from,
        "to_date": date_to,
    }

    # Case 1: list of records keyed by a stable identifier
    if isinstance(data_a, list) and isinstance(data_b, list):
        key = _detect_list_key(data_a) or _detect_list_key(data_b)
        if key:
            ax = {(r.get(key) or ""): r for r in data_a if isinstance(r, dict)}
            bx = {(r.get(key) or ""): r for r in data_b if isinstance(r, dict)}
            keys_a, keys_b = set(ax), set(bx)
            added = sorted(keys_b - keys_a)
            removed = sorted(keys_a - keys_b)
            common = keys_a & keys_b
            changed: list[dict] = []
            for k in sorted(common):
                ra, rb = ax[k], bx[k]
                field_deltas = _scalar_delta(ra, rb)
                if field_deltas:
                    changed.append({"key": k, "deltas": field_deltas})
            out["diff_type"] = "keyed_list"
            out["key_field"] = key
            out["added_count"] = len(added)
            out["removed_count"] = len(removed)
            out["changed_count"] = len(changed)
            out["added"] = added[:50]
            out["removed"] = removed[:50]
            out["changed"] = changed[:50]
            return out
        out["diff_type"] = "unkeyed_list"
        out["count_from"] = len(data_a)
        out["count_to"] = len(data_b)
        out["delta"] = len(data_b) - len(data_a)
        return out

    # Case 2: dict — flat scalar diff
    if isinstance(data_a, dict) and isinstance(data_b, dict):
        out["diff_type"] = "dict"
        out["deltas"] = _scalar_delta(data_a, data_b, recurse=True)
        return out

    out["diff_type"] = "incompatible_shapes"
    out["a_type"] = type(data_a).__name__
    out["b_type"] = type(data_b).__name__
    return out


def _detect_list_key(rows: list) -> str | None:
    """Find a likely identifier field in a list of records."""
    if not rows or not isinstance(rows[0], dict):
        return None
    for candidate in ("url", "page", "query", "site_url", "id", "name"):
        if candidate in rows[0]:
            return candidate
    return None


def _scalar_delta(a: dict, b: dict, recurse: bool = False) -> dict[str, Any]:
    """Per-field numeric delta. Strings are reported only if they changed."""
    out: dict[str, Any] = {}
    for k in set(a) | set(b):
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[k] = {
                "from": va,
                "to": vb,
                "absolute": vb - va,
                "percent": round((vb - va) / va * 100, 2) if va else None,
            }
        elif recurse and isinstance(va, dict) and isinstance(vb, dict):
            inner = _scalar_delta(va, vb, recurse=True)
            if inner:
                out[k] = inner
        else:
            out[k] = {"from": va, "to": vb}
    return out
