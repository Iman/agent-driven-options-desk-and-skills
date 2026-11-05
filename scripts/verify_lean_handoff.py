"""Exercise the production LEAN handoff with the pinned offline synthetic fixture."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from optiondesk.integrations.lean import export_plan, summarize_result

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/backend-evaluation"))
from prepare_smoke import prepare


def main():
    image = json.loads((ROOT/"research/backend-evaluation/evidence.json").read_text())["lean_image"]
    with tempfile.TemporaryDirectory(prefix="optiondesk-lean-") as temporary:
        root=Path(temporary);work=root/"work";prepare(work)
        plan={"underlying":"SPY","expiry":"2016-01-15","legs":[
            {"kind":"call","side":"long","qty":1,"strike":200,"price":2}]}
        bundle=export_plan(plan,root/"bundle",start="2016-01-04",end="2016-01-06",
                           exercise_style="american",multiplier=100,data_mode="synthetic")
        for name in ("main.py","plan.json"):
            shutil.copyfile(root/"bundle"/name,work/name)
        config=json.loads((work/"config.json").read_text())
        config["algorithm-type-name"]="OptionDeskBacktest"
        (work/"config.json").write_text(json.dumps(config))
        command=["docker","run","--rm","--network","none","--hostname","evaluation","-v",f"{work}:/evaluation"]
        copy='from pathlib import Path; import shutil; [shutil.copytree(Path("/Lean/Data")/n,Path("/evaluation/data")/n) for n in ("market-hours","symbol-properties")]'
        subprocess.run(command+["--entrypoint","python3",image,"-c",copy],check=True)
        with (work/"run.log").open("w") as log:
            subprocess.run(command+["-v",f"{work}/config.json:/Lean/Launcher/bin/Debug/config.json:ro",image],
                           stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        result=json.loads((work/"results/OptionDeskBacktest.json").read_text())
        summary=summarize_result(result,bundle)
        assert summary["filled_orders"]==2
        assert summary["statistics"]["End Equity"]=="100008"
        assert summary["statistics"]["Total Fees"]=="$2.00"
        assert result["runtimeStatistics"]["Holdings"]=="$0.00"
        assert "ERROR::" not in (work/"run.log").read_text()
        print(json.dumps({"verified":"production LEAN export, offline run and import", "filled_orders":2,
                          "synthetic_net_profit":8,"image":image},indent=2))


if __name__=="__main__":
    main()
