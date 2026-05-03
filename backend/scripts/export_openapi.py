"""Dump the OpenAPI schema to openapi.json at repo root.

The frontend repo consumes this file via openapi-typescript to generate its
TypeScript types. Run this script whenever the API surface changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swiss_legal_api.api.main import app


def main() -> int:
    schema = app.openapi()
    out = Path(__file__).resolve().parents[1] / "openapi.json"
    out.write_text(json.dumps(schema, indent=2))
    print(f"Wrote {out} with {len(schema.get('paths', {}))} paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
