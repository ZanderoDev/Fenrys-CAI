from mcp.server.fastmcp import FastMCP

server = FastMCP("fenrys-test")


@server.tool(name="echo_text", description="Echo benign test text.")
def echo_text(text: str) -> str:
    return f"echo:{text}"


@server.tool(name="structured_echo", description="Return structured benign data.")
def structured_echo(text: str) -> dict[str, str]:
    return {"result": f"structured:{text}"}


if __name__ == "__main__":
    server.run()
