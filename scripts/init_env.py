"""Generate local-only secrets without printing them. Existing secrets are preserved."""
from pathlib import Path
import secrets
p=Path(__file__).resolve().parents[1]/'.env'
if p.exists():print('Existing .env preserved')
else:
    values={'DATABASE_PASSWORD':secrets.token_urlsafe(32),'CSI_INTEGRATION_SECRET':secrets.token_urlsafe(48),'CSI_INTERNAL_TOKEN':secrets.token_urlsafe(48),'CSI_ADMIN_PASSWORD':secrets.token_urlsafe(18),'CSI_ADMIN_USERNAME':'reviewer','CSI_REPOSITORY_ALLOWLIST':'local/csi-demo','LLM_MODE':'disabled','LLM_API_KEY':'','LLM_BASE_URL':'','LLM_MODEL':''}
    fd=p.open('x');p.chmod(0o600);fd.write('\n'.join(f'{k}={v}' for k,v in values.items())+'\n');fd.close();print('Generated .env with restricted permissions; secrets not printed')
