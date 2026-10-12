from mcp.server import MCPServer
from tools import run_tool, get_team_time_off, get_worker, get_direct_reports, get_time_off_balance, search_workers

mcp = MCPServer("workday-hr")

mcp.tool()(get_worker)
mcp.tool()(get_direct_reports)
mcp.tool()(get_time_off_balance)
mcp.tool()(search_workers)
mcp.tool()(get_team_time_off)

if __name__ == "__main__":
    mcp.run()

