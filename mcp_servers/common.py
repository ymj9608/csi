import hmac,os
from fastmcp.server.auth import TokenVerifier,AccessToken
class ServiceTokenVerifier(TokenVerifier):
    async def verify_token(self,token:str):
        expected=os.environ['CSI_INTERNAL_TOKEN']
        if len(expected)<32:raise RuntimeError('Invalid service token configuration')
        if hmac.compare_digest(token,expected):return AccessToken(token=token,client_id='csi-agent',scopes=['csi:internal'])
        return None
