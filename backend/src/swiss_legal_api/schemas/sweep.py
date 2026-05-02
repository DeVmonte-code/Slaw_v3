"""Schemas for the scheduled-sweep stateful layer (Task #22).

Three concepts:

* :class:`UserRecord` — the persistent shape of one stored user
  (``user_id`` + the full :class:`ContextProfile` + notification opt-in).
* :class:`Alert` — one diff event surfaced to the user
  (``NEW`` / ``GONE`` / ``UPDATED``). Persisted in its own table so the
  inbox endpoint can paginate and mark-as-read without re-deriving
  diffs from the scan history.
* :class:`AlertKind` — closed enum of diff change types.

The ``Alert.payload`` deliberately copies a small, stable subset of the
referenced :class:`Benefit` rather than a foreign-key into a scan row.
Two reasons: (1) the inbox should still render correctly after the
referenced scan ages out of the per-user retention window; (2) GONE
alerts have no current Benefit to point at, so the payload must be
self-contained anyway.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .context_profile import ContextProfile

AlertKind = Literal["NEW", "GONE", "UPDATED"]


class UserRecord(BaseModel):
    """One row of the ``users`` table — what the API returns and stores."""

    user_id: str = Field(..., min_length=1, max_length=128)
    profile: ContextProfile
    notify_enabled: bool = True
    created_at: str
    last_seen_at: str


class UserProfileUpsert(BaseModel):
    """Request body for ``POST /users/{user_id}/profile``."""

    profile: ContextProfile
    notify_enabled: bool = True


class AlertPayload(BaseModel):
    """Self-contained snapshot of the entitlement an alert refers to.

    Stored as JSON inside the ``alerts`` row — see module docstring for
    why this is a copy rather than a foreign key.
    """

    entitlement_id: str
    title: str
    category: str
    estimated_value_chf_min: float
    estimated_value_chf_max: float
    # For UPDATED alerts: previous value range, so the frontend can render
    # "estimated value: 600-1200 CHF (was 400-900 CHF)" without joining
    # against the historical scan row.
    previous_estimated_value_chf_min: float | None = None
    previous_estimated_value_chf_max: float | None = None
    # The list of (sr_number, article) pairs whose underlying Fedlex
    # text changed, when this alert was triggered by a Fedlex amendment
    # rather than a profile/catalog delta. Empty for organic NEW/GONE
    # alerts. The frontend renders this as "your cited article was
    # amended" copy.
    changed_citations: list[str] = Field(default_factory=list)


class Alert(BaseModel):
    """One row of the ``alerts`` table.

    ``alert_id`` is a deterministic UUID5 derived from
    ``(user_id, scan_at, kind, entitlement_id)`` so re-running a sweep
    over the same scan + diff is idempotent — the second insert is a
    no-op rather than a duplicate inbox entry.
    """

    alert_id: str
    user_id: str
    kind: AlertKind
    entitlement_id: str
    created_at: str
    read_at: str | None = None
    payload: AlertPayload
