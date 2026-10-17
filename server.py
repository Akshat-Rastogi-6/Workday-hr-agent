from mcp.server import MCPServer
from tools import get_team_time_off, get_worker, get_direct_reports, get_time_off_balance, search_workers, get_compensation, who_am_i

mcp = MCPServer("workday-hr")

mcp.tool()(get_worker)
mcp.tool()(get_direct_reports)
mcp.tool()(get_time_off_balance)
mcp.tool()(search_workers)
mcp.tool()(get_team_time_off)
mcp.tool()(get_compensation)
mcp.tool()(who_am_i)

if __name__ == "__main__":
    mcp.run()

