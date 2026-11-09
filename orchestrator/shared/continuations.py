"""Live Databricks metastore-pause continuations, keyed by deployment instance ID.

Kept outside ``activities.addons`` because a hosted hotfix reloads that module; a reload must not drop the
events that a paused add-on is waiting on and that ``POST /api/addons/{id}/continue`` sets.
"""
from __future__ import annotations

import asyncio

CONTINUATIONS: dict[str, asyncio.Event] = {}
