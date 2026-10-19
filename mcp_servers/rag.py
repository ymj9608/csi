import os
from fastmcp import FastMCP
from .common import ServiceTokenVerifier
from .vector import search,RULE_SECTIONS
mcp=FastMCP('CSI rag-mcp',auth=ServiceTokenVerifier())
@mcp.tool()
def search_security_guidelines(rule_id:str,query:str)->list:
    """Search actual supplied external-reference PDF chunks. Returns original metadata and content."""
    return search(rule_id,False,query[:500])
@mcp.tool()
def search_internal_privacy_policy(rule_id:str,query:str)->list:
    """Search fictional internal policy, distinguished from official legal source material."""
    return search(rule_id,True,query[:500])
@mcp.tool()
def get_guideline_details(rule_id:str)->dict:
    """Fetch policy and reference evidence for a supported scanner rule."""
    return {'ruleId':rule_id,'internal':search(rule_id,True,rule_id),'external':search(rule_id,False,rule_id)}
@mcp.resource('security://guidelines/{rule_id}')
def guidelines(rule_id:str)->dict:
    """Read-only guideline resource with actual document/page locations."""
    return {'ruleId':rule_id,'sections':RULE_SECTIONS[rule_id],'evidence':search(rule_id,False,rule_id)}
if __name__=='__main__':mcp.run(transport='http',host=os.environ.get('MCP_HOST','0.0.0.0'),port=8002,show_banner=False)
