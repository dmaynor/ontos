"""The MCP round trip, proven with a real client over stdio - the same
way an external agent harness would consume Ontos."""

import asyncio
import json
import sys

from conftest import CERTIFY_SUBSET_A, certify

BRIEF_QUESTION = "which findings recurred across the last three runs?"


def _payload(result):
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


async def _run_client(store_path):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ontos", "--store", str(store_path), "mcp-serve"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            ask_result = _payload(await session.call_tool("ask", {"question": BRIEF_QUESTION}))
            gated = _payload(
                await session.call_tool("ask", {"question": "show the timeline of run 3"})
            )
            term = _payload(await session.call_tool("get_term", {"name": "finding"}))
            draft = _payload(await session.call_tool("get_term", {"name": "event"}))
            return names, ask_result, gated, term, draft


def test_mcp_round_trip(workspace):
    certify(workspace["store"], CERTIFY_SUBSET_A)
    names, ask_result, gated, term, draft = asyncio.run(_run_client(workspace["store"]))

    assert {"ask", "get_term", "list_terms"} <= set(names)

    assert ask_result["status"] == "answered"
    assert ask_result["rows"][0]["title"] == "Public status page not updated"
    assert ask_result["terms_used"], "MCP answers must carry term provenance"
    assert all(t["certified_by"] == "Test Certifier" for t in ask_result["terms_used"])

    # The gate holds over MCP too: event terms are drafts, so this refuses.
    assert gated["status"] == "refused"
    assert {m["name"] for m in gated["missing_terms"]} == {
        "event", "event.occurred_at", "event.in_run",
    }

    assert term["state"] == "certified"
    assert draft["state"] == "draft"  # lookup shows drafts, clearly labeled
