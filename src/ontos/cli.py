"""The Ontos CLI: sample, generate, certify, terms, ask, demo, mcp-serve.

Exit codes for `ask`: 0 = answered, 3 = refused (uncertified terms),
4 = unsupported question shape. A refusal is the gate working, not an
error - but scripts should be able to tell the difference.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ontos import __version__, sample, service
from ontos.generate import run_generate
from ontos.store import Store

EXIT_ANSWERED = 0
EXIT_REFUSED = 3
EXIT_UNSUPPORTED = 4

BRIEF_QUESTION = "which findings recurred across the last three runs?"

CERTIFY_SUBSET_A = [
    "finding", "finding.title", "finding.severity", "finding.in_run",
    "run", "run.in_exercise",
    "exercise", "exercise.in_organization",
    "organization",
]
CERTIFY_SUBSET_B = ["event", "event.occurred_at", "event.in_run"]


def _default_certifier(args) -> str:
    return getattr(args, "certifier", None) or os.environ.get("ONTOS_CERTIFIER") or getpass.getuser()


# ---------------------------------------------------------------- sample
def cmd_sample(args) -> int:
    try:
        counts = sample.create_sample_db(args.out, force=args.force)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Sample database written to {args.out}:")
    for table, n in counts.items():
        print(f"  {table}: {n} rows")
    return 0


# -------------------------------------------------------------- generate
def cmd_generate(args) -> int:
    with Store(args.store) as store:
        summary = run_generate(store, args.source)
    print(f"Generated draft ontology from {summary['source']}")
    print(f"  tables read: {', '.join(summary['tables'])}")
    print(f"  terms written: {summary['terms_written']} "
          f"({summary['enriched_by_llm']} enriched by an LLM, rest template drafts)")
    print(f"  store now holds {summary['draft_terms']} draft and "
          f"{summary['certified_terms']} certified terms")
    print("Every generated term is a DRAFT. Drafts are never served - "
          "certify with `ontos certify`.")
    return 0


# -------------------------------------------------------------- certify
def cmd_certify(args) -> int:
    by = _default_certifier(args)
    with Store(args.store) as store:
        if args.list:
            terms = store.list_terms(state=args.state or "draft")
            if not terms:
                print(f"No terms in state '{args.state or 'draft'}'.")
                return 0
            for t in terms:
                print(f"{t.name} [{t.kind}] ({t.origin}) - {t.definition}")
            return 0
        if args.accept_all:
            names = [t.name for t in store.list_terms(state="draft")]
            return _certify_names(store, names, by)
        if args.accept:
            return _certify_names(store, args.accept, by)
        if args.reject:
            for name in args.reject:
                try:
                    store.reject(name, by)
                    print(f"rejected: {name} (by {by})")
                except KeyError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 1
            return 0
        if args.edit:
            name, definition = args.edit
            try:
                term = store.edit_definition(name, definition, by)
            except KeyError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            note = " (was certified - returned to draft; re-certify to serve it)" \
                if term.state == "draft" else ""
            print(f"edited: {name} - definition updated by {by}{note}")
            return 0
        # No scripted action: interactive review, terminals only.
        if not sys.stdin.isatty():
            print(
                "error: interactive certification needs a terminal. "
                "Scripted use: `ontos certify --accept NAME...`, `--accept-all`, "
                "`--reject NAME...`, `--edit NAME DEFINITION`, or `--list`.",
                file=sys.stderr,
            )
            return 1
        return _certify_interactive(store, by)


def _certify_names(store: Store, names: list[str], by: str) -> int:
    for name in names:
        try:
            term = store.certify(name, by)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"certified: {term.name} (by {term.certified_by} at {term.certified_at})")
    return 0


def _certify_interactive(store: Store, by: str) -> int:
    drafts = store.list_terms(state="draft")
    if not drafts:
        print("No draft terms to review.")
        return 0
    print(f"Reviewing {len(drafts)} draft term(s) as {by}. "
          "[a]ccept, [e]dit, [r]eject, [s]kip, [q]uit")
    for term in drafts:
        print(f"\n{term.name} [{term.kind}] (origin: {term.origin})")
        print(f"  {term.definition}")
        try:
            choice = input("  > ").strip().lower()
        except EOFError:
            print()
            break
        if choice == "q":
            break
        if choice == "a":
            store.certify(term.name, by)
            print("  certified.")
        elif choice == "r":
            store.reject(term.name, by)
            print("  rejected.")
        elif choice == "e":
            try:
                new_def = input("  new definition: ").strip()
            except EOFError:
                new_def = ""
            if new_def:
                store.edit_definition(term.name, new_def, by)
                again = input("  certify the edited definition? [y/N] ").strip().lower()
                if again == "y":
                    store.certify(term.name, by)
                    print("  edited and certified.")
                else:
                    print("  edited; still a draft.")
        else:
            print("  skipped.")
    return 0


# ---------------------------------------------------------------- terms
def cmd_terms(args) -> int:
    terms = service.list_terms(args.store, args.state)
    if args.json:
        print(json.dumps(terms, indent=2))
        return 0
    if not terms:
        print("No terms found.")
        return 0
    for t in terms:
        print(f"{t['name']} [{t['kind']}] state={t['state']} origin={t['origin']}")
    return 0


# ------------------------------------------------------------------ ask
def _render_ask_text(result: dict) -> str:
    lines = [result["answer"]]
    if result["status"] == "answered":
        lines.append("")
        lines.append(f"SQL: {result['sql']}")
        if result["params"]:
            lines.append(f"Params: {result['params']}")
        lines.append("Terms used (certified):")
        for t in result["terms_used"]:
            lines.append(f"  - {t['name']} [{t['kind']}] certified by "
                         f"{t['certified_by']} at {t['certified_at']}")
    return "\n".join(lines)


def cmd_ask(args) -> int:
    result = service.ask(args.store, args.question)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_render_ask_text(result))
    if result["status"] == "answered":
        return EXIT_ANSWERED
    if result["status"] == "refused":
        return EXIT_REFUSED
    return EXIT_UNSUPPORTED


# ------------------------------------------------------------ mcp-serve
def cmd_mcp_serve(args) -> int:
    from ontos.mcp_server import run

    run(args.store)
    return 0


# ----------------------------------------------------------------- demo
def _demo_env() -> dict:
    """Demo subprocesses run credential-free on purpose: generate must
    prove its deterministic fallback, not an LLM."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("ONTOS_LLM_") or key.startswith("OPENAI_"):
            del env[key]
    env.pop("ONTOS_CERTIFIER", None)
    return env


def _run_step(cmd: list[str], cwd: Path, env: dict) -> tuple[int, str]:
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out.rstrip())
    return proc.returncode, out


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(f"demo check failed: {msg}")


async def _mcp_step(store_path: Path, env: dict) -> dict:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ontos", "--store", str(store_path), "mcp-serve"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"MCP tools exposed: {', '.join(names)}")
            _check("ask" in names and "get_term" in names, "MCP tool list")
            result = await session.call_tool("ask", {"question": BRIEF_QUESTION})
            payload = None
            if getattr(result, "structuredContent", None):
                payload = result.structuredContent
            elif result.content:
                payload = json.loads(result.content[0].text)
            return payload or {}


def cmd_demo(args) -> int:
    workspace = Path(args.dir)
    certifier = args.certifier
    print("=" * 70)
    print("Ontos slice-1 demo: generate -> certify -> ask -> ask via MCP")
    print("Note: model credentials are scrubbed for the demo - `generate`")
    print("proves its deterministic template-draft fallback, no LLM involved.")
    print("=" * 70)
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    env = _demo_env()
    py = [sys.executable, "-m", "ontos", "--store", "ontology.db"]
    try:
        rc, _ = _run_step(py + ["sample", "--out", "sample.db"], workspace, env)
        _check(rc == 0, "sample creation")

        rc, _ = _run_step(py + ["generate", "--source", "sample.db"], workspace, env)
        _check(rc == 0, "generate")

        print("\n-- The gate: asking before anything is certified --")
        rc, out = _run_step(py + ["ask", BRIEF_QUESTION], workspace, env)
        _check(rc == EXIT_REFUSED and "Refused" in out,
               "uncertified question must be refused")

        rc, _ = _run_step(
            py + ["certify", "--as", certifier, "--accept"] + CERTIFY_SUBSET_A,
            workspace, env,
        )
        _check(rc == 0, "certify subset A")

        rc, out = _run_step(py + ["ask", "how many findings are there?"], workspace, env)
        _check(rc == 0 and "17 findings" in out, "count of findings")

        rc, out = _run_step(py + ["ask", BRIEF_QUESTION], workspace, env)
        _check(rc == 0 and "Public status page not updated" in out,
               "recurrence within the last three runs")

        rc, out = _run_step(py + ["ask", "how many findings per organization?"], workspace, env)
        _check(rc == 0 and "HarborPoint Health" in out, "per-organization rollup")

        rc, out = _run_step(py + ["ask", "findings by severity"], workspace, env)
        _check(rc == 0 and "critical" in out, "severity breakdown")

        print("\n-- The gate again: the timeline needs event terms, still drafts --")
        rc, out = _run_step(py + ["ask", "show the timeline of run 3"], workspace, env)
        _check(rc == EXIT_REFUSED and "event" in out,
               "timeline must refuse until event terms are certified")

        rc, _ = _run_step(
            py + ["certify", "--as", certifier, "--accept"] + CERTIFY_SUBSET_B,
            workspace, env,
        )
        _check(rc == 0, "certify subset B")

        rc, out = _run_step(py + ["ask", "show the timeline of run 3"], workspace, env)
        _check(rc == 0 and "Timeline of run 3" in out, "timeline after certification")

        print("\n-- The same question through the MCP server (real client call) --")
        print(f'ask("{BRIEF_QUESTION}") via MCP stdio')
        payload = asyncio.run(_mcp_step(workspace / "ontology.db", env))
        print(json.dumps(payload, indent=2)[:1600])
        _check(payload.get("status") == "answered", "MCP ask answered")
        _check(bool(payload.get("terms_used")), "MCP ask carries term provenance")
        _check(
            all(t.get("certified_by") == certifier for t in payload["terms_used"]),
            "MCP provenance names the certifier",
        )
    except RuntimeError as exc:
        print(f"\nDEMO FAILED: {exc}", file=sys.stderr)
        return 1
    print("\n" + "=" * 70)
    print("DEMO COMPLETE: draft -> certified -> served, with provenance,")
    print("and the gate refused twice along the way. Artifacts kept in:")
    print(f"  {workspace.resolve()}")
    print("=" * 70)
    return 0


# ----------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ontos",
        description="Ontos - a certification-first auto-ontology layer for agents.",
    )
    parser.add_argument("--version", action="version", version=f"ontos {__version__}")
    parser.add_argument(
        "--store",
        default=os.environ.get("ONTOS_STORE", "ontology.db"),
        help="ontology store path (default: $ONTOS_STORE or ./ontology.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample", help="create the bundled sample database")
    p.add_argument("--out", default="sample.db", help="output path (default: sample.db)")
    p.add_argument("--force", action="store_true", help="overwrite if it exists")
    p.set_defaults(fn=cmd_sample)

    p = sub.add_parser("generate", help="draft an ontology from a source database")
    p.add_argument("--source", required=True,
                   help="SQLite file / sqlite:/// URL, or a postgresql:// connection string")
    p.set_defaults(fn=cmd_generate)

    p = sub.add_parser("certify", help="review and certify draft terms")
    p.add_argument("--as", dest="certifier", default=None,
                   help="certifier name (default: $ONTOS_CERTIFIER or your username)")
    p.add_argument("--list", action="store_true", help="list terms (drafts by default)")
    p.add_argument("--state", default=None, help="state filter for --list")
    p.add_argument("--accept", nargs="+", metavar="NAME", help="certify the named terms")
    p.add_argument("--accept-all", action="store_true", help="certify every draft")
    p.add_argument("--reject", nargs="+", metavar="NAME", help="reject the named terms")
    p.add_argument("--edit", nargs=2, metavar=("NAME", "DEFINITION"),
                   help="replace a term's definition (a certified term returns to draft)")
    p.set_defaults(fn=cmd_certify)

    p = sub.add_parser("terms", help="list terms in the store")
    p.add_argument("--state", default=None, help="filter by state")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_terms)

    p = sub.add_parser("ask", help="ask a question - certified terms only")
    p.add_argument("question")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser("demo", help="run the slice-1 end-to-end demo")
    p.add_argument("--dir", default="demo-workspace",
                   help="workspace directory (reset on each run; default: demo-workspace)")
    p.add_argument("--certifier", default="Demo Certifier")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("mcp-serve", help="run the MCP server (stdio)")
    p.set_defaults(fn=cmd_mcp_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
