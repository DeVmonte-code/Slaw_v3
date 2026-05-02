"""Scheduled benefit sweep — diff classifier + Fedlex change detector.

Two pure functions plus one orchestrator:

* :func:`classify_diff` — given previous and current reports, emit
  :class:`Alert` objects tagged ``NEW`` / ``GONE`` / ``UPDATED``. Pure
  over its inputs so tests pin the classifier in isolation.
* :func:`fedlex_changed_articles` — given two Fedlex snapshot files
  (current and previous), return the set of ``(sr_number, article)``
  whose verbatim text changed. Used by the orchestrator to decide
  which users get a forced rescan even when their profile hasn't moved.
* :func:`sweep_all_users` — orchestrator: iterates the ``users``
  table, runs the scan engine, persists results, computes diffs, and
  writes alerts. Designed to be called from APScheduler *and* from
  tests directly (with a stubbed ``scan_fn``) so the scheduler isn't
  in the test critical path.

Determinism contract:
* ``alert_id`` is a UUID5 of ``(user_id, scan_at, kind, entitlement_id)``
  so the same diff produced twice (manual rerun, scheduler restart)
  is a no-op insert rather than a duplicate inbox row.
* The classifier sorts alerts by ``(kind, entitlement_id)`` before
  returning so test fixtures don't have to depend on dict ordering.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import uuid
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from .. import storage
from ..config import settings
from ..schemas import (
    Alert,
    AlertPayload,
    Benefit,
    BenefitReport,
    ContextProfile,
    Entitlement,
    UserRecord,
)

logger = logging.getLogger(__name__)

# Stable namespace so alert_id collisions across users are impossible
# but two runs of the same sweep collide (which is what we want — see
# module docstring).
_ALERT_NAMESPACE = uuid.UUID("8b1f3c5e-2a4d-4e8a-9c7b-1f5d2e3a4b6c")


# ----- Diff classification (pure) ----------------------------------------


def _benefit_key(b: Benefit) -> str:
    return b.entitlement_id


def _value_changed(prev: Benefit, curr: Benefit) -> bool:
    return (
        prev.estimated_value_chf.min != curr.estimated_value_chf.min
        or prev.estimated_value_chf.max != curr.estimated_value_chf.max
    )


def _citations_changed(
    prev: Benefit, curr: Benefit
) -> bool:
    """Two benefits cite different SR/articles for their primary basis.

    We compare the *set* of (sr_number, article) tuples — not the
    quote text and not the score — so a Fedlex re-embedding that
    shuffles paragraph quotes within the same article isn't reported
    as a spurious UPDATE.
    """
    prev_keys = {(c.sr_number, c.article) for c in prev.citations}
    curr_keys = {(c.sr_number, c.article) for c in curr.citations}
    return prev_keys != curr_keys


def _benefit_cites_changed(
    benefit: Benefit, changed: set[tuple[str, str]]
) -> list[str]:
    """Return the human-readable ``SR/Art`` strings of cited articles
    that appear in ``changed``. Empty list when none match.
    """
    out: list[str] = []
    for c in benefit.citations:
        if (c.sr_number, c.article) in changed:
            out.append(f"SR{c.sr_number}/Art{c.article}")
    return sorted(set(out))


def _make_alert(
    *,
    user_id: str,
    scan_at: str,
    kind: str,
    benefit: Benefit,
    previous_value: tuple[float, float] | None = None,
    changed_citations: list[str] | None = None,
) -> Alert:
    aid = uuid.uuid5(
        _ALERT_NAMESPACE, f"{user_id}|{scan_at}|{kind}|{benefit.entitlement_id}"
    )
    payload = AlertPayload(
        entitlement_id=benefit.entitlement_id,
        title=benefit.title,
        category=benefit.category,
        estimated_value_chf_min=benefit.estimated_value_chf.min,
        estimated_value_chf_max=benefit.estimated_value_chf.max,
        previous_estimated_value_chf_min=(
            previous_value[0] if previous_value else None
        ),
        previous_estimated_value_chf_max=(
            previous_value[1] if previous_value else None
        ),
        changed_citations=changed_citations or [],
    )
    return Alert(
        alert_id=str(aid),
        user_id=user_id,
        kind=kind,  # type: ignore[arg-type]
        entitlement_id=benefit.entitlement_id,
        created_at=scan_at,
        read_at=None,
        payload=payload,
    )


def classify_diff(
    *,
    user_id: str,
    previous: BenefitReport | None,
    current: BenefitReport,
    changed_articles: set[tuple[str, str]] | None = None,
) -> list[Alert]:
    """Emit one :class:`Alert` per change between ``previous`` and ``current``.

    Rules:

    * **NEW**: entitlement_id present in ``current`` and not in ``previous``.
      First-ever sweep (``previous is None``) yields one NEW per benefit
      so the user's inbox isn't empty on initial enrolment.
    * **GONE**: entitlement_id present in ``previous`` and not in ``current``.
    * **UPDATED**: same entitlement, different ``estimated_value_chf`` *or*
      different cited (sr_number, article) set *or* the entitlement
      cites an article in ``changed_articles`` (a Fedlex amendment).
      The third clause is what makes "your cited article was amended"
      land in the inbox even when the value/citations are otherwise
      identical — without it, a Fedlex revision that doesn't change
      the entitlement's quantitative output would be invisible.
    """
    changed = changed_articles or set()
    curr_by_id = {_benefit_key(b): b for b in current.benefits}
    prev_by_id = (
        {_benefit_key(b): b for b in previous.benefits} if previous else {}
    )

    alerts: list[Alert] = []

    for eid, benefit in curr_by_id.items():
        if eid not in prev_by_id:
            alerts.append(
                _make_alert(
                    user_id=user_id,
                    scan_at=current.generated_at,
                    kind="NEW",
                    benefit=benefit,
                )
            )
            continue
        prev_b = prev_by_id[eid]
        cited_changes = _benefit_cites_changed(benefit, changed)
        if (
            _value_changed(prev_b, benefit)
            or _citations_changed(prev_b, benefit)
            or cited_changes
        ):
            alerts.append(
                _make_alert(
                    user_id=user_id,
                    scan_at=current.generated_at,
                    kind="UPDATED",
                    benefit=benefit,
                    previous_value=(
                        prev_b.estimated_value_chf.min,
                        prev_b.estimated_value_chf.max,
                    ),
                    changed_citations=cited_changes,
                )
            )

    for eid, benefit in prev_by_id.items():
        if eid not in curr_by_id:
            alerts.append(
                _make_alert(
                    user_id=user_id,
                    scan_at=current.generated_at,
                    kind="GONE",
                    benefit=benefit,
                )
            )

    alerts.sort(key=lambda a: (a.kind, a.entitlement_id))
    return alerts


# ----- Fedlex snapshot diff ----------------------------------------------


def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _index_snapshot(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """Index a Fedlex snapshot by ``(sr_number, article)`` -> text-hash.

    Rolls all paragraphs of one article into one digest so a paragraph
    re-numbering (Fedlex sometimes reshuffles ``para_Y`` while keeping
    text identical) doesn't fire a false "amended" alert.
    """
    by_article: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for r in rows:
        sr = str(r.get("sr_number", "") or "")
        art = str(r.get("article", "") or "")
        if not sr or not art:
            continue
        para = str(r.get("paragraph", "") or "")
        text = str(r.get("text", "") or "")
        by_article.setdefault((sr, art), []).append((para, text))
    out: dict[tuple[str, str], str] = {}
    for k, paras in by_article.items():
        joined = "\n".join(t for _, t in sorted(paras))
        out[k] = _hash_text(joined)
    return out


def fedlex_changed_articles(
    current_path: str | Path, previous_path: str | Path
) -> set[tuple[str, str]]:
    """Return the set of ``(sr_number, article)`` whose text changed.

    Both inputs are JSON files in the ``law_articles.fedlex.json``
    shape produced by :mod:`swiss_legal_api.ingest.fedlex`. Missing
    files yield an empty set — first-ever sweep has no baseline to
    diff against, which is the right behaviour.
    """
    cur_p, prev_p = Path(current_path), Path(previous_path)
    if not cur_p.exists() or not prev_p.exists():
        return set()
    try:
        cur_rows = json.loads(cur_p.read_text())
        prev_rows = json.loads(prev_p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "fedlex_diff_unreadable cur=%s prev=%s err=%s", cur_p, prev_p, exc
        )
        return set()
    cur_idx = _index_snapshot(cur_rows)
    prev_idx = _index_snapshot(prev_rows)
    changed: set[tuple[str, str]] = set()
    for k, h in cur_idx.items():
        if prev_idx.get(k) != h:
            changed.add(k)
    # Removed articles also count as "changed" so any user who cites a
    # now-repealed SR/Art gets an UPDATED alert flagging the disappearance.
    for k in prev_idx.keys() - cur_idx.keys():
        changed.add(k)
    return changed


def promote_fedlex_snapshot(
    current_path: str | Path, previous_path: str | Path
) -> None:
    """Copy the current snapshot over the previous-snapshot slot.

    Called *after* a successful sweep so the next run only sees deltas
    accumulated since this one. No-op if the current file is missing.
    """
    cur_p, prev_p = Path(current_path), Path(previous_path)
    if not cur_p.exists():
        return
    prev_p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cur_p, prev_p)


# ----- Orchestrator ------------------------------------------------------


ScanFn = Callable[[ContextProfile, list[Entitlement]], Awaitable[BenefitReport]]


async def sweep_one_user(
    user: UserRecord,
    catalog: list[Entitlement],
    *,
    scan_fn: ScanFn,
    changed_articles: set[tuple[str, str]],
) -> tuple[BenefitReport, list[Alert]]:
    """Run + persist one user's scan, return (report, inserted_alerts).

    Returns the *inserted* alerts (excluding duplicates) so callers /
    tests can assert idempotency. Storage interaction is wrapped so a
    DB error on alert insert doesn't lose the scan result.
    """
    previous = storage.latest_scan(user.user_id)
    report = await scan_fn(user.profile, catalog)
    storage.insert_scan(user.user_id, report)
    storage.prune_scans(user.user_id, settings.sweep_retention_per_user)

    alerts = classify_diff(
        user_id=user.user_id,
        previous=previous,
        current=report,
        changed_articles=changed_articles,
    )
    inserted: list[Alert] = []
    for a in alerts:
        try:
            if storage.insert_alert(a):
                inserted.append(a)
        except Exception as exc:
            logger.exception(
                "sweep_alert_insert_failed user_id=%s alert_id=%s err=%s",
                user.user_id, a.alert_id, type(exc).__name__,
            )
    logger.info(
        "sweep_user_done user_id=%s benefits=%d new_alerts=%d "
        "previous=%s changed_articles=%d",
        user.user_id,
        len(report.benefits),
        len(inserted),
        "yes" if previous else "no",
        len(changed_articles),
    )
    return report, inserted


async def sweep_all_users(
    catalog: list[Entitlement],
    *,
    scan_fn: ScanFn,
    fedlex_current: str | Path | None = None,
    fedlex_previous: str | Path | None = None,
) -> dict[str, Any]:
    """Run the sweep for every notify-enabled user.

    Steps:
    1. Compute the changed-articles set from the two Fedlex snapshots.
    2. For each user with ``notify_enabled``: run scan, persist,
       classify diff, persist alerts.
    3. After all users complete successfully, promote the current
       snapshot into the previous slot so the next sweep diffs from
       this point.

    Returns a summary dict so the scheduler can log it and tests can
    assert on it without re-querying storage.
    """
    cur_path = Path(fedlex_current) if fedlex_current else _default_fedlex_current()
    prev_path = (
        Path(fedlex_previous)
        if fedlex_previous
        else _default_fedlex_previous()
    )
    changed = fedlex_changed_articles(cur_path, prev_path)

    users = storage.list_users(only_notify_enabled=True)
    total_alerts = 0
    failures = 0
    for u in users:
        try:
            _, inserted = await sweep_one_user(
                u, catalog, scan_fn=scan_fn, changed_articles=changed,
            )
            total_alerts += len(inserted)
        except Exception as exc:
            failures += 1
            logger.exception(
                "sweep_user_failed user_id=%s err=%s",
                u.user_id, type(exc).__name__,
            )

    if failures == 0:
        # Promote the snapshot only if every user succeeded — partial
        # promotion would silently swallow Fedlex changes for the
        # users whose sweep crashed.
        promote_fedlex_snapshot(cur_path, prev_path)

    summary = {
        "users": len(users),
        "failures": failures,
        "alerts_inserted": total_alerts,
        "changed_articles": len(changed),
    }
    logger.info("sweep_complete %s", summary)
    return summary


# Sync wrapper used by APScheduler — schedules call sync callables.
def sweep_all_users_sync(
    catalog: list[Entitlement],
    *,
    scan_fn: ScanFn,
    fedlex_current: str | Path | None = None,
    fedlex_previous: str | Path | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        sweep_all_users(
            catalog,
            scan_fn=scan_fn,
            fedlex_current=fedlex_current,
            fedlex_previous=fedlex_previous,
        )
    )


def _default_fedlex_current() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "seed" / "law_articles.fedlex.json"
    )


def _default_fedlex_previous() -> Path:
    raw = settings.fedlex_previous_snapshot_path
    p = Path(raw)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[3] / p
    return p
