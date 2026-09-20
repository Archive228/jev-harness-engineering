"""Separate main-thread process preserves the lab client's total HTTP deadline."""
import json
import os
from pathlib import Path
import sys


def main():
    # Reuse the tested response contract, not the toy task orchestration.
    lab = Path(__file__).resolve().parents[2] / "jev-harness-lab"
    sys.path.insert(0, str(lab))
    from judge import Judge, JudgeError
    request_path, response_path = map(Path, sys.argv[1:3])
    try:
        if not os.environ.get("TYPESAFE_API_KEY"):
            raise JudgeError("TYPESAFE_API_KEY не задан. Передайте ключ TypeSafe через окружение.")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        judge = Judge("live", response_path.parent / "provider", timeout=20, model=request["model"])
        response = judge.ask(request["state"], request["questions"])
        response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except (ValueError, OSError, JudgeError) as exc:
        print("Jev: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
