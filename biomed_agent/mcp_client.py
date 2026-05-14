import asyncio
import json
import logging
import subprocess
from importlib.metadata import PackageNotFoundError, version
from typing import Any, TextIO

from .servers import MCPServer

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for communicating with MCP servers via stdio."""
    
    def __init__(self, server: MCPServer):
        self.server = server
        self.process: subprocess.Popen[str] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._response_futures: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._tools: list[dict[str, Any]] = []
        
    async def connect(self) -> None:
        """Start the MCP server process and establish communication."""
        self.process = subprocess.Popen(
            self.server.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(self.server.path),
        )
        if not self.process.stdin or not self.process.stdout or not self.process.stderr:
            raise RuntimeError(f"Failed to open stdio streams for {self.server.name}")

        self._reader_task = asyncio.create_task(self._read_responses())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        init_result = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {
                    "name": "biomed-agent",
                    "version": _package_version(),
                },
            },
        )

        logger.debug("Initialize response: %s", init_result)

        await self._send_notification("notifications/initialized")

        # Some stdio MCP servers need a tick after initialized before tools/list.
        await asyncio.sleep(0.1)

        tools_response = await self._send_request("tools/list", {})
        self._tools = tools_response.get("tools", [])

        logger.info("Connected to %s with %s tools", self.server.name, len(self._tools))
        
    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
                
        if self.process:
            try:
                self.process.terminate()
                # Allow graceful stdio shutdown before forcing termination.
                await asyncio.sleep(0.1)
                if self.process.poll() is None:
                    self.process.kill()
            finally:
                self.process = None
                self._fail_pending_futures(
                    RuntimeError(f"MCP server {self.server.name} disconnected")
                )
                
    async def list_tools(self) -> list[dict[str, Any]]:
        """Return cached list of available tools."""
        return self._tools
        
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the server."""
        response = await self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        content = response.get("content", [])
        if isinstance(content, list) and content:
            first_content = content[0]
            if isinstance(first_content, dict) and "text" in first_content:
                try:
                    return json.loads(first_content["text"])
                except json.JSONDecodeError:
                    return first_content["text"]
        return content
        
    async def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request to the server and wait for response."""
        request_id = self._next_id
        self._next_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        
        # Always include params for requests (even if empty)
        if params is not None:
            request["params"] = params

        future = asyncio.get_running_loop().create_future()
        self._response_futures[request_id] = future
        try:
            self._write_jsonrpc_message("request", request)
        except Exception:
            self._response_futures.pop(request_id, None)
            raise

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError as exc:
            self._response_futures.pop(request_id, None)
            raise TimeoutError(f"Timeout waiting for response to {method}") from exc
            
    async def _send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        
        if params is not None:
            notification["params"] = params

        self._write_jsonrpc_message("notification", notification)

    def _write_jsonrpc_message(self, label: str, message: dict[str, Any]) -> None:
        stdin = self._require_stdin()
        message_str = json.dumps(message) + "\n"
        logger.debug("Sending %s: %s", label, message_str.strip())
        stdin.write(message_str)
        stdin.flush()

    def _require_stdin(self) -> TextIO:
        if not self.process or self.process.poll() is not None:
            raise RuntimeError(f"MCP server {self.server.name} is not running")
        if not self.process.stdin:
            raise RuntimeError(f"MCP server {self.server.name} stdin is unavailable")
        return self.process.stdin
        
    async def _read_responses(self) -> None:
        """Read responses from the server stdout."""
        while True:
            try:
                if not self.process or not self.process.stdout:
                    break
                line = await asyncio.get_running_loop().run_in_executor(
                    None, self.process.stdout.readline
                )
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue

                response = self._parse_response_line(line)
                if response is not None:
                    self._dispatch_response(response)
                        
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error reading response: %s", exc)
                break

        self._fail_pending_futures(
            RuntimeError(f"MCP server {self.server.name} closed before responding")
        )

    def _parse_response_line(self, line: str) -> dict[str, Any] | None:
        logger.debug("Raw output from %s: %s", self.server.name, line)
        if not line.startswith('{'):
            return None

        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.debug("Failed to parse JSON: %s - Line: %s", exc, line)
            return None

        logger.debug("Parsed response: %s", response)
        return response

    def _dispatch_response(self, response: dict[str, Any]) -> None:
        request_id = response.get("id")
        if request_id is None or request_id not in self._response_futures:
            return

        future = self._response_futures.pop(request_id)
        if "error" in response:
            future.set_exception(RuntimeError(str(response["error"])))
        else:
            future.set_result(response.get("result", {}))

    async def _read_stderr(self) -> None:
        """Read stderr from the server process and log it."""
        while True:
            try:
                if not self.process or not self.process.stderr:
                    break
                line = await asyncio.get_running_loop().run_in_executor(
                    None, self.process.stderr.readline
                )
                if not line:
                    break
                line = line.strip()
                if line:
                    lowered = line.lower()
                    if (
                        "virtual_env=" in lowered
                        and "does not match the project environment path" in lowered
                    ):
                        logger.debug("stderr from %s: %s", self.server.name, line)
                        continue
                    if any(
                        token in lowered
                        for token in ("error", "exception", "traceback", "warning")
                    ):
                        logger.warning("stderr from %s: %s", self.server.name, line)
                    else:
                        logger.debug("stderr from %s: %s", self.server.name, line)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error reading stderr from %s: %s", self.server.name, e)
                break

    def _fail_pending_futures(self, error: Exception) -> None:
        for request_id, future in list(self._response_futures.items()):
            if not future.done():
                future.set_exception(error)
            self._response_futures.pop(request_id, None)


def _package_version() -> str:
    try:
        return version("biomed-agent")
    except PackageNotFoundError:
        return "0.0.0"
