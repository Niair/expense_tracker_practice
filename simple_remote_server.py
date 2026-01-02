import random
from fastmcp import FastMCP
import random
import json

# Create a FastMCP server instance
mcp = FastMCP(name="Simple Calculate Server")

@mcp.tool
def random_number(min_val: int = 1, max_val: int = 100) -> int:
    """Generate the random number within the given range.
    
    Args : 
      min_val : Minimum Value (default 1)
      max_val : Maximum Value (default 1)

    Returns : 
      A random integer between the min_val and max_val
      """
    return random.randint(min_val, max_val)

@mcp.tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together.
    
      Args : 
            a : First number
            b : Second number
      
      Returns : 
            The sum of a and b
      """
    return a + b

@mcp.resource("info://server")
def server_info() -> str:
    """
    Get information about this server
    """
    info = {
        "name" : "Simple Calculator Server",
        "version" : "1.0.0",
        "description" : "A basic MCP server with math tools",
        "tools" : ["add", "random_number"],
        "author" : "Nihal"
    }
    return json.dumps(info, indent = 2)

if __name__ == "__main__":
    mcp.run(transport = "http", host = "0.0.0.0", port = 8000)
    # transport set to http

    # in local case we used | mcp.run() | which trigers the STDio as transport