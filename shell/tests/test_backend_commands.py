import json
from pathlib import Path
import pytest
from optiondesk.cli.__main__ import build_parser
from optiondesk.cli import lean, price
from optiondesk.mcp.server import handle


def plan():
    return {"underlying":"SPY","expiry":"2016-01-15","legs":[
        {"kind":"call","side":"long","qty":1,"strike":200,"price":2}]}


def test_lean_export_and_import_provenance(tmp_path):
    p=tmp_path/'plan.json';p.write_text(json.dumps(plan()))
    destination=tmp_path/'bundle'
    args=build_parser().parse_args(['lean','export','--plan',str(p),'--destination',str(destination),
        '--start','2016-01-04','--end','2016-01-06','--exercise-style','american','--multiplier','100','--data-mode','synthetic'])
    exported=lean.run(args)
    assert exported['bundle']['legs'][0]['quantity']==1
    assert (destination/'main.py').is_file()
    result={'state':{'Status':'Completed','RuntimeError':''},'runtimeStatistics':{'OptionDesk Data Mode':'synthetic'},
            'orders':{'1':{'status':3,'tag':'OptionDesk plan sha256: '+exported['bundle']['plan_sha256']}},
            'statistics':{'Total Orders':'1'}}
    r=tmp_path/'result.json';r.write_text(json.dumps(result))
    args=build_parser().parse_args(['lean','import','--result',str(r),'--bundle',str(destination/'plan.json')])
    assert lean.run(args)['filled_orders']==1
    result['orders']['1']['tag']='unrelated';r.write_text(json.dumps(result))
    with pytest.raises(ValueError):lean.run(args)


def test_quantlib_mcp_uses_the_same_handler(monkeypatch):
    from optiondesk import engine_bridge
    seen=[]
    def backend(payload):
        seen.append(payload)
        return {'price':20,'degraded':False,'degraded_reason':None}
    monkeypatch.setattr(engine_bridge,'quantlib_price',backend)
    arguments=dict(spot=80,strike=100,valuation_date='2026-09-12',expiry='2027-09-12',
                   volatility=.2,rate=.05,dividend_yield=0,kind='put',exercise_style='american')
    response=handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'option_price','arguments':arguments}})
    assert not response['result'].get('isError')
    assert seen==[arguments]
