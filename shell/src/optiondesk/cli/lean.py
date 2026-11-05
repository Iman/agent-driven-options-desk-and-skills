"""Export fixed option legs for local LEAN backtests and import final results."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from optiondesk.artifacts import DISCLAIMER, artifact_dir
from optiondesk.integrations.lean import export_plan, summarize_result


def add_arguments(parser):
    parser.add_argument("action", choices=("export", "import"))
    for name in ("plan", "destination", "start", "end", "exercise-style", "data-mode", "result", "bundle"):
        parser.add_argument("--"+name)
    parser.add_argument("--multiplier", type=int)


def run(args):
    if args.action == "export":
        if not args.plan:
            raise ValueError("export requires --plan")
        destination = args.destination or artifact_dir()/"lean"/uuid4().hex
        bundle = export_plan(json.loads(Path(args.plan).read_text()), destination,
                             start=args.start, end=args.end, exercise_style=args.exercise_style,
                             multiplier=args.multiplier, data_mode=args.data_mode)
        return dict(bundle=bundle, artifact=str(Path(destination).resolve()), degraded=False,
                    degraded_reason=None, disclaimer=DISCLAIMER,
                    limitations=["Fixed single-expiry legs; separate simulated market orders.",
                                 "Provide a local LEAN configuration and licensed data before execution.",
                                 "No historical strategy selection or automatic look-ahead validation."])
    if args.action != "import" or not args.result or not args.bundle:
        raise ValueError("import requires --result and --bundle")
    raw = Path(args.result).read_bytes()
    result = summarize_result(json.loads(raw), json.loads(Path(args.bundle).read_text()))
    result.update(result_sha256=hashlib.sha256(raw).hexdigest(), artifact=str(Path(args.result).resolve()),
                  degraded=True, degraded_reason="Fill/provenance checks do not validate data coverage or model suitability.",
                  disclaimer=DISCLAIMER)
    return result
