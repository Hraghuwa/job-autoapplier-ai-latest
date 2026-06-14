"""Regression guard: every data/mutation route must carry an auth dependency.

This is how the H5 IDOR slipped in — a route shipped without scoping to the user.
The test walks the live FastAPI route table and asserts each route (except a
small allowlist of intentionally-public ones) depends on get_current_user /
require_admin / require_plan. A new endpoint that forgets auth fails CI.
"""
import backend.main as m

# Intentionally public: health probes, signature-verified webhooks, pre-auth
# auth flows, and static plan/config catalogs.
PUBLIC = {
    "/health", "/", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
    "/auth/login", "/auth/register", "/auth/refresh",
    "/payments/razorpay/webhook", "/payments/stripe/webhook",
    "/payments/plans", "/payments/config",
    "/agents/healthcheck", "/career-ops/health",
}
AUTH_CALLABLES = {"get_current_user", "require_admin", "require_plan", "_check", "promote_self"}


def _route_has_auth(route) -> bool:
    seen = set()
    stack = list(getattr(route.dependant, "dependencies", []))
    while stack:
        dep = stack.pop()
        call = getattr(dep, "call", None)
        nm = getattr(call, "__name__", "")
        if nm in AUTH_CALLABLES:
            return True
        if id(dep) not in seen:
            seen.add(id(dep))
            stack.extend(getattr(dep, "dependencies", []))
    return False


def test_all_non_public_routes_require_auth():
    missing = []
    for route in m.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if not hasattr(route, "dependant"):
            continue
        if path in PUBLIC or path.startswith("/ws"):
            continue
        if methods <= {"HEAD", "OPTIONS"}:
            continue
        if not _route_has_auth(route):
            missing.append(f"{sorted(methods)} {path}")
    assert not missing, "routes missing auth dependency:\n" + "\n".join(missing)
