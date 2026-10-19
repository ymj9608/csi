import os
from uuid import UUID
import httpx
from fastmcp import FastMCP
from .common import ServiceTokenVerifier
from .policy_review import compare_findings
mcp=FastMCP('CSI business-mcp',auth=ServiceTokenVerifier())
async def request(path,method='GET'):
    async with httpx.AsyncClient(base_url=os.environ.get('CSI_BACKEND_URL','http://127.0.0.1:8080'),timeout=12,headers={'Authorization':'Bearer '+os.environ['CSI_INTERNAL_TOKEN']}) as client:
        r=await client.request(method,'/internal'+path);r.raise_for_status();return r.json()
@mcp.tool()
async def get_scan_context(scan_id:str)->dict:
    """Validate immutable scan identity and persisted terminal status before analysis."""
    return await request(f'/scans/{UUID(scan_id)}')
@mcp.tool()
async def get_scan_findings(scan_id:str)->list:
    """Read immutable masked static evidence for one scan."""
    return await request(f'/scans/{UUID(scan_id)}/findings')
@mcp.tool()
async def get_privacy_policy(scan_id:str)->dict:
    """Read the policy version snapshotted at scan intake, not the latest policy."""
    return await request(f'/scans/{UUID(scan_id)}/policy')
@mcp.tool()
async def get_scan_history(scan_id:str)->list:
    """Read previous scans for policy drift comparison."""
    return await request(f'/scans/{UUID(scan_id)}/history')
@mcp.tool()
async def compare_policy_with_findings(scan_id:str)->dict:
    """Compare supported rule candidates with the actual project policy. Does not assert legal violations."""
    policy=await get_privacy_policy.fn(scan_id);findings=await get_scan_findings.fn(scan_id)
    return compare_findings(findings, policy)
@mcp.tool()
async def request_security_review(scan_id:str)->dict:
    """Create an idempotent approval request. This does not execute any remediation."""
    return await request(f'/scans/{UUID(scan_id)}/review-request','POST')
@mcp.tool()
async def create_security_issue(approval_id:str)->dict:
    """Create a CSI internal review issue only after backend verifies reviewer approval. No external messages."""
    return await request(f'/approvals/{UUID(approval_id)}/issue','POST')
if __name__=='__main__':mcp.run(transport='http',host=os.environ.get('MCP_HOST','0.0.0.0'),port=8001,show_banner=False)
