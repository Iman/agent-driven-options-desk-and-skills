import json
import subprocess
import sys
import pytest


def test_quantlib_command_runs_isolated_worker():
    pytest.importorskip('QuantLib')
    result=subprocess.run([sys.executable,'-m','optiondesk.cli','price','--spot','80','--strike','100',
        '--valuation-date','2026-09-12','--expiry','2027-09-12','--volatility','.2','--rate','.05',
        '--dividend-yield','0','--kind','put','--exercise-style','american'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr+result.stdout
    assert json.loads(result.stdout)['price']==pytest.approx(20,abs=.001)
