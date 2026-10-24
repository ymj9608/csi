"""Versioned project configuration and fail-closed, project-independent result gates."""
import ast
import json
import re
from pathlib import Path, PurePosixPath
from .repository import Rejected, git, read, digest

ROOT = Path(__file__).resolve().parent
ADAPTER = 'python-pytest-v1'
PACK = 'pii-log-leak-v1'
MODEL = 'ministral-3:8b-instruct-2512-q4_K_M'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def fingerprint(value):
    return digest(canonical(value))


def safe_path(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', value)
            or value.startswith('/') or any(p in {'', '.', '..'} for p in value.split('/'))
            or any(p.startswith('.') for p in PurePosixPath(value).parts)):
        raise Rejected('PROFILE_PATH_INVALID')
    return value


def validate_profile(p, *, prepared=True):
    required = {'schemaVersion', 'profileId', 'repository', 'runtime', 'snapshotPaths', 'editablePaths',
                'contextPaths', 'testPaths', 'pack', 'driver', 'contracts', 'ruleIds', 'reproductionTests',
                'relatedFailures', 'allowedSkips', 'model', 'generationTimeoutSeconds'}
    if prepared:
        required |= {'inventory'}
    if not isinstance(p, dict) or set(p) != required or p['schemaVersion'] != 1:
        raise Rejected('PROFILE_SCHEMA')
    if not re.fullmatch(r'[a-z0-9-]{3,80}', p['profileId']) or not re.fullmatch(r'[\w.-]+/[\w.-]+', p['repository']):
        raise Rejected('PROFILE_IDENTITY')
    r = p['runtime']
    if set(r) != {'adapter', 'imageId', 'workingDirectory'} or r['adapter'] != ADAPTER or not re.fullmatch(r'sha256:[a-f0-9]{64}', r['imageId']):
        raise Rejected('PROFILE_RUNTIME')
    safe_path(r['workingDirectory'])
    if p['model'] != MODEL or type(p['generationTimeoutSeconds']) is not int or not 30 <= p['generationTimeoutSeconds'] <= 300:
        raise Rejected('PROFILE_BUDGET')
    if p['pack'] != {'id': PACK, 'sha256': digest((ROOT/'verification/privacy_pack.py').read_text(encoding='utf-8'))}:
        raise Rejected('PACK_VERSION_MISMATCH')
    driver = p['driver']
    if set(driver) != {'path', 'sha256'}:
        raise Rejected('PROFILE_DRIVER')
    path = safe_path(driver['path'])
    if not path.startswith('project_profiles/') or not path.endswith('/driver.py'):
        raise Rejected('PROFILE_DRIVER')
    if digest((ROOT/path).read_text(encoding='utf-8')) != driver['sha256']:
        raise Rejected('DRIVER_VERSION_MISMATCH')
    for key in ('snapshotPaths', 'editablePaths', 'contextPaths', 'testPaths'):
        if not isinstance(p[key], list) or not 1 <= len(p[key]) <= 50 or len(set(p[key])) != len(p[key]):
            raise Rejected('PROFILE_PATHS')
        for path in p[key]:
            safe_path(path)
    if len(p['editablePaths']) != 1 or not p['editablePaths'][0].endswith('.py'):
        raise Rejected('PROFILE_EDIT_SCOPE')
    target = p['editablePaths'][0]
    if any(not path.endswith('.py') for path in p['contextPaths']):
        raise Rejected('PROFILE_CONTEXT_LANGUAGE')
    if target not in p['contextPaths'] or any(part.startswith('test') for part in PurePosixPath(target).parts):
        raise Rejected('PROFILE_EDIT_SCOPE')
    if not isinstance(p['contracts'], list) or not p['contracts'] or any(not isinstance(c, str) or len(c) > 1500 for c in p['contracts']):
        raise Rejected('PROFILE_CONTRACTS')
    if not p['ruleIds'] or any(not re.fullmatch(r'[A-Z]+-\d+', rule) for rule in p['ruleIds']):
        raise Rejected('PROFILE_RULES')
    for key in ('reproductionTests', 'relatedFailures', 'allowedSkips'):
        if not isinstance(p[key], list) or len(set(p[key])) != len(p[key]) or any(not isinstance(v, str) or '::' not in v for v in p[key]):
            raise Rejected('PROFILE_TEST_IDS')
    if not p['reproductionTests'] or set(p['allowedSkips']) & set(p['reproductionTests'] + p['relatedFailures']):
        raise Rejected('PROFILE_TEST_IDS')
    if prepared:
        ids = p['inventory']
        if not isinstance(ids, list) or not ids or ids != sorted(set(ids)):
            raise Rejected('PROFILE_INVENTORY')
        if not set(p['reproductionTests'] + p['relatedFailures'] + p['allowedSkips']) <= set(ids):
            raise Rejected('PROFILE_TEST_IDS')
        required_pack = {'tests/test_csi_privacy_pack.py::' + name for name in (
            'test_no_sensitive_logs', 'test_useful_log_preserved', 'test_behavior_preserved', 'test_invalid_input_rejected')}
        if not required_pack <= set(ids) or not required_pack & set(p['reproductionTests']) or required_pack & set(p['allowedSkips']):
            raise Rejected('PROFILE_PACK_REQUIRED')
    return p


def export_snapshot(repo, sha, destination, p):
    manifest = {}
    for entry in git(repo, 'ls-tree', '-rz', '--full-tree', sha).split(b'\0'):
        if not entry:
            continue
        _, raw = entry.split(b'\t', 1)
        path = raw.decode('utf-8')
        if not any(path == root or path.startswith(root + '/') for root in p['snapshotPaths']):
            continue
        safe_path(path)
        if PurePosixPath(path).suffix not in {'.py', '.ini', '.toml', '.txt', '.json', '.yml', '.yaml'}:
            continue
        if any(part.lower() in {'secrets', 'credentials', 'node_modules'} for part in PurePosixPath(path).parts):
            raise Rejected('SNAPSHOT_SECRET_PATH')
        content = read(repo, sha, path)
        manifest[path] = digest(content)
        target = destination/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8', newline='')
        if len(manifest) > 2000 or sum(f.stat().st_size for f in destination.rglob('*') if f.is_file()) > 8_000_000:
            raise Rejected('SNAPSHOT_TOO_LARGE')
    if not set(p['contextPaths']) <= manifest.keys():
        raise Rejected('PROFILE_SOURCE_MISSING')
    return manifest


def validate_candidate(before, after):
    if not isinstance(after, str) or not 20 <= len(after.encode()) <= 32000 or after == before:
        raise Rejected('CANDIDATE_SIZE_OR_NO_CHANGE')
    try:
        old, new = ast.parse(before), ast.parse(after)
        compile(new, '<candidate>', 'exec')
    except (SyntaxError, ValueError):
        raise Rejected('CANDIDATE_SYNTAX') from None
    def signatures(tree):
        return {n.name: ast.dump(n.args) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if signatures(old) != signatures(new):
        raise Rejected('CALL_CONTRACT_CHANGED')
    def imports(tree):
        return {ast.dump(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))}
    if not imports(new) <= imports(old):
        raise Rejected('IMPORT_NOT_ALLOWED')
    for node in ast.walk(new):
        if isinstance(node, ast.Name) and (node.id.startswith('__') or node.id in {'exec','eval','compile','open','__import__','getattr','setattr','globals','locals','vars'}):
            raise Rejected('DYNAMIC_EXECUTION_NOT_ALLOWED')
        if isinstance(node, ast.Attribute) and (node.attr.startswith('__') or node.attr in {
            'disable','disabled','setLevel','basicConfig','dictConfig','addHandler','removeHandler','handlers','filters','addFilter','propagate',
            'sys','modules','settrace','setprofile','_getframe','f_globals','f_locals'}):
            raise Rejected('LOGGING_CONFIG_NOT_ALLOWED')


def report_gate(p, report, *, baseline=False):
    if report.get('error') == 'TIMEOUT':
        raise Rejected('VERIFICATION_TIMEOUT')
    if report.get('error') or report.get('collectionErrors'):
        raise Rejected('VERIFICATION_HARNESS_ERROR')
    if report.get('isolation') != 'DOCKER_NETWORK_NONE' or report.get('imageId') != p['runtime']['imageId']:
        raise Rejected('VERIFICATION_ENVIRONMENT')
    checks = report.get('checks', [])
    ids = [c.get('id') for c in checks]
    if sorted(ids) != p['inventory'] or len(set(ids)) != len(ids) or report.get('inventory') != p['inventory']:
        raise Rejected('TEST_INVENTORY_CHANGED')
    if report.get('inventoryDigest') != fingerprint(p['inventory']):
        raise Rejected('TEST_INVENTORY_CHANGED')
    statuses = {c['id']: c.get('status') for c in checks}
    if any(s not in {'PASS', 'FAIL', 'SKIP'} for s in statuses.values()) or report.get('exitCode') not in {0, 1}:
        raise Rejected('VERIFICATION_HARNESS_ERROR')
    skips = {k for k, v in statuses.items() if v == 'SKIP'}
    if not skips <= set(p['allowedSkips']):
        raise Rejected('REQUIRED_TEST_SKIPPED')
    failures = {k for k, v in statuses.items() if v == 'FAIL'}
    if baseline:
        if not failures & set(p['reproductionTests']):
            raise Rejected('VULNERABILITY_NOT_REPRODUCED')
        if not failures <= set(p['reproductionTests'] + p['relatedFailures']):
            raise Rejected('BASELINE_REGRESSION_FAILED')
        if report['exitCode'] != 1:
            raise Rejected('VERIFICATION_HARNESS_ERROR')
    elif failures or report['exitCode'] != 0:
        raise Rejected('TESTS_FAILED')
    return True
