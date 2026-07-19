"""HTTP-layer auth helpers for the knowledge serve module.

Follows the existing derisk-serve conventions instead of inventing a new
system:

- **User identity**: `derisk_serve.utils.auth.get_user_from_headers`
  (X-User-ID header / derisk_session cookie / JWT). When the permissions
  feature plugin is off (single-machine mode) it returns a mock admin and
  all filtering below is skipped — behavior is unchanged from before.
- **API keys**: the `check_api_key` pattern from
  `derisk_serve.datasource.api.endpoints` — when `ServeConfig.api_keys`
  is non-empty, every route requires a matching
  `Authorization: Bearer <key>`; when empty, all requests are allowed.

The FastAPI dependency functions (`check_api_key`, `space_access_guard`)
live in `endpoints.py` so `app.dependency_overrides[get_service]` keeps
working in tests; this module holds the pure logic.

Visibility semantics (spaces.visibility):
- private: only the owner (and role=admin) can read or write; other users
  get 404 (existence is hidden).
- shared:  any authenticated user can read; only the owner can write.
- public:  same as shared for now (read for all, write for owner) — the
  distinction is reserved for unauthenticated read once the platform
  supports anonymous sessions.

Legacy rows (owner_id == "") were created before auth existed; they stay
world-accessible so existing single-machine deployments never lock
themselves out.
"""

from __future__ import annotations

import logging
from functools import cache
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from derisk_serve.utils.auth import UserRequest, _is_permissions_enabled

logger = logging.getLogger(__name__)


@cache
def parse_api_keys(api_keys: str) -> List[str]:
    """Parse the comma-separated api keys config into a list."""
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


def check_space_access(space: Any, user: UserRequest, write: bool) -> None:
    """Raise 404/403 when `user` may not access `space`.

    `space` is anything with `owner_id` / `visibility` attributes or keys
    (a `derisk.knowledge.types.Space` or a list_spaces() dict).
    """
    if isinstance(space, dict):
        owner = (space.get("owner_id") or "").strip()
        visibility = space.get("visibility") or "private"
    else:
        owner = (getattr(space, "owner_id", None) or "").strip()
        visibility = getattr(space, "visibility", "private")
        visibility = getattr(visibility, "value", visibility) or "private"

    # Legacy spaces (no owner recorded) stay world-accessible.
    if not owner:
        return
    if user.user_id == owner or user.role == "admin":
        return
    if visibility == "private":
        # Hide existence from non-owners.
        raise HTTPException(status_code=404, detail="space not found")
    if write:
        raise HTTPException(
            status_code=403, detail="space is read-only for non-owners"
        )
    # shared/public read: allowed


def filter_spaces_for_user(
    spaces: List[Dict[str, Any]], user: UserRequest
) -> List[Dict[str, Any]]:
    """Apply visibility filtering to a list_spaces() result.

    Single-machine mode (permissions plugin off): unfiltered.
    """
    if not _is_permissions_enabled():
        return spaces
    out: List[Dict[str, Any]] = []
    for s in spaces:
        try:
            check_space_access(s, user, write=False)
        except HTTPException:
            continue
        out.append(s)
    return out


def owner_for_create(user: UserRequest) -> Optional[str]:
    """Resolve the owner_id to record for a newly created space.

    Only real authenticated users (permissions plugin on) are recorded;
    single-machine mode keeps the legacy empty owner so behavior is
    unchanged.
    """
    if not _is_permissions_enabled():
        return None
    return user.user_id


__all__ = [
    "parse_api_keys",
    "check_space_access",
    "filter_spaces_for_user",
    "owner_for_create",
]
