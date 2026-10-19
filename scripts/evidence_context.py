"""Bounded Python AST evidence. Never imports or executes the scanned application."""
import ast

FIELDS = {'name', 'full_name', 'phone_number', 'resident_registration_no', 'date_of_birth', 'home_address'}
CLASSES = {'Signup', 'ProfileUpdate', 'User', 'CsiSignupProfile'}


def collect_context(root):
    declarations = {}
    flows = []
    for path in sorted(root.rglob('*.py')):
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeError):
            continue
        file = str(path.relative_to(root))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in CLASSES:
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id in FIELDS:
                        declarations[(file, stmt.lineno)] = {'field': stmt.target.id, 'entity': node.name,
                            'declarationKind': 'INPUT' if node.name in {'Signup', 'ProfileUpdate'} else 'MODEL',
                            'runtimeVerified': False, 'signals': []}
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            inputs = {a.arg: a.annotation.id for a in fn.args.args
                      if isinstance(a.annotation, ast.Name) and a.annotation.id in {'Signup', 'ProfileUpdate'}}
            if not inputs:
                continue
            # Only explicit db.add(Model(...)) or adjacent model assignment + db.add(variable).
            for block in ast.walk(fn):
                body = getattr(block, 'body', None)
                if not isinstance(body, list):
                    continue
                for i, stmt in enumerate(body):
                    call = stmt.value if isinstance(stmt, ast.Expr) else None
                    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and isinstance(call.func.value, ast.Name) and call.func.value.id == 'db'
                            and call.func.attr == 'add' and len(call.args) == 1):
                        continue
                    ctor = call.args[0]
                    if isinstance(ctor, ast.Name) and i:
                        prev = body[i-1]
                        if isinstance(prev, ast.Assign) and len(prev.targets) == 1 and isinstance(prev.targets[0], ast.Name) and prev.targets[0].id == ctor.id:
                            ctor = prev.value
                    if not (isinstance(ctor, ast.Call) and isinstance(ctor.func, ast.Name) and ctor.func.id in {'User', 'CsiSignupProfile'}):
                        continue
                    lab = False
                    cur = stmt
                    while cur in parents:
                        parent = parents[cur]
                        if isinstance(parent, ast.If) and cur in parent.body and ast.dump(parent.test) == ast.dump(ast.parse('settings.csi_lab_mode', mode='eval').body):
                            lab = True
                        cur = parent
                    for field in FIELDS:
                        for var, source in inputs.items():
                            matched = False
                            for kw in ctor.keywords:
                                if kw.arg == field and isinstance(kw.value, ast.Attribute) and isinstance(kw.value.value, ast.Name) and kw.value.value.id == var and kw.value.attr == field:
                                    matched = True
                                if kw.arg is None and isinstance(kw.value, ast.Call):
                                    dump = kw.value
                                    if isinstance(dump.func, ast.Attribute) and isinstance(dump.func.value, ast.Name) and dump.func.value.id == var and dump.func.attr == 'model_dump' and not dump.args:
                                        try:
                                            opts = {k.arg: ast.literal_eval(k.value) for k in dump.keywords}
                                            # Unknown serialization options are deliberately unsupported.
                                            if set(opts) <= {'exclude'} and isinstance(opts.get('exclude', set()), (set, list, tuple)) and field not in opts.get('exclude', set()):
                                                matched = True
                                        except (ValueError, TypeError):
                                            pass
                            if matched:
                                flows.append({'field': field, 'source': source, 'target': ctor.func.id,
                                              'filePath': file, 'line': stmt.lineno, 'labOnly': lab})
    for context in declarations.values():
        context['signals'] = [f for f in flows if f['field'] == context['field'] and context['entity'] in {f['source'], f['target']}][:8]
    return declarations
