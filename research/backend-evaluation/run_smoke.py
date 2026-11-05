"""Run the pinned LEAN image with synthetic data and verify cash reconciliation."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from evaluate import summarize_result
from prepare_smoke import prepare


def run(destination):
    destination = Path(destination).resolve()
    prepare(destination)
    evidence = json.loads(Path(__file__).with_name("evidence.json").read_text())
    image = evidence["lean_image"]
    command = ["docker", "run", "--rm", "--network", "none", "--hostname", "evaluation",
               "-v", f"{destination}:/evaluation"]
    reference_copy = (
        'from pathlib import Path; import shutil; '
        '[shutil.copytree(Path("/Lean/Data")/name,Path("/evaluation/data")/name,dirs_exist_ok=True) '
        'for name in ("market-hours","symbol-properties")]')
    subprocess.run(command + ["--entrypoint", "python3", image, "-c", reference_copy], check=True)
    with (destination / "run.log").open("w") as log:
        subprocess.run(command + ["-v", f"{destination}/config.json:/Lean/Launcher/bin/Debug/config.json:ro",
                                  image], stdout=log, stderr=subprocess.STDOUT, check=True)
    raw = (destination / "results/OptionDeskEvaluation.json").read_bytes()
    result = json.loads(raw)
    report = summarize_result(result, json.loads((destination / "plan.json").read_text()))
    orders = sorted(result["orders"].values(), key=lambda order: order["id"])
    if (len(orders) != 2 or [order["quantity"] for order in orders] != [1, -1]
            or [Decimal(str(order["price"])) for order in orders] != [Decimal("2.1"), Decimal("2.2")]
            or result["statistics"].get("Total Fees") != "$2.00"
            or Decimal(result["statistics"]["End Equity"]) != Decimal("100008")
            or result["runtimeStatistics"].get("Holdings") != "$0.00"):
        raise ValueError("synthetic cash or holdings did not reconcile")
    log = (destination / "run.log").read_text()
    if "ERROR::" in log:
        raise ValueError("LEAN logged an error; inspect run.log")
    report.update(lean_image=image, result_sha256=hashlib.sha256(raw).hexdigest(),
                  reconciliation={"entry": 2.1, "exit": 2.2, "contracts": 1,
                                  "multiplier": 100, "fees": 2, "net_profit": 8, "final_holdings": 0},
                  data_usage=[line for line in log.splitlines() if line.startswith("DATA USAGE::")])
    (destination / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"completed": True, "filled_orders": report["filled_orders"],
                      "synthetic_net_profit": 8, "summary": str(destination / "summary.json")}, indent=2))


if __name__ == "__main__":
    run(sys.argv[1])
