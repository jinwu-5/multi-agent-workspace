import asyncio
import json
import os
from typing import Dict

class MCPConnectionManager:
    """Manages MCP server connections"""
    
    def __init__(self):
        self.connections: Dict[str, Dict] = {}
        self.request_ids: Dict[str, int] = {}
        self.base_paths: Dict[str, str] = {}
    
    async def start_azure_devops_mcp(self, org_url: str, pat: str, project: str) -> bool:
        """Start Azure DevOps MCP server"""
        print("Starting Azure DevOps MCP server...")
        
        env_vars = {
            **os.environ,
            "AZURE_DEVOPS_ORG_URL": org_url,
            "AZURE_DEVOPS_AUTH_METHOD": "pat",
            "AZURE_DEVOPS_PAT": pat,
            "AZURE_DEVOPS_DEFAULT_PROJECT": project
        }
        
        process = await asyncio.create_subprocess_exec(
            "npx", "-y", "@tiberriver256/mcp-server-azure-devops",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_vars
        )
        
        self.connections["azure_devops"] = {
            "process": process,
            "stdin": process.stdin,
            "stdout": process.stdout
        }
        self.request_ids["azure_devops"] = 1
        
        await self._init_mcp("azure_devops")
        print("✓ Azure DevOps MCP ready")
        return True
    
    async def start_filesystem_mcp(self, base_path: str) -> bool:
        """Start Filesystem MCP server"""
        print(f"Starting Filesystem MCP server for: {base_path}")
        
        try:
            # Make sure path exists and is absolute
            abs_base_path = os.path.abspath(base_path)
            
            if not os.path.exists(abs_base_path):
                print(f"✗ Path does not exist: {abs_base_path}")
                return False
            
            process = await asyncio.create_subprocess_exec(
                "npx", "-y", "@modelcontextprotocol/server-filesystem", abs_base_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self.connections["filesystem"] = {
                "process": process,
                "stdin": process.stdin,
                "stdout": process.stdout
            }
            self.request_ids["filesystem"] = 1
            self.base_paths["filesystem"] = abs_base_path
            
            await self._init_mcp("filesystem")
            print(f"✓ Filesystem MCP ready (base: {abs_base_path})")
            return True
        except Exception as e:
            print(f"✗ Filesystem MCP failed: {e}")
            return False
    
    async def _init_mcp(self, connection_name: str):
        """Initialize MCP connection"""
        init_request = {
            "jsonrpc": "2.0",
            "id": self.request_ids[connection_name],
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": f"{connection_name}-agent", "version": "1.0.0"}
            }
        }
        
        await self._send_message(connection_name, init_request)
        await self._read_message(connection_name)
        
        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        await self._send_message(connection_name, initialized)
        self.request_ids[connection_name] += 1
    
    async def _send_message(self, connection_name: str, message: Dict):
        """Send message to MCP server"""
        conn = self.connections[connection_name]
        message_str = json.dumps(message) + "\n"
        conn["stdin"].write(message_str.encode())
        await conn["stdin"].drain()
    
    async def _read_message(self, connection_name: str) -> Dict:
        """Read message from MCP server"""
        conn = self.connections[connection_name]
        line = await conn["stdout"].readline()
        return json.loads(line.decode().strip())
    
    async def call_tool(self, connection_name: str, tool_name: str, arguments: Dict) -> Dict:
        """Call an MCP tool"""
        request = {
            "jsonrpc": "2.0",
            "id": self.request_ids[connection_name],
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        
        await self._send_message(connection_name, request)
        response = await self._read_message(connection_name)
        self.request_ids[connection_name] += 1
        return response
    
    async def cleanup(self):
        """Clean up all MCP connections"""
        for conn in self.connections.values():
            if conn["process"]:
                conn["process"].terminate()
                await conn["process"].wait()
