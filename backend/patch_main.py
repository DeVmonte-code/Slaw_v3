with open("src/swiss_legal_api/api/main.py", "r") as f:
    text = f.read()

# mcp.FastMCP.session_manager.run() in fastmcp 1.2+ is a bit finicky if re-entered. 
# We'll mock out this part for the tests or change the implementation. But actually, changing it to not re-use fmcp across multiple test starts. Wait, the global _MCP_MOUNTS has a fixed fmcp instance.
# Let's fix this in the test by making sure it doesn't fail if we run multiple tests. 

# wait, actually we can just recreate FastMCP instances by changing _MCP_MOUNTS to be a list of functions that return FastMCP? Or we can just ignore it for now.
