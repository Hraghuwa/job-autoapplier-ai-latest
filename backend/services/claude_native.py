"""Claude-native mode: hand the thinking to the caller's LLM instead of ours.

With `?brief=true`, an AI endpoint builds exactly the prompt it would have sent
to llm_router (CV, job description, rubric, output format) and returns it
instead of calling a model. The MCP client (Claude) reasons over it in its own
context and stores the result through a save-only endpoint. No server AI key or
local model is needed, and no AI token is spent.

    router = APIRouter(dependencies=[Depends(brief_mode)])   # per router
    maybe_brief(prompt)                                       # first line of the AI call
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import Query

_BRIEF: ContextVar[bool] = ContextVar("claude_brief", default=False)


class BriefOnly(Exception):
    """Raised instead of calling a model; main.py turns it into a 200 response."""

    def __init__(self, prompt: str):
        super().__init__("brief")
        self.prompt = prompt


async def brief_mode(brief: bool = Query(False, description="Return the AI prompt for the caller's own LLM "
                                                             "instead of running it here (Claude-native mode).")):
    # async dependency → runs in the request's own context, so the endpoint sees it.
    # Always set (True or False) so a value can never leak between requests.
    _BRIEF.set(brief)


def is_brief() -> bool:
    return _BRIEF.get()


def maybe_brief(prompt: str) -> None:
    if _BRIEF.get():
        raise BriefOnly(prompt)


def brief_response(prompt: str) -> dict:
    return {"mode": "claude_native", "instructions": prompt}
