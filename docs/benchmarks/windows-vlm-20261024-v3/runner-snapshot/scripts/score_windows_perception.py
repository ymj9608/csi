"""Post-hoc representation diagnostic; never changes frozen scores or prompts.

Only literal labels printed in the image are accepted as aliases for IDs.
No fuzzy matching, inferred edges, case repair or invented nodes. This diagnostic
was added after the first Instruct response used full box labels instead of IDs.
"""
import json
import sys
from pathlib import Path


def score(out):
    graph=json.loads((out/'cases/retry-small/architecture.json').read_text(encoding='utf-8'))
    aliases={node:node for node in graph['nodes']}
    for node,route in graph['routes'].items():
        aliases[f"{node}: {route['boundary']} {route['recipient']}"]=node
    truth={(e['from'],e['to'],e['style']) for e in graph['edges']}
    rows=[]
    for path in sorted((out/'calls').glob('compat-*-image.json')):
        raw=json.loads(path.read_text(encoding='utf-8'))
        if raw['status']!='COMPLETED':
            rows.append({'model':raw['model'],'status':raw['status'],'semanticScore':None})
            continue
        answer=raw['answer']
        mapped_nodes={aliases.get(n,n) for n in answer['nodes']}
        edges={(aliases.get(e['from'],e['from']),aliases.get(e['to'],e['to']),e['style']) for e in answer['edges']}
        rows.append({'model':raw['model'],'status':'COMPLETED',
                     'exactVisibleLabelAliasesUsed':{n:aliases[n] for n in answer['nodes'] if n in aliases and n!=aliases[n]},
                     'matchedNodes':len(mapped_nodes&set(graph['nodes'])),
                     'extraNodes':len(mapped_nodes-set(graph['nodes'])),
                     'matchedDirectedStyledEdges':len(edges&truth),
                     'missingEdges':len(truth-edges),'extraEdges':len(edges-truth)})
    value={'analysis':'POST_HOC_SUPPLEMENTAL; primary compatibility.json retained unchanged',
           'rule':'Only exact printed box labels may replace IDs; no response modification or model reinference.',
           'limits':'Single four-node image. Relation correctness does not establish general architecture/security accuracy.',
           'results':rows}
    (out/'perception-label-diagnostic.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    return value


if __name__=='__main__': print(json.dumps(score(Path(sys.argv[1]))))
