"""Trusted verifier entrypoint; no application secrets or network are available."""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from contract import SECURITY_TESTS, SUITE_VERSION

os.environ.update(TEST_DATABASE_URL='sqlite://', DATABASE_URL='sqlite://',
                  JWT_SECRET='isolated-csi-coding-test-secret-only', CSI_LAB_MODE='false',
                  HOME='/tmp', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
    '--junitxml=/tmp/report.xml', 'tests'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=80)
report = {'exitCode':result.returncode,'passed':0,'failed':0,'skipped':0,'securityPassed':0,'failedTests':[],
          'suiteVersion':SUITE_VERSION,'securityTotal':len(SECURITY_TESTS),'securityChecks':[], 'skippedTests':[]}
try:
    for case in ET.parse('/tmp/report.xml').getroot().iter('testcase'):
        failed = case.find('failure') is not None or case.find('error') is not None
        skipped = case.find('skipped') is not None
        if failed:
            report['failed'] += 1
            report['failedTests'].append(case.get('name','unknown')[:160])
        elif skipped:
            report['skipped'] += 1
            report['skippedTests'].append(case.get('name','unknown')[:160])
        else:
            report['passed'] += 1
            if 'test_csi_coding_security' in case.get('classname',''):
                report['securityPassed'] += 1
        if case.get('classname','').split('.')[-1] == 'test_csi_coding_security':
            report['securityChecks'].append({'id':case.get('name','unknown')[:160],
                'status':'FAILED' if failed else 'SKIPPED' if skipped else 'PASSED'})
except (OSError, ET.ParseError):
    report['failedTests'] = ['TEST_COLLECTION_OR_RUNTIME_ERROR']
print('CSI_VERIFICATION_JSON='+json.dumps(report))
