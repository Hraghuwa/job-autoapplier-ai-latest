import asyncio
import json
from typing import Dict, Set, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt

from backend.config import settings
from backend.database import engine
import backend.models  # noqa: F401 — imports all models, registers with database.Base
from backend.routers import auth, onboarding, agents, jobs, users, payments, admin, resumes, ai, graph, bugs, career_ops

# ── In-memory WebSocket connection manager (Redis fallback) ───────────────────
class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def register(self, user_id: str, ws: WebSocket):
        self.connections.setdefault(user_id, set()).add(ws)

    def unregister(self, user_id: str, ws: WebSocket):
        self.connections.get(user_id, set()).discard(ws)

    async def broadcast(self, user_id: str, message: str):
        for ws in list(self.connections.get(user_id, [])):
            try:
                await ws.send_text(message)
            except Exception:
                self.connections.get(user_id, set()).discard(ws)

    def send_from_thread(self, user_id: str, message: str):
        """Called from background threads — schedules broadcast on the stored event loop.
        Never calls asyncio.get_event_loop() from a thread: in Python 3.10+ that returns
        a new (non-running) loop, causing run_coroutine_threadsafe to silently fail.
        """
        loop = self.loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(user_id, message), loop)
        # else: app not yet started or shutting down — drop silently


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup must be resilient — the platform healthcheck (30s) hits
    `/health` immediately after the process binds the port. If schema creation
    blocks on an unreachable DB, the healthcheck times out and Railway tears
    the deployment down. So we attempt schema creation with a short timeout
    and log+continue on failure rather than crashing startup.
    """
    import logging
    log = logging.getLogger(__name__)

    from backend.database import Base
    import backend.models  # noqa — ensure all models are registered before create_all

    try:
        async def _init_schema():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        await asyncio.wait_for(_init_schema(), timeout=10.0)
        log.info("Database schema ensured.")
    except asyncio.TimeoutError:
        log.error("DB schema init timed out after 10s — starting anyway. "
                  "Check DATABASE_URL connectivity.")
    except Exception as e:
        log.error("DB schema init failed: %s — starting anyway. /health stays up.", e)

    manager.loop = asyncio.get_running_loop()
    yield


app = FastAPI(title="JobAgent API", version="1.0.0", lifespan=lifespan)

# Build CORS origin list from FRONTEND_URL env var (supports comma-separated list)
# plus hardcoded Vercel deployment URL and local dev origins.
_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Vercel production deployment
    "https://frontend-2oec020pb-harshs-projects-68f6e57b.vercel.app",
    # Vercel aliased domain (shorter URL)
    "https://frontend-lac-mu-2eggctjwqm.vercel.app",
    # Latest Vercel production deployment
    "https://frontend-f0n34xezv-harshs-projects-68f6e57b.vercel.app",
]
# FRONTEND_URL may be a single URL or comma-separated list
for _u in (settings.frontend_url or "").split(","):
    _u = _u.strip()
    if _u and _u not in _cors_origins:
        _cors_origins.append(_u)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Allow any Vercel preview/production URL for this project. Each preview
    # gets a unique subdomain (e.g. frontend-xyz123-…vercel.app), so a regex
    # avoids needing to redeploy the backend every time Vercel rotates URLs.
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,       prefix="/auth",       tags=["auth"])
app.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
app.include_router(agents.router,     prefix="/agents",     tags=["agents"])
app.include_router(jobs.router,       prefix="/jobs",       tags=["jobs"])
app.include_router(users.router,      prefix="/users",      tags=["users"])
app.include_router(payments.router,   prefix="/payments",   tags=["payments"])
app.include_router(admin.router,      prefix="/admin",      tags=["admin"])
app.include_router(resumes.router,    prefix="/resumes",    tags=["resumes"])
app.include_router(ai.router,         prefix="/ai",         tags=["ai"])
app.include_router(graph.router,      prefix="/graph",      tags=["graph"])
app.include_router(bugs.router,       prefix="/bugs",       tags=["bugs"])
app.include_router(career_ops.router, prefix="/career-ops", tags=["career-ops"])


# ── WebSocket — live agent feed ───────────────────────────────────────────────
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, token: str = Query("")):
    # Validate JWT token before accepting connection
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("sub") != user_id:
            await websocket.close(code=4003)
            return
    except JWTError:
        await websocket.close(code=4001)
        return
    await websocket.accept()
    manager.register(user_id, websocket)

    # Try Redis pub/sub for Celery workers; in-memory handles background threads
    redis_task = None
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"user:{user_id}:progress")

        async def redis_reader():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])

        redis_task = asyncio.create_task(redis_reader())
    except Exception:
        redis_client = None
        pubsub = None

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(user_id, websocket)
        if redis_task:
            redis_task.cancel()
        if pubsub:
            try:
                await pubsub.unsubscribe(f"user:{user_id}:progress")
                await redis_client.aclose()
            except Exception:
                pass


@app.get("/health")
async def health():
    return {"status": "ok", "ws_connections": {k: len(v) for k, v in manager.connections.items()}}


