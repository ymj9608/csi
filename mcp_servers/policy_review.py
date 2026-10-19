"""Deterministic field comparison shared by MCP and report construction."""
import re

FIELDS = {'name', 'full_name', 'phone_number', 'resident_registration_no', 'date_of_birth', 'home_address'}

def normalize(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())

def compare_finding(finding, policy):
    context = finding.get('codeContext') or {}
    field = context.get('field')
    if field not in FIELDS:
        match = re.match(r'\s*([A-Za-z_]+)\s*:', finding.get('maskedCodeEvidence', ''))
        field = match.group(1) if match and match.group(1) in FIELDS else None
    approved = {normalize(x) for x in policy.get('approvedFields', [])}
    restricted = {normalize(x) for x in policy.get('restrictedFields', [])}
    status = ('UNKNOWN' if not field or not policy.get('approvedFields') else
              'RESTRICTED' if normalize(field) in restricted else
              'LISTED' if normalize(field) in approved else 'NOT_LISTED')
    return {'findingId': finding['id'], 'field': field, 'entity': context.get('entity', 'UNKNOWN'),
            'inventoryStatus': status, 'policyVersion': policy.get('version', 'UNKNOWN'),
            'section': policy.get('inventorySection'), 'page': policy.get('inventoryPage'),
            'approvalRecord': 'NOT_CHECKED', 'runtimeVerified': False,
            'signals': context.get('signals', []), 'declarationKind': context.get('declarationKind', 'UNKNOWN')}

def compare_findings(findings, policy):
    return {'policyVersion': policy.get('version', 'UNKNOWN'),
            'items': [compare_finding(f, policy) for f in findings if f['ruleId'] == 'POL-01'],
            'requiresHumanReview': bool(findings),
            'limitations': ['Static observations only', 'Separate approval records not checked', 'Fictional training policy']}
