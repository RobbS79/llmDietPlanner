"""Unit tests for the slack_bot helpers that don't need a live Slack/Claude."""

import asyncio

from slack_bot.bot import SlackClaudeBot, ThreadSession, _describe_tool


def test_bash_shows_command():
    assert _describe_tool("Bash", {"command": "pytest -k pricing"}) == (
        ":wrench: Bash: `pytest -k pricing`"
    )


def test_file_tools_show_basename_only():
    label = _describe_tool("Edit", {"file_path": "/app/diet_planner/tasks.py"})
    assert label == ":memo: Edit: `tasks.py`"


def test_grep_shows_pattern():
    assert _describe_tool("Grep", {"pattern": "TODO"}) == ":mag: Grep: `TODO`"


def test_long_detail_is_truncated():
    label = _describe_tool("Bash", {"command": "x" * 200})
    assert label.endswith("…`")
    assert len(label) < 120


def test_newlines_collapsed():
    assert "\n" not in _describe_tool("Bash", {"command": "a\nb\n  c"})


def test_unknown_tool_falls_back_to_gear():
    assert _describe_tool("WebFetch", {"url": "x"}).startswith(":gear: WebFetch")


def test_missing_input_is_safe():
    assert _describe_tool("Read", None) == ":book: Read"


# --- async flow tests -----------------------------------------------------
# These exercise _handle_mention end-to-end with fakes for Slack and Claude,
# covering the placeholder -> live-status -> final-answer message lifecycle.
# asyncio.run keeps them runnable under plain pytest (no asyncio plugin).


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Msg:
    def __init__(self, content):
        self.content = content


class _FakeClaude:
    """Mimics ClaudeSDKClient: query() then async receive_response()."""

    def __init__(self, script=None, raises=None):
        self.script = script or []
        self.raises = raises

    async def query(self, prompt):
        self._prompt = prompt

    async def receive_response(self):
        if self.raises is not None:
            raise self.raises
        for m in self.script:
            yield m


class _FakeWeb:
    """Records the ordered sequence of Slack web API calls."""

    def __init__(self):
        self.calls = []

    async def chat_postMessage(self, **kw):
        self.calls.append(("post", kw))
        return {"ts": "111.222"}

    async def chat_update(self, **kw):
        self.calls.append(("update", kw))
        return {"ok": True}


def _make_bot(web, client):
    bot = SlackClaudeBot("xapp", "xoxb", {"C1"}, {"U1"})
    bot.bot_user_id = "UBOT"
    bot.web_client = web
    bot.sessions["T1"] = ThreadSession(client=client)
    return bot


def _run_mention(bot):
    event = {"channel": "C1", "user": "U1", "text": "<@UBOT> go", "ts": "T1"}
    asyncio.run(bot._handle_mention(event))


def test_flow_placeholder_status_then_answer():
    web = _FakeWeb()
    client = _FakeClaude(
        script=[
            _Msg([_Block(text="Looking into it.")]),
            _Msg([_Block(name="Bash", input={"command": "pytest -k pricing"})]),
            _Msg([_Block(text="Done. All green.")]),
        ]
    )
    _run_mention(_make_bot(web, client))

    kinds = [k for k, _ in web.calls]
    texts = [kw.get("text") for _, kw in web.calls]
    # First call posts the placeholder fresh; the answer edits that same message.
    assert kinds[0] == "post"
    assert kinds[-1] == "update"
    assert texts[0] == ":thought_balloon: On it…"
    assert any("Bash" in (t or "") for t in texts), "tool status never surfaced"
    assert "Done. All green." in (texts[-1] or "")


def test_flow_reports_error_when_claude_raises():
    web = _FakeWeb()
    client = _FakeClaude(raises=RuntimeError("boom"))
    _run_mention(_make_bot(web, client))

    final = web.calls[-1][1].get("text") or ""
    assert ":warning:" in final, "user should see an error notice, not silence"


def test_flow_denies_user_not_on_allowlist():
    web = _FakeWeb()
    bot = _make_bot(web, _FakeClaude())
    event = {"channel": "C1", "user": "U_INTRUDER", "text": "<@UBOT> go", "ts": "T1"}
    asyncio.run(bot._handle_mention(event))

    assert len(web.calls) == 1
    assert "not on the bot allowlist" in (web.calls[0][1].get("text") or "")
