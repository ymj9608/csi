"""Operator preflight: pin an image, driver, pack and full test inventory before activation.

python -m coding_agent.project_setup --repo PATH --commit SHA --config draft.json --output prepared.json
Uses Docker only; does not call models, modify the target repository, or activate a profile.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
import httpx
from .project_adapter import verify
from .project_verification import ADAPTER, ROOT, PACK, validate_profile, export_snapshot, fingerprint, report_gate, safe_path
from .repository import commit, digest, Rejected


def capabilities(url):
    images, models = [], []
    try:
        result = subprocess.run(['docker','image','ls','--no-trunc','--quiet'], capture_output=True, text=True, timeout=10, check=True)
        subprocess.run(['docker','info','--format','{{.ServerVersion}}'], capture_output=True, timeout=10, check=True)
        images = sorted(set(result.stdout.split()))
        with httpx.Client(timeout=5, trust_env=False) as client:
            response = client.get(url.rstrip('/')+'/api/tags')
            response.raise_for_status()
            models = [m['name'] for m in response.json()['models']]
    except (OSError, subprocess.SubprocessError, httpx.HTTPError, ValueError, KeyError):
        pass
    return {'adapters':[ADAPTER], 'imageIds':images, 'models':models}


def prepare(repo, sha, draft, image='csi-project-verifier:v1'):
    p = json.loads(json.dumps(draft))
    inspected = subprocess.run(['docker','image','inspect','--format','{{.Id}}',image],capture_output=True,text=True,timeout=10,check=True)
    p['runtime']['imageId'] = inspected.stdout.strip()
    p['pack'] = {'id':PACK,'sha256':digest((ROOT/'verification/privacy_pack.py').read_text(encoding='utf-8'))}
    driver_path = safe_path(p['driver']['path'])
    if not driver_path.startswith('project_profiles/') or not driver_path.endswith('/driver.py'):
        raise Rejected('PROFILE_DRIVER')
    p['driver']['sha256'] = digest((ROOT/driver_path).read_text(encoding='utf-8'))
    validate_profile(p, prepared=False)
    sha = commit(repo, sha)
    with tempfile.TemporaryDirectory(prefix='csi-profile-preflight-') as directory:
        tree = Path(directory)
        manifest = export_snapshot(repo, sha, tree, p)
        report = verify(tree, p)
    p['inventory'] = report['inventory']
    validate_profile(p)
    report_gate(p, report, baseline=True)
    return {'config':p,'configDigest':fingerprint(p),'validation':{'commitSha':sha,
            'sourceManifest':manifest,'sourceManifestDigest':fingerprint(manifest),'baseline':report}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', default='csi-project-verifier:v1')
    args = parser.parse_args()
    prepared = prepare(args.repo, args.commit, json.loads(args.config.read_text(encoding='utf-8')), args.image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(prepared,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'VALIDATED','testCount':len(prepared['config']['inventory']), 'output':str(args.output)}))


if __name__ == '__main__':
    main()
