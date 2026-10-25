"""Register a locally preflighted profile, attach Worker validation, and activate it.

Uses CSI reviewer credentials and the internal Worker token from --env-file; never prints them.
The prepared artifact is produced by coding_agent.project_setup. No repository code is changed.
"""
import argparse
import json
from pathlib import Path
import httpx
from dotenv import dotenv_values
from coding_agent.worker import backend_url
from coding_agent.project_verification import fingerprint, validate_profile, report_gate
from coding_agent.project_lookup import login, resolve_project


def read_prepared(path):
    prepared=json.loads(Path(path).read_text(encoding='utf-8'))
    p=validate_profile(prepared['config'])
    if prepared['configDigest']!=fingerprint(p):
        raise ValueError('PROFILE_DIGEST_MISMATCH')
    report_gate(p,prepared['validation']['baseline'],baseline=True)
    return prepared


def activate_prepared(api, worker, project, prepared, *, preserve_active=False):
    """Reuse the same API gates for manual setup and approved local automation."""
    p=prepared['config']
    if preserve_active:
        response=api.get(f'/api/projects/{project}/coding-capabilities')
        response.raise_for_status()
        active=response.json().get('profile')
        if active:
            return {'status':'ACTIVE' if active['configDigest']==prepared['configDigest'] else 'EXISTING_PROFILE_PRESERVED',
                    'projectId':project,'version':active['version'],'changed':False}
    response=api.post(f'/api/projects/{project}/verification-profiles',json=p)
    response.raise_for_status()
    version=response.json()['version']
    response=worker.post(f'/internal/projects/{project}/verification-profiles/{version}/validate',json=prepared)
    response.raise_for_status()
    response=api.post(f'/api/projects/{project}/verification-profiles/{version}/activate')
    response.raise_for_status()
    return {'status':'ACTIVE','projectId':project,'version':version,'tests':len(p['inventory']),'changed':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',help='Optional UUID; otherwise resolve the prepared profile repository')
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--backend',default='http://127.0.0.1:8080')
    parser.add_argument('--env-file',type=Path,default=Path('.env'))
    args=parser.parse_args()
    prepared=read_prepared(args.prepared)
    p=prepared['config']
    cfg=dotenv_values(args.env_file)
    with httpx.Client(base_url=backend_url(args.backend),timeout=30,trust_env=False) as api:
        login(api, args.env_file)
        project=resolve_project(api, p['repository'], args.project)
        # Separate Worker client never shares the reviewer's session cookie.
        with httpx.Client(base_url=backend_url(args.backend),timeout=30,trust_env=False,
                          headers={'Authorization':'Bearer '+cfg['CSI_INTERNAL_TOKEN']}) as worker:
            result=activate_prepared(api, worker, project, prepared)
        print(json.dumps(result))


if __name__=='__main__':
    main()
