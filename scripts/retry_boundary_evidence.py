"""Bounded fixture evidence planner. Static imports are candidates, not runtime proof."""
import ast,json,re

def plan(sources,initial,vision=None,budget=4):
 graph={};config_readers=set()
 for path,source in sources.items():
  if not path.endswith('.py'):continue
  tree=ast.parse(source);edges=[]
  for node in ast.walk(tree):
   if isinstance(node,ast.ImportFrom) and node.module:
    target=node.module+'.py'
    if target in sources:edges.append(target)
   if isinstance(node,ast.Constant) and node.value=='topology.json':config_readers.add(path)
  graph[path]=sorted(set(edges))
 topology=json.loads(sources['topology.json'])
 external={k:v for k,v in topology.items() if isinstance(v,dict) and v.get('zone')=='external'}
 if not external or not config_readers:raise ValueError('EXTERNAL_EVIDENCE_MISSING')
 # Reach all repository-local import dependencies, and retain predecessors to sinks.
 seen=set(initial);queue=list(initial)
 while queue:
  for nxt in graph.get(queue.pop(0),[]):
   if nxt not in seen:seen.add(nxt);queue.append(nxt)
 sinks=seen & config_readers
 required=set(sinks)
 changed=True
 while changed:
  changed=False
  for src,edges in graph.items():
   if src in seen and any(t in required for t in edges) and src not in required:
    required.add(src);changed=True
 extra=sorted(required-set(initial))+['topology.json']
 if len(extra)>budget:raise ValueError('MANDATORY_EVIDENCE_EXCEEDS_BUDGET')
 hints=sorted(set(re.findall(r'\b[\w]+\.py\b',vision or '')))
 return {'selected':list(initial)+extra,'additional':extra,'importGraph':graph,
         'externalConfig':external,'configReaders':sorted(sinks),
         'visionMentionedFiles':hints,'unresolvedVisionFiles':sorted(set(hints)-set(sources)),
         'note':'Raw vision statements are advisory only and are not passed as verified facts. Import graph is not runtime dataflow proof; read implementations and run tests.',
         'indexedBytes':sum(len(v.encode()) for v in sources.values()),
         'unreadSourceFiles':sorted(set(sources)-set(initial)-set(extra))}
