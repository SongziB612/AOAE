"""Apply expert-mixture identity to existing net-return matrices without tuning."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from aoae.strategy_sleeve_identity import inspect_sleeve_mixture


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--selection-report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    r=json.loads(args.selection_report.read_text())
    cases=[]
    for name,digest in r['matrix_sha256'].items():
        raw=(args.selection_report.parent/name).read_bytes()
        if sha256(raw).hexdigest()!=digest:
            raise ValueError('matrix changed')
        matrix=json.loads(raw)
        result=inspect_sleeve_mixture(matrix['net_returns'])
        cases.append({'matrix':name,'columns':matrix['columns'],'matrix_sha256':digest,**result})
    result={'status':'IDENTITY_CONFIRMED' if all(c['maximum_identity_error']<1e-10 and c['maximum_inter_sleeve_transfer']<1e-10 for c in cases) else 'FAIL',
            'cases':cases,'capital_authorized':False,
            'interpretation':'Wealth-proportional expert weights equal initial equal funding with no subsequent inter-sleeve transfers. This is not a new timing edge.',
            'source_sha256':{str(p):sha256(p.read_bytes()).hexdigest() for p in
                             (args.selection_report,Path(__file__),Path('src/aoae/strategy_sleeve_identity.py'))}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({'status':result['status'],'matrices':len(cases),'max_wealth_error':max(c['maximum_identity_error'] for c in cases),'max_transfer':max(c['maximum_inter_sleeve_transfer'] for c in cases)}))


if __name__=='__main__':
    main()
