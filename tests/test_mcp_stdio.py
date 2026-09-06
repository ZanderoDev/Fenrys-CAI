import sys

from fenrys.integrations.mcp import StdioMCPClient


async def test_stdio_mcp_transport(tmp_path):
    server = tmp_path / "fake_mcp.py"
    server.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "  req=json.loads(line)\n"
        "  if 'id' not in req: continue\n"
        "  method=req['method']\n"
        "  if method == 'tools/list': result={'tools':[{'name':'nmap_scan'}]}\n"
        "  elif method == 'tools/call': result={'content':'port 80 open'}\n"
        "  else: result={'protocolVersion':'2024-11-05'}\n"
        "  print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}), flush=True)\n",
        encoding="utf-8",
    )
    client = StdioMCPClient([sys.executable, str(server)])
    assert (await client.list_tools())[0]["name"] == "nmap_scan"
    assert (await client.call_tool("nmap_scan", {"target": "challenge.local"}))["content"] == "port 80 open"
    await client.close()