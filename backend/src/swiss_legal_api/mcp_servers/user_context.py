"""``swiss-user-context-mcp`` — read/update the persisted user profile.

Tools:
- ``read_user_docs(user_id)`` — return the persisted ``UserRecord``
  (profile + notify flag + latest scan summary).
- ``update_user_profile(user_id, profile, notify_enabled)`` — upsert
  the profile. Permission policy on the agent is ``always_ask``
  because this writes durable state.

Both tools delegate to ``swiss_legal_api.storage`` directly — the SSOT
test asserts identity so a future schema migration in ``storage.py``
propagates to the MCP path with no second copy to update.
"""

from __future__ import annotations

from typing import Any

from .. import storage
from ..schemas import ContextProfile
from . import McpServerSpec, McpToolSpec, build_fastmcp


def read_user_docs(user_id: str) -> dict[str, Any] | None:
    """Return ``UserRecord`` as a JSON dict, or ``None`` when missing."""
    rec = storage.get_user(user_id)
    return None if rec is None else rec.model_dump(mode="json")


def update_user_profile(
    user_id: str,
    profile: dict[str, Any],
    notify_enabled: bool = True,
) -> dict[str, Any]:
    """Validated upsert of the profile."""
    ctx = ContextProfile.model_validate(profile)
    rec = storage.upsert_user(user_id, ctx, notify_enabled)
    return rec.model_dump(mode="json")


SERVER = McpServerSpec(
    name="swiss-user-context-mcp",
    tools=(
        McpToolSpec(
            name="read_user_docs",
            description="Read the persisted UserRecord for a user_id.",
            impl=read_user_docs,
        ),
        McpToolSpec(
            name="update_user_profile",
            description="Upsert a ContextProfile for a user_id.",
            impl=update_user_profile,
        ),
    ),
)


def serve() -> None:  # pragma: no cover
    build_fastmcp(SERVER, mount_path="/mcp").run(transport="streamable-http")


if __name__ == "__main__":  # pragma: no cover
    serve()
