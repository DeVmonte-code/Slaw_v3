"""Test-suite-wide fixtures and environment defaults.

Anthropic's client validates that an API key is present at request-build
time (before httpx's transport runs), so respx-mocked tests still need
*some* string set. We default ANTHROPIC_API_KEY to a placeholder when the
env var is unset so the offline mocked tests don't accidentally require a
real key.

We deliberately do NOT default QDRANT_URL — tests that need live retrieval
patch `retrieve_for_citation`, and the live-secrets-gated tests in
test_api.py / test_scan.py / test_retrieval.py read QDRANT_URL directly to
decide whether to skip themselves.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-offline-mocked")
