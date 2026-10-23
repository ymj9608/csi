"""Validate source-backed file/function handoffs without widening a host write policy."""
import ast
import hashlib
from .call_contract import collect_call_contract, contradictory_input_accesses, CONTRACT_RULES

class ScopeError(ValueError):
    pass

def digest(text):return hashlib.sha256(text.encode()).hexdigest()

def declaration(source, name):
    try: tree=ast.parse(source)
    except SyntaxError as exc: raise ScopeError('SOURCE_SYNTAX') from exc
    matches=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    if len(matches)!=1:raise ScopeError('FUNCTION_NOT_FOUND')
    node=matches[0]
    if node.decorator_list:raise ScopeError('DECORATED_FUNCTION_UNSUPPORTED')
    return node

def build_handoff(sources, path, symbol, allowed_paths, evidence_paths, instruction, constraints):
    if path not in sources or path not in allowed_paths:raise ScopeError('PATH_NOT_ALLOWED')
    node=declaration(sources[path],symbol)
    if not evidence_paths or any(p not in sources for p in evidence_paths):raise ScopeError('EVIDENCE_MISSING')
    if not isinstance(instruction,str) or not instruction.strip():raise ScopeError('INSTRUCTION_MISSING')
    return {'path':path,'function':symbol,'sourceSha256':digest(sources[path]),
            'source':sources[path],'functionSource':ast.get_source_segment(sources[path],node),
            'evidence':{p:{'source':sources[p],'sha256':digest(sources[p])} for p in evidence_paths},
            'inputContract':collect_call_contract({p:sources[p] for p in set(evidence_paths) | {path}},path,symbol),
            'contractRules':CONTRACT_RULES,
            'instruction':instruction,'preserve':list(constraints),
            'scope':'Replace this function only. Other declarations, files, tests and settings are read-only.'}

def replace_function(source, packet, replacement):
    if digest(source)!=packet['sourceSha256']:raise ScopeError('SOURCE_CHANGED')
    original=declaration(source,packet['function'])
    try: tree=ast.parse(replacement)
    except (SyntaxError,TypeError) as exc:raise ScopeError('PATCH_SYNTAX') from exc
    if len(tree.body)!=1:
        # Some small models return the whole module despite a function-only request.
        # Accept only if every OTHER declaration is AST-identical, preserving original text.
        before=ast.parse(source)
        if len(tree.body)!=len(before.body):raise ScopeError('OUTSIDE_FUNCTION_SCOPE')
        index=next(i for i,n in enumerate(before.body) if n.lineno==original.lineno)
        if any(ast.dump(a)!=ast.dump(b) for i,(a,b) in enumerate(zip(before.body,tree.body)) if i!=index):
            raise ScopeError('OUTSIDE_FUNCTION_SCOPE')
        replacement=ast.get_source_segment(replacement,tree.body[index])
        tree=ast.parse(replacement)
    if len(tree.body)!=1 or not isinstance(tree.body[0],type(original)):raise ScopeError('OUTSIDE_FUNCTION_SCOPE')
    new=tree.body[0]
    if new.name!=original.name or new.decorator_list or ast.dump(new.args)!=ast.dump(original.args):raise ScopeError('SIGNATURE_CHANGED')
    if (ast.dump(new.returns) if new.returns else None) != (ast.dump(original.returns) if original.returns else None):
        raise ScopeError('RETURN_ANNOTATION_CHANGED')
    contradictions=contradictory_input_accesses(replacement,packet.get('inputContract',{}))
    if contradictions:
        raise ScopeError('INPUT_CONTRACT_MISMATCH: '+str(contradictions))
    lines=source.splitlines(keepends=True)
    result=''.join(lines[:original.lineno-1])+replacement.rstrip()+'\n'+''.join(lines[original.end_lineno:])
    compile(result,packet['path'],'exec')
    return result
