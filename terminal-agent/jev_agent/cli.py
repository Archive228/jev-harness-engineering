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
from .runtime import clean, codex_binary


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
    parser = argparse.ArgumentParser(description="JEVIS — терминальный агент: идея, план, работа и наблюдаемые проверки")
    parser.add_argument("--project", type=Path, help="Рабочий проект: агент сможет изменять файлы здесь")
    parser.add_argument("--mission", choices=["loglab", "cryptolab"], help="Создать новую копию учебного проекта; запрос отправляете вы")
    parser.add_argument("--resume", metavar="SESSION", help="Продолжить сессию: last, ID или путь")
    parser.add_argument("--sessions", type=Path, default=ROOT / ".sessions", help="Где сохранять историю и протоколы")
    parser.add_argument("--prompt", help="Только заполнить поле; не запускает агента автоматически")
    parser.add_argument("--direct", action="store_true", help="Чат без предварительного опроса и согласования плана")
    parser.add_argument("--run", metavar="TEXT", help="Явно запустить один запрос без TUI; JSONL для интеграций")
    parser.add_argument("--mode", choices=["auto", "plan"], help="auto: выполнение; plan: только чтение и план")
    parser.add_argument("--jev-mode", choices=["assist", "observe", "off"], help="Как применять решения Jev; по умолчанию assist")
    parser.add_argument("--list", action="store_true", help="Список сохранённых сессий в JSON; без моделей")
    parser.add_argument("--export", action="store_true", help="Сохранить --resume SESSION в Markdown; без моделей")
    parser.add_argument("--doctor", action="store_true", help="Проверить зависимости и наличие ключа, не вызывая модели")
    parser.add_argument("--replay", metavar="SESSION", help="Пересчитать решения сохранённой сессии; без моделей и без рабочей папки")
    args = parser.parse_args(argv)
    if args.replay:
        if args.run or args.project or args.mission or args.resume or args.export:
            parser.error("--replay только читает журнал; не сочетайте его с запуском или выбором проекта")
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
        parser.error("--export требует --resume SESSION (или last)")
    if args.export and (args.run or args.mode or args.jev_mode or args.prompt):
        parser.error("--export не сочетается с запросом или изменением режима")
    if args.doctor:
        load_local_key()
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
            session = Session.load(session_directory(args.sessions, args.resume), activate=not args.export)
        else:
            session = Session.create(args.sessions, project=args.project, mission=args.mission)
        if args.export:
            print(export_session(session))
            return 0
        session.configure(execution_mode=args.mode, jev_mode=args.jev_mode)
        if session.jev_mode != "off":
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
