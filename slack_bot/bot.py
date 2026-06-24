"""Slack <-> Claude Code bridge.

One Slack thread == one persistent Claude Code session. The bot listens via
Socket Mode (no public URL needed), enforces a channel + user allowlist, and
spawns a ClaudeSDKClient per thread that survives across messages until the
thread is idle for IDLE_TIMEOUT_SECONDS.

Security model
--------------
The bot grants full Claude Code (read, write, shell, git) to anyone on the
allowlist. The allowlist is the only meaningful gate. Everything else is a
soft guardrail in the system prompt and a sufficiently clever user can talk
Claude past it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = int(os.environ.get("SLACKBOT_IDLE_TIMEOUT", "1800"))  # 30 min
WORKING_DIR = os.environ.get("SLACKBOT_WORKING_DIR", "/app")

SYSTEM_PROMPT = """You are a coding assistant connected to a Slack thread.
You have full Claude Code tools (Bash, Read, Edit, Write, Glob, Grep) over
the repo at /app. Guidelines:
- Be concise — Slack messages should be short. Prefer a one-paragraph
  summary over verbose explanation.
- Do not run destructive git operations (push --force, reset --hard,
  branch -D) without an explicit confirmation message from the user.
- Do not modify .env files, secrets, or anything in node_modules.
- When you write code, show the diff in your response so the user can
  review it in Slack.
- Format code blocks using triple backticks; Slack renders them.
"""


@dataclass
class ThreadSession:
    """One Claude Code session bound to a Slack thread."""

    client: ClaudeSDKClient
    last_activity: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SlackClaudeBot:
    def __init__(
        self,
        app_token: str,
        bot_token: str,
        allowed_channels: set[str],
        allowed_users: set[str],
    ) -> None:
        self.app_token = app_token
        self.allowed_channels = allowed_channels
        self.allowed_users = allowed_users
        self.sessions: dict[str, ThreadSession] = {}
        self.bot_user_id: Optional[str] = None

        self.web_client = AsyncWebClient(token=bot_token)
        self.socket_client: Optional[SocketModeClient] = None

    async def start(self) -> None:
        self.socket_client = SocketModeClient(
            app_token=self.app_token,
            web_client=self.web_client,
        )
        self.socket_client.socket_mode_request_listeners.append(self._on_request)

        auth = await self.web_client.auth_test()
        self.bot_user_id = auth["user_id"]
        logger.info(
            "bot identity: user_id=%s team=%s allowed_channels=%s allowed_users=%s",
            self.bot_user_id,
            auth.get("team"),
            sorted(self.allowed_channels) or "<none>",
            sorted(self.allowed_users) or "<none>",
        )
        await self.socket_client.connect()
        asyncio.create_task(self._reap_idle_sessions())
        await asyncio.Event().wait()  # block forever

    async def _on_request(self, client: SocketModeClient, req: SocketModeRequest) -> None:
        # Ack first so Slack does not retry.
        await client.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )
        if req.type != "events_api":
            return
        event = req.payload.get("event") or {}
        if event.get("type") != "app_mention":
            return
        try:
            await self._handle_mention(event)
        except Exception:
            logger.exception("error handling mention")

    async def _handle_mention(self, event: dict) -> None:
        channel = event["channel"]
        user = event.get("user")
        text = event.get("text", "")
        # If the mention is in an existing thread reply, thread_ts is set; if
        # it's a fresh top-level message, the thread is the message itself.
        thread_ts = event.get("thread_ts") or event["ts"]

        if self.allowed_channels and channel not in self.allowed_channels:
            logger.warning("denied: channel %s not on allowlist (user=%s)", channel, user)
            return
        if self.allowed_users and user not in self.allowed_users:
            await self.web_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f":no_entry: <@{user}> is not on the bot allowlist.",
            )
            return

        # Strip the bot's own @mention from the text.
        prompt = text
        if self.bot_user_id:
            prompt = prompt.replace(f"<@{self.bot_user_id}>", "").strip()
        if not prompt:
            return

        session = await self._get_session(thread_ts)
        # Post the placeholder before taking the lock so the user gets an
        # instant "On it…" even when another message in this thread is still
        # being processed and holds the lock.
        status_ts = await self._post_status(channel, thread_ts, ":thought_balloon: On it…")
        async with session.lock:
            session.last_activity = time.time()
            updater = self._make_status_updater(channel, status_ts)
            try:
                response = await self._query_claude(session.client, prompt, updater)
            except Exception:
                logger.exception("claude query failed for thread_ts=%s", thread_ts)
                response = (
                    ":warning: Something went wrong while processing that — "
                    "check `docker-compose logs slackbot`."
                )
            session.last_activity = time.time()

        await self._finalize(channel, thread_ts, status_ts, response)

    async def _get_session(self, thread_ts: str) -> ThreadSession:
        existing = self.sessions.get(thread_ts)
        if existing is not None:
            return existing

        options = ClaudeAgentOptions(
            cwd=WORKING_DIR,
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
            permission_mode="acceptEdits",
        )
        client = ClaudeSDKClient(options=options)
        await client.connect()
        session = ThreadSession(client=client)
        self.sessions[thread_ts] = session
        logger.info("opened new session for thread_ts=%s", thread_ts)
        return session

    async def _query_claude(self, client: ClaudeSDKClient, prompt: str, on_tool) -> str:
        await client.query(prompt)
        chunks: list[str] = []
        async for message in client.receive_response():
            # The SDK yields a variety of message types. We forward assistant
            # text to Slack and surface tool-use as live status, dropping the
            # rest of the chatter.
            content = getattr(message, "content", None)
            if not content:
                continue
            for block in content:
                name = getattr(block, "name", None)
                if name and hasattr(block, "input"):
                    try:
                        await on_tool(_describe_tool(name, getattr(block, "input", None)))
                    except Exception:
                        pass  # status is best-effort, never fail the run for it
                    continue
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks).strip() or "_(no response)_"

    async def _post_status(self, channel: str, thread_ts: str, text: str) -> Optional[str]:
        """Post the live-status placeholder and return its ts (None on failure)."""
        try:
            resp = await self.web_client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=text
            )
            return resp["ts"]
        except Exception:
            logger.exception("failed to post status placeholder")
            return None

    def _make_status_updater(self, channel: str, status_ts: Optional[str]):
        """Return an async fn that edits the placeholder, throttled to ~1/s."""
        state = {"last": 0.0}

        async def update(label: str) -> None:
            if status_ts is None:
                return
            now = time.time()
            if now - state["last"] < 1.0:
                return  # throttle: next tool-use will refresh it
            state["last"] = now
            try:
                await self.web_client.chat_update(
                    channel=channel, ts=status_ts, text=f":thought_balloon: {label}"
                )
            except Exception:
                pass  # transient / rate-limit — non-fatal

        return update

    async def _finalize(
        self, channel: str, thread_ts: str, status_ts: Optional[str], text: str
    ) -> None:
        # Slack hard-limits messages to 40k chars; chunk just in case.
        chunks = list(_chunk(text, 35_000)) or ["_(no response)_"]
        if status_ts is not None:
            try:
                await self.web_client.chat_update(
                    channel=channel, ts=status_ts, text=chunks[0]
                )
            except Exception:
                logger.exception("failed to edit placeholder; posting answer fresh")
                await self.web_client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts, text=chunks[0]
                )
        else:
            await self.web_client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=chunks[0]
            )
        for chunk in chunks[1:]:
            await self.web_client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=chunk
            )

    async def _reap_idle_sessions(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.time()
            stale = [
                ts
                for ts, sess in self.sessions.items()
                if now - sess.last_activity > IDLE_TIMEOUT_SECONDS
            ]
            for ts in stale:
                sess = self.sessions.pop(ts, None)
                if sess is None:
                    continue
                try:
                    await sess.client.disconnect()
                except Exception:
                    logger.exception("error disconnecting stale session %s", ts)
                logger.info("reaped idle session thread_ts=%s", ts)


def _chunk(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


_TOOL_EMOJI = {
    "Bash": ":wrench:",
    "Read": ":book:",
    "Grep": ":mag:",
    "Glob": ":mag:",
    "Edit": ":memo:",
    "Write": ":memo:",
}


def _describe_tool(name: str, tool_input: Optional[dict]) -> str:
    """Render a one-line Slack status string for a tool-use block.

    Picks the most informative field per tool (command / file / pattern) and
    truncates it so the live status stays a single tidy line.
    """
    emoji = _TOOL_EMOJI.get(name, ":gear:")
    inp = tool_input or {}
    detail = ""
    if name == "Bash":
        detail = inp.get("command", "")
    elif name in ("Read", "Edit", "Write"):
        path = inp.get("file_path", "")
        detail = path.rsplit("/", 1)[-1] if path else ""
    elif name in ("Grep", "Glob"):
        detail = inp.get("pattern", "")
    detail = " ".join(str(detail).split())
    if len(detail) > 80:
        detail = detail[:79] + "…"
    label = f"{emoji} {name}"
    if detail:
        label += f": `{detail}`"
    return label
