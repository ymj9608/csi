"""Preserve complete pytest node IDs (path, class, name and parameter identity)."""
import json
from pathlib import Path

inventory = []
results = {}
collection_errors = []


def pytest_collection_finish(session):
    inventory.extend(item.nodeid for item in session.items)


def pytest_collectreport(report):
    if report.failed:
        collection_errors.append(report.nodeid)


def pytest_runtest_logreport(report):
    state = results.setdefault(report.nodeid, 'ERROR')
    if report.failed:
        results[report.nodeid] = 'FAIL' if report.when == 'call' else 'ERROR'
    elif report.skipped and state not in {'FAIL'}:
        results[report.nodeid] = 'SKIP'
    elif report.when == 'call' and state not in {'FAIL', 'SKIP'}:
        results[report.nodeid] = 'PASS'


def pytest_sessionfinish(session, exitstatus):
    Path('/tmp/csi-results.json').write_text(json.dumps({
        'inventory': sorted(inventory), 'collectionErrors': collection_errors,
        'checks': [{'id': key, 'status': results.get(key, 'ERROR')} for key in sorted(inventory)]}))
