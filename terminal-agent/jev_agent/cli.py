"""Launch a real empty terminal chat. No task starts until the user submits it."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from .core import Session
from .runtime import clean, codex_binary


ROOT = Path(__file__).resolve().parents[1]


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


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Jev Terminal — настоящий чат, действия Codex и наблюдаемый harness")
    parser.add_argument("--project", type=Path, help="Рабочий проект: агент сможет изменять файлы здесь")
    parser.add_argument("--mission", choices=["loglab"], help="Создать новую копию учебного проекта; запрос отправляете вы")
    parser.add_argument("--resume", metavar="SESSION", help="Продолжить сессию: last, ID или путь")
    parser.add_argument("--sessions", type=Path, default=ROOT / ".sessions", help="Где сохранять историю и протоколы")
    parser.add_argument("--prompt", help="Только заполнить поле; не запускает агента автоматически")
    parser.add_argument("--run", metavar="TEXT", help="Явно запустить один запрос без TUI; JSONL для интеграций")
    parser.add_argument("--doctor", action="store_true", help="Проверить зависимости и наличие ключа, не вызывая модели")
    args = parser.parse_args()
    load_local_key()
    if args.doctor:
        import textual
        try:
            binary = codex_binary()
        except RuntimeError as exc:
            binary = str(exc)
        print(json.dumps({"python": sys.version.split()[0], "textual": textual.__version__,
                          "codex": binary, "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY")),
                          "sessions": str(args.sessions.resolve())}, ensure_ascii=False, indent=2))
        return 0
    try:
        if args.resume:
            if args.project or args.mission:
                parser.error("--resume уже определяет проект; не сочетайте с --project/--mission")
            name = ((args.sessions / "last-session.txt").read_text().strip()
                    if args.resume == "last" else args.resume)
            directory = Path(name) if Path(name).is_absolute() else args.sessions / name
            session = Session.load(directory)
        else:
            session = Session.create(args.sessions, project=args.project, mission=args.mission)
        if args.run:
            try:
                result = asyncio.run(session.run_turn(args.run, lambda e: print(json.dumps(e, ensure_ascii=False), flush=True)))
            except KeyboardInterrupt:
                return 130
            return 0 if result["status"] in ("accepted", "ready", "answered") else 2
        from .tui import JevApp
        JevApp(session, initial_prompt=args.prompt).run()
        return 0
    except (ValueError, OSError) as exc:
        print(clean(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
