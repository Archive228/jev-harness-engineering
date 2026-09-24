"""Copy a bounded, inspectable mission and return an external check contract."""
from pathlib import Path
import shutil
import sys


MISSION_ROOT = Path(__file__).resolve().parents[1] / "missions"


def prepare_mission(name: str, workspace: Path) -> dict:
    if name not in ("loglab", "cryptolab"):
        raise ValueError("Unknown mission: %s. Available: loglab, cryptolab" % name)
    workspace = Path(workspace).expanduser().absolute()
    if workspace.is_symlink():
        raise ValueError("Mission workspace must not be a symlink")
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        raise ValueError("Mission workspace must be empty; existing files are never overwritten")
    source = (MISSION_ROOT.parent / "examples" / "crypto-ledger") if name == "cryptolab" else MISSION_ROOT / "loglab"
    shutil.copytree(source / "seed", workspace, dirs_exist_ok=True)
    if name == "cryptolab":
        return {"prompt": (source / "task.txt").read_text(encoding="utf-8"),
                "checks": [{"id": "ledger-contract", "title": "Crypto Ledger: seven predefined tests",
                            "argv": [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]}],
                "protected": []}
    oracle = source / "oracle.py"
    checks = [
        ("timestamps", "UTC ordering and timezone normalization"),
        ("duplicates", "Deduplicate event_id without inflating counts"),
        ("malformed", "Recover from malformed lines and invalid events"),
        ("severity", "Normalize severity and preserve incident evidence"),
        ("artifacts", "Write usable JSON and Markdown reports"),
        ("combined", "All requirements on a mixed incident"),
    ]
    return {
        "prompt": (source / "task.md").read_text(encoding="utf-8"),
        "checks": [
            {"id": name, "title": title,
             "argv": [sys.executable, "-B", str(oracle), "--check", name,
                      "--project", str(workspace)]}
            for name, title in checks
        ],
        "protected": [],
    }
