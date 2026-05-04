"""History tools registered with the MCP server.

Three tools turn one-shot queries into a longitudinal monitor:

  - ``history_save_snapshot``  persist any tool output for later comparison
  - ``history_diff``            compare two snapshots and report what changed
  - ``history_list``            see what's already stored
"""
from __future__ import annotations

from typing import Any

from ..guardrails import with_meta
from . import diff_snapshots, list_snapshots, save_snapshot


def history_save_snapshot(
    client_id: str,
    tool_name: str,
    result: dict | list,
) -> dict:
    """Persist a tool result so you can diff it later.

    Args:
        client_id: A name for the project / client (e.g. ``"acme"``). One
            directory per client. Use any string — it's filesystem-sanitised.
        tool_name: The tool whose output we're storing (e.g.
            ``"gsc_site_snapshot"``). One directory per tool.
        result: The full ``{"data": ..., "_meta": ...}`` dict the tool
            returned. Storing the meta lets the future diff cite source
            and period.

    Returns the absolute path on disk + a timestamp.
    """
    path = save_snapshot(client_id, tool_name, result)
    return with_meta(
        {
            "saved_to": str(path),
            "client_id": client_id,
            "tool_name": tool_name,
            "size_bytes": path.stat().st_size,
        },
        source="history.save_snapshot",
        extra={"client_id": client_id, "tool_name": tool_name},
    )


def history_diff(
    client_id: str,
    tool_name: str,
    date_from: str,
    date_to: str | None = None,
) -> dict:
    """Compare two snapshots of the same tool at two dates.

    For tools that return keyed lists (rows with ``url`` / ``page`` /
    ``query``), the diff reports added / removed / changed entries. For
    tools that return scalar dicts (e.g. ``gsc_site_snapshot``), the diff
    is a per-field absolute + percent delta.

    Args:
        client_id: same value used at save time.
        tool_name: same value used at save time.
        date_from: ISO date (``YYYY-MM-DD``) of the OLDER snapshot.
        date_to:   ISO date of the NEWER snapshot. Defaults to today.
    """
    return with_meta(
        diff_snapshots(client_id, tool_name, date_from, date_to),
        source="history.diff",
        extra={"client_id": client_id, "tool_name": tool_name},
    )


def history_list(client_id: str, tool_name: str | None = None) -> dict:
    """List snapshots stored for a client (optionally filtered by tool).

    Useful before running ``history_diff`` to know which dates are available.
    """
    snaps = list_snapshots(client_id, tool_name=tool_name)
    return with_meta(
        {
            "client_id": client_id,
            "tool_filter": tool_name,
            "snapshots_count": len(snaps),
            "snapshots": snaps,
        },
        source="history.list",
        extra={"client_id": client_id},
    )
