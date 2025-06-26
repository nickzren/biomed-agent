import os
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
from dotenv import load_dotenv
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .mcp_client import MCPClient, MCPServer

load_dotenv()
logger = logging.getLogger(__name__)

# MCP Server configurations with comprehensive capabilities
MCP_SERVERS = {
    "opentargets": {
        "description": "Open Targets Platform - comprehensive drug target, disease, and evidence data",
        "capabilities": [
            "targets", "diseases", "drugs", "evidence", "variants", "studies",
            "genetic_associations", "pathways", "expression", "protein_interactions",
            "tractability", "safety", "mouse_phenotypes", "chemical_probes",
            "literature", "clinical_trials", "biomarkers"
        ],
        "module": "opentargets_mcp.server"
    },
    "monarch": {
        "description": "Monarch Initiative - phenotype associations, disease models, and semantic similarity",
        "capabilities": [
            "phenotypes", "diseases", "genes", "genotype_phenotype",
            "disease_phenotype", "gene_phenotype", "model_organisms",
            "semantic_similarity", "hpo_terms", "disease_models"
        ],
        "module": "monarch_mcp.server"
    },
    "mychem": {
        "description": "MyChem.info - comprehensive chemical and drug information",
        "capabilities": [
            "chemicals", "drugs", "compounds", "structures", "identifiers",
            "drugbank", "chembl", "pubchem", "pharmgkb", "drug_interactions",
            "mechanisms", "targets", "indications", "side_effects"
        ],
        "module": "mychem_mcp.server"
    },
    "mydisease": {
        "description": "MyDisease.info - disease annotations from multiple sources",
        "capabilities": [
            "diseases", "symptoms", "phenotypes", "genetics", "drugs",
            "mondo", "omim", "orphanet", "mesh", "umls", "hpo",
            "disgenet", "ctd", "clinical_trials"
        ],
        "module": "mydisease_mcp.server"
    },
    "mygene": {
        "description": "MyGene.info - gene annotation data aggregator",
        "capabilities": [
            "genes", "transcripts", "proteins", "variants", "homologs",
            "pathways", "interactions", "expression", "ontology",
            "entrez", "ensembl", "uniprot", "refseq", "go_terms"
        ],
        "module": "mygene_mcp.server"
    }
}

class BiomedAgent:
    """Main agent that orchestrates MCP servers and provides LLM reasoning."""
    
    def __init__(self, servers: Optional[List[str]] = None):
        """Initialize the agent with specified servers."""
        self.servers = servers
        self.clients: Dict[str, MCPClient] = {}
        self.tools_registry: Dict[str, Dict[str, Any]] = {}
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
    async def connect(self):
        """Connect to all configured MCP servers."""
        tasks = []
        
        for server_name in self.servers:
            if server_name in MCP_SERVERS:
                # Get server path from environment or use relative path
                env_var = f"{server_name.upper()}_MCP_PATH"
                server_path = Path(os.getenv(env_var, f"../{server_name}-mcp"))
                
                if not server_path.exists():
                    logger.warning(f"Server path not found: {server_path}")
                    continue
                    
                server_config = MCP_SERVERS[server_name]
                server = MCPServer(
                    name=server_name,
                    path=server_path,
                    command=["uv", "run", "python", "-m", server_config["module"]],
                    description=server_config["description"],
                    capabilities=server_config["capabilities"]
                )
                
                client = MCPClient(server)
                self.clients[server_name] = client
                tasks.append(self._connect_and_register(server_name, client))
                
        await asyncio.gather(*tasks)
        logger.info(f"Connected to {len(self.clients)} MCP servers")
        
    async def _connect_and_register(self, server_name: str, client: MCPClient):
        """Connect to a server and register its tools."""
        try:
            await client.connect()
            tools = await client.list_tools()
            
            for tool in tools:
                tool_id = f"{server_name}.{tool['name']}"
                self.tools_registry[tool_id] = {
                    "server": server_name,
                    "tool": tool,
                    "client": client
                }
                
            logger.info(f"Registered {len(tools)} tools from {server_name}")
            
        except Exception as e:
            logger.error(f"Failed to connect to {server_name}: {e}")
            
    async def disconnect(self):
        """Disconnect from all MCP servers."""
        tasks = [client.disconnect() for client in self.clients.values()]
        await asyncio.gather(*tasks)
        
    async def call_tool(self, tool_id: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool by its full ID (server.tool_name)."""
        if tool_id not in self.tools_registry:
            raise ValueError(f"Unknown tool: {tool_id}")
            
        tool_info = self.tools_registry[tool_id]
        client = tool_info["client"]
        tool_name = tool_info["tool"]["name"]
        
        return await client.call_tool(tool_name, arguments)
        
    def list_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all available tools grouped by server."""
        tools_by_server = {}
        
        for tool_id, info in self.tools_registry.items():
            server = info["server"]
            if server not in tools_by_server:
                tools_by_server[server] = []
            tools_by_server[server].append({
                "id": tool_id,
                "name": info["tool"]["name"],
                "description": info["tool"].get("description", "")
            })
            
        return tools_by_server
        
    def find_tools_by_capability(self, capability: str) -> List[str]:
        """Find tools that match a capability keyword."""
        matching_tools = []
        capability_lower = capability.lower()
        
        # Check tool descriptions
        for tool_id, info in self.tools_registry.items():
            tool_desc = info["tool"].get("description", "").lower()
            tool_name = info["tool"]["name"].lower()
            
            if capability_lower in tool_desc or capability_lower in tool_name:
                matching_tools.append(tool_id)
                continue
                
            # Also check server capabilities
            server_name = info["server"]
            if server_name in MCP_SERVERS:
                server_caps = MCP_SERVERS[server_name]["capabilities"]
                if any(capability_lower in cap.lower() for cap in server_caps):
                    matching_tools.append(tool_id)
                    
        return list(set(matching_tools))  # Remove duplicates
        
    async def reason_and_act(self, query: str, max_steps: int = 10) -> Dict[str, Any]:
        """Use LLM to reason about the query and decide which tools to use."""
        # Get available tools with full parameter info
        tools_description = self._format_tools_for_llm_detailed()
        
        system_prompt = f"""You are a biomedical research assistant with access to multiple specialized databases.

Available tools with their exact parameters:
{tools_description}

Important guidelines:
1. Use the EXACT tool names and parameter names as shown above
2. For drug queries: First search by name to get ChEMBL ID, then use that ID for detailed info
3. Pay attention to required vs optional parameters
4. Common ID formats:
   - ChEMBL IDs: CHEMBLXXXXXX (e.g., CHEMBL1229517)
   - Ensembl IDs: ENSGXXXXXXXXXX (e.g., ENSG00000157764)
   - EFO IDs: EFO_XXXXXXX (e.g., EFO_0000270)

You must respond in valid JSON format:
{{
  "thought": "your reasoning",
  "action": {{
    "tool": "server.tool_name",
    "arguments": {{"param_name": "value"}}
  }},
  "is_final": false
}}

Or for final answer:
{{
  "thought": "your reasoning",
  "answer": "your final answer",
  "is_final": true
}}
"""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]
        
        steps = []
        
        for step in range(max_steps):
            try:
                # Get LLM response
                response = await self.llm.ainvoke(messages)
                content = response.content
                
                # Parse response
                try:
                    # Find JSON in the response
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = content[json_start:json_end]
                        action_dict = json.loads(json_str)
                    else:
                        raise ValueError("No JSON found in response")
                except Exception as e:
                    logger.error(f"Failed to parse JSON: {e}, Content: {content}")
                    action_dict = {
                        "thought": "Failed to parse response", 
                        "is_final": True, 
                        "answer": "I apologize, I had trouble processing the response. Please try again."
                    }
                    
                steps.append(action_dict)
                
                if action_dict.get("is_final", False):
                    return {
                        "query": query,
                        "answer": action_dict.get("answer", ""),
                        "steps": steps
                    }
                    
                # Execute tool call
                if "action" in action_dict and action_dict["action"]:
                    action = action_dict["action"]
                    if "tool" in action and "arguments" in action:
                        tool_id = action["tool"]
                        arguments = action["arguments"]
                        
                        try:
                            result = await self.call_tool(tool_id, arguments)
                            observation = {"tool": tool_id, "result": result}
                        except Exception as e:
                            observation = {"tool": tool_id, "error": str(e)}
                            
                        steps.append({"observation": observation})
                        
                        # Add to conversation
                        messages.append(AIMessage(content=json.dumps(action_dict)))
                        messages.append(HumanMessage(content=f"Observation: {json.dumps(observation)}"))
                    else:
                        # Invalid action format
                        error_msg = "Invalid action format. Expected {\"tool\": \"...\", \"arguments\": {...}}"
                        steps.append({"observation": {"error": error_msg}})
                        messages.append(AIMessage(content=json.dumps(action_dict)))
                        messages.append(HumanMessage(content=f"Error: {error_msg}. Please use the correct format."))
                    
            except Exception as e:
                logger.error(f"Error in reasoning step: {e}")
                return {
                    "query": query,
                    "answer": f"Error during processing: {str(e)}",
                    "steps": steps
                }
                
        return {
            "query": query,
            "answer": "Reached maximum steps without final answer",
            "steps": steps
        }
        
    def _format_tools_for_llm(self, tools: Dict[str, List[Dict[str, Any]]]) -> str:
        """Format tools list for LLM consumption."""
        formatted = []
        for server, server_tools in tools.items():
            formatted.append(f"\n{server}:")
            for tool in server_tools:
                formatted.append(f"  - {tool['id']}: {tool['description']}")
        return "\n".join(formatted)
    
    def _format_tools_for_llm_detailed(self) -> str:
        """Format tools with complete parameter information for LLM."""
        formatted = []
        
        # Group tools by server
        tools_by_server = {}
        for tool_id, info in self.tools_registry.items():
            server = info["server"]
            if server not in tools_by_server:
                tools_by_server[server] = []
            tools_by_server[server].append((tool_id, info["tool"]))
        
        # Format each server's tools
        for server, tools in tools_by_server.items():
            formatted.append(f"\n{server} tools:")
            
            for tool_id, tool_info in tools:
                formatted.append(f"\n  {tool_id}:")
                formatted.append(f"    Description: {tool_info.get('description', 'N/A')}")
                
                # Add parameter details
                if 'inputSchema' in tool_info:
                    schema = tool_info['inputSchema']
                    if 'properties' in schema:
                        formatted.append("    Parameters:")
                        
                        # Required parameters first
                        required = schema.get('required', [])
                        for param_name, param_info in schema['properties'].items():
                            param_type = param_info.get('type', 'string')
                            param_desc = param_info.get('description', 'No description')
                            is_required = param_name in required
                            
                            if is_required:
                                formatted.append(f"      - {param_name} ({param_type}, REQUIRED): {param_desc}")
                        
                        # Optional parameters
                        for param_name, param_info in schema['properties'].items():
                            if param_name not in required:
                                param_type = param_info.get('type', 'string')
                                param_desc = param_info.get('description', 'No description')
                                default = param_info.get('default', 'N/A')
                                formatted.append(f"      - {param_name} ({param_type}, optional, default: {default}): {param_desc}")
                                
        return "\n".join(formatted)