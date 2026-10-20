"""Log the JobAgent MCP server in without a password — for the machine that runs the backend.

    .venv/bin/python -m backend.scripts.mcp_login <email> [--api http://localhost:3002]

Issues a refresh token straight from this backend's DB + SECRET_KEY and saves it
where mcp_server/jobagent_mcp.py looks (~/.jobagent/credentials.json, 0600).
Anyone who can run this already controls the DB, so it grants nothing new.
For a remote backend use `jobagent_mcp.py login` (password) instead.
"""
import argparse
import os
import sys

from backend.models.user import User
from backend.routers.auth import create_tokens
from backend.workers.agent_tasks import _sync_session
import backend.models  # noqa: F401 — register tables

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mcp_server"))
from jobagent_mcp import CRED_PATH, _save_creds  # noqa: E402

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("email")
p.add_argument("--api", default="http://localhost:3002", help="URL the MCP server should call")
args = p.parse_args()

session = _sync_session()
user = session.query(User).filter_by(email=args.email).first()
if not user:
    sys.exit(f"No account with email {args.email} in this backend's database.")
_save_creds(args.api.rstrip("/"), create_tokens(str(user.id)).refresh_token)
print(f"MCP logged in as {user.email}. Token saved to {CRED_PATH} (readable only by you).")
