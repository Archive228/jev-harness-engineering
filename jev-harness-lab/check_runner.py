"""Immutable checks live outside the worker's project directory."""
import importlib.util
import json
import sys


def run(check_id, project):
    spec = importlib.util.spec_from_file_location("lab_app", project + "/app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    if check_id == "C1":
        actual = [item["id"] for item in app.search("milk")]
        assert actual == [1], "title search: expected [1], got %r" % actual
        return {"query": "milk", "actual_ids": actual, "expected_ids": [1]}
    if check_id == "C2":
        actual = [item["id"] for item in app.search("carton")]
        assert actual == [1], "description-only search: expected [1], got %r" % actual
        return {"query": "carton", "actual_ids": actual, "expected_ids": [1]}
    if check_id == "D1":
        actual = [item["id"] for item in app.api_search("carton", ["title", "description"])]
        return {"backend_direct_ids": actual, "expected_ids": [1], "backend_match": actual == [1]}
    if check_id == "D2":
        request = app.ui_request("carton")
        return {"request": request, "includes_description": "description" in request["fields"]}
    raise ValueError("Unregistered check")


if __name__ == "__main__":
    check_id = sys.argv[1]
    try:
        result = run(check_id, sys.argv[2])
        print(json.dumps({"check_id": check_id, "kind": "check_completed", "observation": result}, ensure_ascii=False))
    except AssertionError as exc:
        print(json.dumps({"check_id": check_id, "kind": "assertion_failure", "error": type(exc).__name__, "detail": str(exc)}))
        sys.exit(1)
    except (Exception, SystemExit) as exc:
        print(json.dumps({"check_id": check_id, "kind": "tool_error", "error": type(exc).__name__, "detail": str(exc)}))
        sys.exit(2)
