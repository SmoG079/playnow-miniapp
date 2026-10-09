"""Stable pseudonymous API identities; internal WeChat identifiers stay server-side."""

import uuid


def public_user_id(value):
    if value is None:
        return None
    value = str(value)
    try:
        if str(uuid.UUID(value)) == value:
            return value
    except ValueError:
        pass
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "playnow:user:" + value))


USER_KEYS = {
    "user_id",
    "partner_user_id",
    "actor_id",
    "created_by",
    "reviewed_by",
    "locked_by",
}


def public_references(value, key=None):
    if isinstance(value, dict):
        return {k: public_references(v, k) for k, v in value.items()}
    if isinstance(value, list):
        if key in ("users", "user_ids"):
            return [public_user_id(v) for v in value]
        return [public_references(v) for v in value]
    if key in USER_KEYS and value is not None:
        return public_user_id(value)
    return value
