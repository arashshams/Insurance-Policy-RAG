"""
model_check.py — is the pinned model still there, and is there a newer one?

The generator and judge models are pinned (PLAN.md D4, D15), so nothing moves
on its own. This check, run weekly by .github/workflows/model-check.yml, lists
the models the API key can use and reports:
  * ACTION NEEDED  the pinned generator or judge model is no longer listed
                   (retired, or closed to new users): the app or the judge will
                   fail until the model is bumped.
  * UPGRADE        a newer "gemini-<version>-flash" model is listed: worth
                   evaluating (README, "Upgrading the model").
Listing models is not a generation request, so it costs no generation quota.
The API key is sent in a header, never in the URL.

CLI (needs GEMINI_API_KEY):
    python -m src.model_check                 # print the report
    python -m src.model_check --out report.md # also write it to a file
In GitHub Actions it also sets the step outputs action_needed / upgrade_available.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_FLASH_RE = re.compile(r"^gemini-(\d+(?:\.\d+)*)-flash$")


def flash_version(name: str) -> tuple[int, ...] | None:
    """(3, 8) for "gemini-3.8-flash"; None for anything else (lite, preview,
    dated or numbered variants are not upgrade candidates)."""
    m = _FLASH_RE.match(name.removeprefix("models/"))
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def list_models(api_key: str, timeout: float = 30.0) -> list[str]:
    """Names of the models this key can use (without the "models/" prefix)."""
    names, token = [], None
    while True:
        query = {"pageSize": 1000, **({"pageToken": token} if token else {})}
        req = urllib.request.Request(f"{LIST_URL}?{urllib.parse.urlencode(query)}",
                                     headers={"x-goog-api-key": api_key})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names += [m["name"].removeprefix("models/") for m in data.get("models", [])
                  if m.get("name")]
        token = data.get("nextPageToken")
        if not token:
            return sorted(set(names))


def check(available: list[str], pinned: dict[str, str]) -> dict:
    """Compare the available models with the pinned ones.

    pinned: role -> model, e.g. {"generator": "gemini-3.8-flash", "judge": ...}.
    """
    avail = set(available)
    missing = {role: model for role, model in pinned.items() if model not in avail}
    current = flash_version(pinned.get("generator", ""))
    newer = [] if current is None else sorted(
        (n for n in avail if (flash_version(n) or ()) > current),
        key=flash_version, reverse=True)
    return {"missing": missing, "newer": newer, "action_needed": bool(missing),
            "upgrade_available": bool(newer)}


def render(result: dict, pinned: dict[str, str]) -> str:
    lines = ["## Gemini model check", ""]
    lines += [f"- {role}: `{model}` — "
              + ("**not available** (retired or closed to new users)"
                 if role in result["missing"] else "available")
              for role, model in pinned.items()]
    lines.append("")
    if result["missing"]:
        lines += ["**Action needed:** a pinned model is gone, so the app or the judge will "
                  "fail until it is replaced. Evaluate a replacement with "
                  "`INSURANCE_RAG_GEN_MODEL` / `INSURANCE_RAG_JUDGE_MODEL`, compare the "
                  "reports, then change the default (README, \"Upgrading the model\").", ""]
    if result["newer"]:
        lines += ["**Upgrade candidates** (newer Flash versions than the generator): "
                  + ", ".join(f"`{n}`" for n in result["newer"]) + ". Worth evaluating; "
                  "nothing changes until the default is bumped.", ""]
    if not result["missing"] and not result["newer"]:
        lines += ["Nothing to do: the pinned models are available and no newer Flash "
                  "version is listed.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from src import judge as jd
    from src import rag_pipeline as rp

    ap = argparse.ArgumentParser(description="Check the pinned Gemini models.")
    ap.add_argument("--out", default=None, help="also write the markdown report here")
    args = ap.parse_args(argv)
    try:
        key = rp._read_api_key()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    pinned = {"generator": rp.GEN_MODEL, "judge": jd.JUDGE_MODEL}
    try:
        available = list_models(key)
    except Exception as exc:  # noqa: BLE001 - network/API errors: report, don't guess
        print(f"error: could not list models: {exc}", file=sys.stderr)
        return 2
    result = check(available, pinned)
    report = render(result, pinned)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"action_needed={str(result['action_needed']).lower()}\n")
            fh.write(f"upgrade_available={str(result['upgrade_available']).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
