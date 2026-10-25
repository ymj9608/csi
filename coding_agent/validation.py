import ast
import builtins
import symtable
from .profile import ALLOWED_IMPORTS, FUNCTIONS, TARGET
from .repository import Rejected

def validate_code(before, after):
    if not isinstance(after, str) or not 20 < len(after.encode()) <= 24_000 or '\x00' in after:
        raise Rejected('CODE_SIZE')
    try:
        old, new = ast.parse(before), ast.parse(after)
        compile(new, TARGET, 'exec')
    except (SyntaxError, ValueError):
        raise Rejected('PYTHON_SYNTAX') from None
    old_fn = {x.name:x for x in old.body if isinstance(x, ast.FunctionDef)}
    new_fn = {x.name:x for x in new.body if isinstance(x, ast.FunctionDef)}
    if set(old_fn) != FUNCTIONS or set(new_fn) != FUNCTIONS or sum(isinstance(x, ast.FunctionDef) for x in new.body) != len(FUNCTIONS):
        raise Rejected('FUNCTION_SET_CHANGED')
    for name in FUNCTIONS:
        if ast.dump(old_fn[name].args) != ast.dump(new_fn[name].args) or new_fn[name].decorator_list:
            raise Rejected('FUNCTION_SIGNATURE_CHANGED')
    if ast.dump(old_fn['validate_lab_signup']) != ast.dump(new_fn['validate_lab_signup']):
        raise Rejected('SYNTHETIC_GUARD_CHANGED')
    if any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='hash_signup_password'
           for node in ast.walk(new_fn['verify_lab_password'])):
        raise Rejected('LEGACY_USES_NEW_HASH', {'function':'verify_lab_password'})
    for node in ast.walk(new):
        if isinstance(node, ast.Import) and any(a.name not in ALLOWED_IMPORTS for a in node.names):
            raise Rejected('IMPORT_NOT_ALLOWED', {'line':node.lineno,'module':','.join(a.name for a in node.names)[:160]})
        if isinstance(node, ast.ImportFrom) and not (node.module == 'app.core.errors' and node.level == 0 and [a.name for a in node.names] == ['AppError']):
            raise Rejected('IMPORT_NOT_ALLOWED', {'line':node.lineno,'module':(node.module or '')[:160]})
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'exec','eval','open','compile','__import__','getattr','setattr','globals','locals'}:
            raise Rejected('DYNAMIC_CODE_NOT_ALLOWED')
        if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            raise Rejected('DYNAMIC_CODE_NOT_ALLOWED')
        if isinstance(node, ast.Attribute) and (node.attr in {'disable','basicConfig','setLevel','addHandler','removeHandler','setLoggerClass'}
                or isinstance(node.ctx, ast.Store) and node.attr in {'disabled','propagate','handlers'}):
            raise Rejected('LOGGING_CONFIG_NOT_ALLOWED')
    symbols = symtable.symtable(after, TARGET, 'exec')
    defined = {s.get_name() for s in symbols.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()} | set(dir(builtins))
    missing = set()
    def check_scope(scope):
        for symbol in scope.get_symbols():
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in defined:
                missing.add(symbol.get_name())
        for child in scope.get_children():
            check_scope(child)
    check_scope(symbols)
    if missing:
        raise Rejected('UNDEFINED_GLOBAL', {'names':sorted(missing)[:16]})
    return True

def validate_response(value, before, finding_ids, reference_ids):
    if not isinstance(value, dict) or set(value) != {'files','reason','evidence_ids','limitations','tests_to_run'}:
        raise Rejected('RESPONSE_SCHEMA')
    files = value['files']
    if not isinstance(files,list) or len(files)!=1 or not isinstance(files[0],dict) or set(files[0]) != {'path','content'} or files[0]['path'] != TARGET:
        raise Rejected('EDIT_SCOPE')
    if not isinstance(value['reason'],str) or not 1 <= len(value['reason']) <= 2400:
        raise Rejected('REASON_SCHEMA')
    for key in ('evidence_ids','limitations','tests_to_run'):
        if not isinstance(value[key],list) or len(value[key])>16 or any(not isinstance(x,str) or len(x)>1600 for x in value[key]):
            raise Rejected('RESPONSE_SCHEMA')
    cited=set(value['evidence_ids'])
    if not cited <= finding_ids | reference_ids or not cited & finding_ids or not cited & reference_ids:
        raise Rejected('EVIDENCE_IDS')
    # Model prose is a recommendation, not a compliance verdict; require actual retrieved sources.
    validate_code(before,files[0]['content'])
    return files[0]['content']
