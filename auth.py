import logging
from functools import wraps

from flask import jsonify, g, session

from db import get_user_by_id, check_user_quota

logger = logging.getLogger(__name__)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated", "code": "AUTH_REQUIRED"}), 401

        user = get_user_by_id(user_id)
        if not user or not user.get("active"):
            session.clear()
            return jsonify({"error": "Account disabled", "code": "ACCOUNT_DISABLED"}), 403

        g.user = user
        return f(*args, **kwargs)

    return decorated


def require_quota(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not authenticated", "code": "AUTH_REQUIRED"}), 401

        if not check_user_quota(user_id):
            user = get_user_by_id(user_id)
            return jsonify({
                "error": "Trial quota exhausted",
                "code": "QUOTA_EXHAUSTED",
                "max_iterations": user["max_iterations"] if user else 0,
                "used_iterations": user["used_iterations"] if user else 0,
            }), 429

        return f(*args, **kwargs)

    return decorated
