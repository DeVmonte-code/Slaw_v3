with open("src/swiss_legal_api/scheduler.py", "r") as f:
    text = f.read()

replacement = """def _job() -> None:
    \"\"\"Top-level scheduler callable. Catches every exception so a
    transient Anthropic / Qdrant outage doesn't crash the scheduler
    and skip every subsequent night.\"\"\"
    try:
        catalog = load_catalog()
        
        if settings.fedlex_refresh_enabled:
            from datetime import datetime, UTC
            from pathlib import Path
            from .ingest.fedlex import ingest, write_snapshot
            from .engine.sweep import promote_fedlex_snapshot, _default_fedlex_current

            logger.info("Starting nightly fedlex refresh")
            
            srs = {c.sr_number for e in catalog for c in e.source_citations if not getattr(c, "canton", None)}
            
            records = ingest(sorted(srs))
            
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            snap_path = Path(__file__).resolve().parents[2] / "seed" / "snapshots" / f"fedlex_{ts}.json"
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            
            write_snapshot(records, snap_path)
            promote_fedlex_snapshot(snap_path, _default_fedlex_current())
            
            logger.info("Fedlex refresh successful. Wrote snapshot to %s", snap_path)

        summary = sweep_all_users_sync(catalog, scan_fn=run_benefit_scan)
        logger.info("nightly_sweep_summary %s", summary)
    except Exception as exc:
        logger.exception("nightly_sweep_failed err=%s", type(exc).__name__)
"""
text = text.split("def _job() -> None:")[0] + replacement + text.split("def start() -> BackgroundScheduler | None:")[1]
import re
text = re.sub(r'def start.*?def stop', 'def start() -> BackgroundScheduler | None:\n' + text.split("def start() -> BackgroundScheduler | None:")[1].split("def stop")[0] + "\ndef stop", text, flags=re.DOTALL)
with open("src/swiss_legal_api/scheduler.py", "w") as f:
    f.write(text)

