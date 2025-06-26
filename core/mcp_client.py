import asyncio
import json
import subprocess
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class MCPServer:
    """Configuration for an MCP server."""
    name: str
    path: Path
    command: List[str]
    description: str
    capabilities: List[str]

class MCPClient:
    """Client for communicating with MCP servers via stdio."""
    
    def __init__(self, server: MCPServer):
        self.server = server
        self.process: Optional[subprocess.Popen] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._response_futures: Dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._tools: List[Dict[str, Any]] = []
        
    async def connect(self):
        """Start the MCP server process and establish communication."""
        # Change to server directory for proper module resolution
        original_cwd = os.getcwd()
        os.chdir(self.server.path)
        
        try:
            self.process = subprocess.Popen(
                self.server.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            os.chdir(original_cwd)
            
            # Start reader task
            self._reader_task = asyncio.create_task(self._read_responses())
            
            # Step 1: Send initialize request
            init_result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "clientInfo": {
                    "name": "biomed-agent",
                    "version": "0.1.0"
                }
            })
            
            logger.debug(f"Initialize response: {init_result}")
            
            # Step 2: Send initialized notification (no ID for notifications)
            await self._send_notification("notifications/initialized")
            
            # Give server a moment to process the notification
            await asyncio.sleep(0.1)
            
            # Step 3: List available tools
            tools_response = await self._send_request("tools/list", {})
            self._tools = tools_response.get("tools", [])
            
            logger.info(f"Connected to {self.server.name} with {len(self._tools)} tools")
            
        except Exception as e:
            os.chdir(original_cwd)
            logger.error(f"Connection error: {e}")
            raise e
        
    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self._reader_task:
            self._reader_task.cancel()
            # Do not await the task here, as it can be on a different event loop
            # and cause the "Task attached to a different loop" error.
            # The cancellation will be processed by the task's event loop.
                
        if self.process:
            self.process.terminate()
            await asyncio.sleep(0.1)
            if self.process.poll() is None:
                self.process.kill()
                
    async def list_tools(self) -> List[Dict[str, Any]]:
        """Return cached list of available tools."""
        return self._tools
        
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the server."""
        response = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        # Extract content from response
        content = response.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            # MCP tools return content as an array of content items
            first_content = content[0]
            if isinstance(first_content, dict) and "text" in first_content:
                try:
                    # Try to parse as JSON
                    return json.loads(first_content["text"])
                except json.JSONDecodeError:
                    # Return as is if not JSON
                    return first_content["text"]
        return content
        
    async def _send_request(self, method: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Send a JSON-RPC request to the server and wait for response."""
        request_id = self._next_id
        self._next_id += 1
        
        # Build request
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }
        
        # Always include params for requests (even if empty)
        if params is not None:
            request["params"] = params
        
        # Create future for response
        future = asyncio.Future()
        self._response_futures[request_id] = future
        
        # Send request
        request_str = json.dumps(request) + "\n"
        logger.debug(f"Sending request: {request_str.strip()}")
        self.process.stdin.write(request_str)
        self.process.stdin.flush()
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            self._response_futures.pop(request_id, None)
            raise Exception(f"Timeout waiting for response to {method}")
            
    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Send a JSON-RPC notification (no response expected)."""
        # Build notification (no id field)
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        
        if params is not None:
            notification["params"] = params
        
        # Send notification
        notification_str = json.dumps(notification) + "\n"
        logger.debug(f"Sending notification: {notification_str.strip()}")
        self.process.stdin.write(notification_str)
        self.process.stdin.flush()
        
    async def _read_responses(self):
        """Read responses from the server stdout."""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self.process.stdout.readline
                )
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                    
                # Debug log raw output
                logger.debug(f"Raw output from {self.server.name}: {line}")
                
                # Skip non-JSON lines
                if not line.startswith('{'):
                    continue
                    
                try:
                    response = json.loads(line)
                    logger.debug(f"Parsed response: {response}")
                    
                    # Only process responses with an ID (not notifications)
                    request_id = response.get("id")
                    if request_id and request_id in self._response_futures:
                        future = self._response_futures.pop(request_id)
                        if "error" in response:
                            future.set_exception(Exception(response["error"]))
                        else:
                            future.set_result(response.get("result", {}))
                except json.JSONDecodeError as e:
                    logger.debug(f"Failed to parse JSON: {e} - Line: {line}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading response: {e}")