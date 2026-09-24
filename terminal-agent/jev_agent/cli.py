"""Launch a real empty terminal chat. No task starts until the user submits it."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from .core import Session
from .catalog import export_session, list_sessions
from .replay import replay_session
from .runtime import claude_binary, clean, codex_binary


ROOT = Path(__file__).resolve().parents[1]


def session_directory(base, name):
    """Resolve last / ID / path the same way for --resume, --export and --replay."""
    if name == "last":
        name = (base / "last-session.txt").read_text(encoding="utf-8").strip()
    requested = Path(name)
    return requested if requested.is_absolute() or len(requested.parts) > 1 else base / requested


def load_local_key():
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    # This exact file was supplied for this project. Never source it as shell code.
    path = ROOT.parent / ".env.live"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "TYPESAFE_API_KEY":
                os.environ["TYPESAFE_API_KEY"] = value.strip().strip('"').strip("'")
                return


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="JEVIS, a terminal agent: idea, plan, work and observable checks")
    parser.add_argument("--project", type=Path, help="Working project: the agent may change files here")
    parser.add_argument("--mission", choices=["loglab", "cryptolab"], help="Create a fresh copy of a practice project; you send the request")
    parser.add_argument("--resume", metavar="SESSION", help="Resume a session: last, ID or path")
    parser.add_argument("--sessions", type=Path, default=ROOT / ".sessions", help="Where to save history and logs")
    parser.add_argument("--prompt", help="Only fill the field; does not start the agent automatically")
    parser.add_argument("--direct", action="store_true", help="Chat without the upfront questions and plan acceptance")
    parser.add_argument("--run", metavar="TEXT", help="Run one request explicitly without the TUI; JSONL for integrations")
    parser.add_argument("--mode", choices=["auto", "plan"], help="auto: execution; plan: read only and a plan")
    parser.add_argument("--jev-mode", choices=["assist", "observe", "off"], help="How to apply Jev decisions; assist by default")
    parser.add_argument("--list", action="store_true", help="List saved sessions as JSON; no models")
    parser.add_argument("--export", action="store_true", help="Save --resume SESSION as Markdown; no models")
    parser.add_argument("--doctor", action="store_true", help="Check dependencies and the key without calling models")
    parser.add_argument("--replay", metavar="SESSION", help="Recompute the decisions of a saved session; no models, no workspace")
    parser.add_argument("--worker", choices=["codex", "claude"],
                        help="Who does the work: codex or claude; saved in the session")
    parser.add_argument("--web", choices=["off", "on"],
                        help="Let the worker search and read on the web; off by default")
    parser.add_argument("--demo", action="store_true",
                        help="A full turn without Codex or a key: answers are synthesised locally and flagged")
    args = parser.parse_args(argv)
    if args.replay:
        if args.run or args.project or args.mission or args.resume or args.export:
            parser.error("--replay only reads the log; do not combine it with a run or a project")
        try:
            report = replay_session(session_directory(args.sessions, args.replay))
        except (ValueError, OSError) as exc:
            print(clean(str(exc)), file=sys.stderr)
            return 2
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["mismatches"] == 0 else 2
    if args.list:
        print(json.dumps(list_sessions(args.sessions), ensure_ascii=False, indent=2))
        return 0
    if args.export and not args.resume:
        parser.error("--export requires --resume SESSION (or last)")
    if args.export and (args.run or args.mode or args.jev_mode or args.prompt):
        parser.error("--export does not combine with a request or a mode change")
    if args.demo and args.project:
        # The demo worker writes example files; it may only do so in a workspace
        # the session owns, never in a project the user pointed the agent at.
        parser.error("--demo works in its own workspace; do not combine it with --project")
    if args.doctor:
        load_local_key()
        import textual
        def probe(resolve):
            try:
                return resolve()
            except RuntimeError as exc:
                return str(exc)
        binary = probe(codex_binary)
        print(json.dumps({"python": sys.version.split()[0], "textual": textual.__version__,
                          "codex": binary, "claude": probe(claude_binary),
                          "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY")),
                          "sessions": str(args.sessions.resolve())}, ensure_ascii=False, indent=2))
        return 0
    try:
        if args.resume:
            if args.project or args.mission:
                parser.error("--resume already sets the project; do not combine with --project/--mission")
            session = Session.load(session_directory(args.sessions, args.resume), activate=not args.export)
        else:
            session = Session.create(args.sessions, project=args.project, mission=args.mission)
        if args.export:
            print(export_session(session))
            return 0
        session.configure(execution_mode=args.mode, jev_mode=args.jev_mode, web=args.web)
        if args.worker:
            session.use_worker(args.worker)
        if args.demo:
            session.use_demo()
        elif session.jev_mode != "off":
            load_local_key()
        if args.run:
            try:
                result = asyncio.run(session.run_turn(args.run, lambda e: print(json.dumps(e, ensure_ascii=False), flush=True)))
            except KeyboardInterrupt:
                return 130
            return 0 if result["status"] in ("accepted", "ready", "answered") else 2
        from .tui import JevApp
        JevApp(session, initial_prompt=args.prompt, guided=not args.direct).run()
        return 0
    except (ValueError, OSError) as exc:
        print(clean(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
