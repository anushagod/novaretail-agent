import sys
from pathlib import Path

# Ensure the project root is in sys.path for `mcp dev`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer

from mcp_server.tools.customer import get_customer
from mcp_server.tools.escalation import escalate_to_human
from mcp_server.tools.orders import lookup_order
from mcp_server.tools.policy_rag import search_policy
from mcp_server.tools.refunds import process_refund

mcp = MCPServer("NovaRetail-Support-Server")

# Register all 5 modular tools
mcp.tool()(search_policy)
mcp.tool()(get_customer)
mcp.tool()(lookup_order)
mcp.tool()(process_refund)
mcp.tool()(escalate_to_human)

if __name__ == "__main__":
   mcp.run()

