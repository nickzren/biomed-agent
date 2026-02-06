import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

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

MAX_TOOL_OBSERVATION_CHARS = 8000
MAX_CITATIONS = 8
CONFIDENCE_LEVELS = {"low", "medium", "high"}
HIGH_RISK_MEDICAL_PATTERN = re.compile(
    r"\b("
    r"diagnos(?:e|is|ing)|"
    r"treat(?:ment|ing)?|"
    r"prescrib(?:e|ing)|"
    r"dose|dosage|"
    r"what should i take|"
    r"should i take|"
    r"medical advice|"
    r"my symptoms|"
    r"for me personally|"
    r"should i stop"
    r")\b",
    flags=re.IGNORECASE,
)


class BiomedAgent:
    """Main agent that orchestrates MCP servers and provides LLM reasoning."""

    def __init__(self, servers: Optional[List[str]] = None):
        """Initialize the agent with specified servers."""
        self.servers = servers if servers else list(MCP_SERVERS.keys())
        self.clients: Dict[str, MCPClient] = {}
        self.tools_registry: Dict[str, Dict[str, Any]] = {}
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.llm: Optional[ChatOpenAI] = None

    def _get_llm(self) -> ChatOpenAI:
        if self.llm is None:
            if not self.api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Configure it in your environment or .env file."
                )
            llm_kwargs: Dict[str, Any] = {
                "model": self.model,
                "api_key": self.api_key,
            }
            temperature_raw = os.getenv("OPENAI_TEMPERATURE")
            if temperature_raw is not None:
                try:
                    llm_kwargs["temperature"] = float(temperature_raw)
                except ValueError:
                    logger.warning(
                        "Invalid OPENAI_TEMPERATURE value '%s'; ignoring.",
                        temperature_raw,
                    )
            self.llm = ChatOpenAI(
                **llm_kwargs,
            )
        return self.llm

    async def connect(self):
        """Connect to all configured MCP servers."""
        if not self.servers:
            raise ValueError("No MCP servers were selected.")

        self.clients = {}
        self.tools_registry = {}
        tasks = []

        unknown_servers = [name for name in self.servers if name not in MCP_SERVERS]
        for unknown in unknown_servers:
            logger.warning("Unknown server requested: %s", unknown)

        for server_name in self.servers:
            if server_name not in MCP_SERVERS:
                continue

            env_var = f"{server_name.upper()}_MCP_PATH"
            server_path = Path(os.getenv(env_var, f"../{server_name}-mcp")).expanduser()

            if not server_path.exists():
                logger.warning("Server path not found for %s: %s", server_name, server_path)
                continue

            server_config = MCP_SERVERS[server_name]
            server = MCPServer(
                name=server_name,
                path=server_path,
                command=["uv", "run", "python", "-m", server_config["module"]],
                description=server_config["description"],
                capabilities=server_config["capabilities"],
            )

            client = MCPClient(server)
            self.clients[server_name] = client
            tasks.append(self._connect_and_register(server_name, client))

        if not tasks:
            raise RuntimeError(
                "No MCP servers were connectable. Check server names and *_MCP_PATH values."
            )

        results = await asyncio.gather(*tasks)
        connected_count = sum(1 for connected in results if connected)
        if connected_count == 0:
            raise RuntimeError("Failed to connect to all requested MCP servers.")

        logger.info("Connected to %s MCP servers", connected_count)

    async def _connect_and_register(self, server_name: str, client: MCPClient) -> bool:
        """Connect to a server and register its tools."""
        try:
            await client.connect()
            tools = await client.list_tools()

            for tool in tools:
                tool_name = tool.get("name")
                if not tool_name:
                    continue
                tool_id = f"{server_name}.{tool_name}"
                self.tools_registry[tool_id] = {
                    "server": server_name,
                    "tool": tool,
                    "client": client,
                }

            logger.info("Registered %s tools from %s", len(tools), server_name)
            return True
        except Exception as e:
            logger.error("Failed to connect to %s: %s", server_name, e)
            self.clients.pop(server_name, None)
            return False

    async def disconnect(self):
        """Disconnect from all MCP servers."""
        if not self.clients:
            return

        tasks = [client.disconnect() for client in self.clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.clients = {}
        self.tools_registry = {}

    async def call_tool(self, tool_id: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool by its full ID (server.tool_name)."""
        if tool_id not in self.tools_registry:
            raise ValueError(f"Unknown tool: {tool_id}")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object.")

        tool_info = self.tools_registry[tool_id]
        client = tool_info["client"]
        tool_name = tool_info["tool"]["name"]
        return await client.call_tool(tool_name, arguments)

    def list_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all available tools grouped by server."""
        tools_by_server: Dict[str, List[Dict[str, Any]]] = {}

        for tool_id, info in self.tools_registry.items():
            server = info["server"]
            if server not in tools_by_server:
                tools_by_server[server] = []
            tools_by_server[server].append(
                {
                    "id": tool_id,
                    "name": info["tool"]["name"],
                    "description": info["tool"].get("description", ""),
                }
            )

        for server in tools_by_server:
            tools_by_server[server].sort(key=lambda item: item["id"])
        return tools_by_server

    def find_tools_by_capability(self, capability: str) -> List[str]:
        """Find tools that match a capability keyword."""
        matching_tools = []
        capability_lower = capability.lower()

        for tool_id, info in self.tools_registry.items():
            tool_desc = info["tool"].get("description", "").lower()
            tool_name = info["tool"]["name"].lower()

            if capability_lower in tool_desc or capability_lower in tool_name:
                matching_tools.append(tool_id)
                continue

            server_name = info["server"]
            server_caps = MCP_SERVERS.get(server_name, {}).get("capabilities", [])
            if any(capability_lower in cap.lower() for cap in server_caps):
                matching_tools.append(tool_id)

        return sorted(set(matching_tools))

    async def reason_and_act(self, query: str, max_steps: int = 10) -> Dict[str, Any]:
        """Use LLM to reason about the query and decide which tools to use."""
        if not query or not query.strip():
            return {
                "query": query,
                "answer": "Please provide a biomedical question.",
                "confidence": "low",
                "citations": [],
                "limitations": ["No query was provided."],
                "steps": [],
            }

        if not self.tools_registry:
            raise RuntimeError("No tools are available. Connect to MCP servers before querying.")

        high_risk_query = self._is_high_risk_medical_query(query)
        safety_note = None
        if high_risk_query:
            safety_note = (
                "This assistant provides general biomedical information only and cannot "
                "provide personalized diagnosis or treatment advice."
            )

        tools_description = self._format_tools_for_llm_detailed()
        system_prompt = self._build_system_prompt(tools_description, high_risk_query)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query),
        ]
        steps: List[Dict[str, Any]] = []
        observations: List[Dict[str, Any]] = []

        for _ in range(max_steps):
            try:
                response = await self._get_llm().ainvoke(messages)
                action_dict = self._parse_llm_json(response.content)
                steps.append(action_dict)

                if action_dict.get("is_final", False):
                    return self._build_final_response(
                        query=query,
                        final_step=action_dict,
                        steps=steps,
                        observations=observations,
                        safety_note=safety_note,
                    )

                action = action_dict.get("action")
                observation = await self._execute_action(action, observations)
                steps.append({"observation": observation})

                messages.append(AIMessage(content=json.dumps(action_dict, ensure_ascii=False)))
                messages.append(
                    HumanMessage(
                        content=(
                            "Observation: "
                            + json.dumps(
                                self._observation_for_prompt(observation),
                                ensure_ascii=False,
                            )
                        )
                    )
                )
            except Exception as e:
                logger.error("Error in reasoning step: %s", e)
                limitations = self._merge_safety_note(
                    ["The reasoning loop failed before completion."],
                    safety_note,
                )
                return {
                    "query": query,
                    "answer": f"Error during processing: {str(e)}",
                    "confidence": "low",
                    "citations": self._default_citations(observations),
                    "limitations": limitations,
                    "steps": steps,
                    "safety_note": safety_note,
                }

        limitations = self._merge_safety_note(
            ["The agent exhausted the configured step budget."],
            safety_note,
        )
        return {
            "query": query,
            "answer": "Reached maximum steps without final answer.",
            "confidence": "low",
            "citations": self._default_citations(observations),
            "limitations": limitations,
            "steps": steps,
            "safety_note": safety_note,
        }

    async def _execute_action(
        self, action: Any, observations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Validate and execute one tool action from the model."""
        obs_id = f"obs_{len(observations) + 1}"
        observation: Dict[str, Any] = {"id": obs_id}

        if not isinstance(action, dict):
            observation["error"] = (
                "Invalid action format. Expected {\"tool\": \"...\", \"arguments\": {...}}."
            )
            observations.append(observation)
            return observation

        tool_id = action.get("tool")
        arguments = action.get("arguments", {})
        observation["tool"] = tool_id
        observation["arguments"] = arguments

        if not isinstance(tool_id, str) or not tool_id:
            observation["error"] = "Missing or invalid action.tool."
            observations.append(observation)
            return observation

        normalized_tool_id = self._normalize_tool_id(tool_id)
        if normalized_tool_id != tool_id:
            observation["tool_normalized_to"] = normalized_tool_id
            tool_id = normalized_tool_id
            observation["tool"] = tool_id

        if tool_id not in self.tools_registry:
            observation["error"] = f"Unknown tool requested by model: {tool_id}"
            observations.append(observation)
            return observation

        if not isinstance(arguments, dict):
            observation["error"] = "action.arguments must be a JSON object."
            observations.append(observation)
            return observation

        arguments = self._sanitize_tool_arguments(tool_id, arguments)
        observation["arguments"] = arguments
        missing_required = self._missing_required_tool_arguments(tool_id, arguments)
        if missing_required:
            observation["error"] = (
                "Missing required tool arguments: " + ", ".join(sorted(missing_required))
            )
            observations.append(observation)
            return observation

        try:
            result = await self.call_tool(tool_id, arguments)
            observation["result"] = result
        except Exception as e:
            observation["error"] = str(e)

        observations.append(observation)
        return observation

    def _build_final_response(
        self,
        query: str,
        final_step: Dict[str, Any],
        steps: List[Dict[str, Any]],
        observations: List[Dict[str, Any]],
        safety_note: Optional[str],
    ) -> Dict[str, Any]:
        answer = str(final_step.get("answer", "")).strip() or "No final answer generated."
        confidence = str(final_step.get("confidence", "medium")).lower()
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "medium"

        limitations = self._normalize_text_list(final_step.get("limitations"))
        if safety_note and safety_note not in limitations:
            limitations.insert(0, safety_note)

        citations = self._normalize_citations(
            final_step.get("citations"),
            observations,
        )
        if not citations:
            citations = self._default_citations(observations)

        if not observations:
            no_tool_note = (
                "No MCP tool calls were used for this response; content may rely on model prior knowledge."
            )
            if no_tool_note not in limitations:
                limitations.insert(0, no_tool_note)
            if confidence == "high":
                confidence = "medium"

        return {
            "query": query,
            "answer": answer,
            "confidence": confidence,
            "citations": citations,
            "limitations": limitations,
            "steps": steps,
            "safety_note": safety_note,
            "tool_calls": len(observations),
        }

    def _parse_llm_json(self, raw_content: Any) -> Dict[str, Any]:
        """Parse model output into a JSON dict, with fallback extraction."""
        content = self._coerce_content_to_text(raw_content)
        if not content.strip():
            return {
                "thought": "Model returned empty output.",
                "is_final": True,
                "answer": "I could not generate an answer from the current model response.",
                "confidence": "low",
                "limitations": ["The model returned an empty response."],
            }

        json_candidates = []
        json_candidates.append(content.strip())

        fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
        json_candidates.extend(fenced)

        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            json_candidates.append(content[start : end + 1])

        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        decoder = json.JSONDecoder()
        for idx, char in enumerate(content):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(content[idx:])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        logger.error("Failed to parse JSON from model output: %s", content)
        return {
            "thought": "Failed to parse model output as JSON.",
            "is_final": True,
            "answer": "I had trouble parsing the model response. Please try again.",
            "confidence": "low",
            "limitations": ["The model returned invalid JSON."],
        }

    def _coerce_content_to_text(self, raw_content: Any) -> str:
        if isinstance(raw_content, str):
            return raw_content
        if isinstance(raw_content, list):
            parts = []
            for item in raw_content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(raw_content)

    def _observation_for_prompt(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Reduce observation payload size before adding it to prompt history."""
        prompt_observation: Dict[str, Any] = {
            "id": observation.get("id"),
            "tool": observation.get("tool"),
        }
        if "error" in observation:
            prompt_observation["error"] = observation["error"]
            return prompt_observation

        serialized = json.dumps(
            observation.get("result", {}),
            ensure_ascii=False,
            default=str,
        )
        if len(serialized) > MAX_TOOL_OBSERVATION_CHARS:
            serialized = serialized[:MAX_TOOL_OBSERVATION_CHARS] + "... [truncated]"
        prompt_observation["result"] = serialized
        return prompt_observation

    def _normalize_citations(
        self,
        citations: Any,
        observations: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        observation_by_id = {
            obs["id"]: obs for obs in observations if isinstance(obs, dict) and "id" in obs
        }
        normalized: List[Dict[str, str]] = []
        if not isinstance(citations, list):
            return normalized

        for item in citations:
            citation: Dict[str, str] = {}
            if isinstance(item, str):
                citation["observation_id"] = item.strip()
            elif isinstance(item, dict):
                observation_id = item.get("observation_id") or item.get("id")
                if observation_id:
                    citation["observation_id"] = str(observation_id).strip()
                if item.get("tool"):
                    citation["tool"] = str(item["tool"])
                if item.get("note"):
                    citation["note"] = str(item["note"])
            else:
                continue

            observation_id = citation.get("observation_id")
            if not observation_id or observation_id not in observation_by_id:
                continue

            if "tool" not in citation:
                citation["tool"] = str(observation_by_id[observation_id].get("tool", ""))
            if "note" not in citation:
                citation["note"] = "Tool result used in synthesis."

            normalized.append(citation)
            if len(normalized) >= MAX_CITATIONS:
                break

        return normalized

    def _default_citations(self, observations: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        citations: List[Dict[str, str]] = []
        for observation in observations:
            if "id" not in observation or "tool" not in observation:
                continue
            if "error" in observation:
                continue
            citations.append(
                {
                    "observation_id": str(observation["id"]),
                    "tool": str(observation["tool"]),
                    "note": "Tool result used in synthesis.",
                }
            )
            if len(citations) >= MAX_CITATIONS:
                break
        return citations

    def _normalize_text_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _merge_safety_note(
        self,
        limitations: List[str],
        safety_note: Optional[str],
    ) -> List[str]:
        merged = list(limitations)
        if safety_note and safety_note not in merged:
            merged.insert(0, safety_note)
        return merged

    def _normalize_tool_id(self, tool_id: str) -> str:
        normalized = tool_id.strip()
        if normalized.startswith("server."):
            normalized = normalized[len("server.") :]
        return normalized

    def _sanitize_tool_arguments(self, tool_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool_info = self.tools_registry.get(tool_id, {}).get("tool", {})
        schema = tool_info.get("inputSchema", {})
        properties = schema.get("properties", {})
        if not properties:
            return arguments

        allowed_keys = set(properties.keys())
        sanitized = {
            key: value
            for key, value in arguments.items()
            if key in allowed_keys
        }

        if not sanitized and arguments:
            logger.warning(
                "All arguments were filtered out for %s. Original keys: %s",
                tool_id,
                sorted(arguments.keys()),
            )

        dropped_keys = sorted(set(arguments.keys()) - allowed_keys)
        if dropped_keys:
            logger.info("Filtered unsupported args for %s: %s", tool_id, dropped_keys)

        return sanitized

    def _missing_required_tool_arguments(
        self, tool_id: str, arguments: Dict[str, Any]
    ) -> List[str]:
        tool_info = self.tools_registry.get(tool_id, {}).get("tool", {})
        schema = tool_info.get("inputSchema", {})
        required = schema.get("required", [])
        return [arg for arg in required if arg not in arguments]

    def _is_high_risk_medical_query(self, query: str) -> bool:
        return bool(HIGH_RISK_MEDICAL_PATTERN.search(query))

    def _build_system_prompt(self, tools_description: str, high_risk_query: bool) -> str:
        risk_instruction = ""
        if high_risk_query:
            risk_instruction = (
                "The user query appears to ask for personalized medical advice. "
                "You may provide general educational information only. "
                "Do not diagnose, prescribe, or recommend patient-specific treatment.\n"
            )

        return f"""You are a general-purpose biomedical knowledge assistant with access to specialized biomedical tools.

Available tools with exact parameters:
{tools_description}

Core rules:
1. Use EXACT tool names and parameter names from the list above.
2. Prefer evidence-backed answers from tool results over unsupported assumptions.
3. For biomedical factual claims, call at least one relevant tool before giving the final answer.
4. If evidence is insufficient or conflicting, say so explicitly.
5. Do not provide personalized diagnosis or treatment instructions.
{risk_instruction}

JSON response format for each step:
{{
  "thought": "reasoning",
  "action": {{
    "tool": "server.tool_name",
    "arguments": {{"param_name": "value"}}
  }},
  "is_final": false
}}

Final JSON format:
{{
  "thought": "reasoning summary",
  "answer": "final biomedical answer",
  "confidence": "high|medium|low",
  "citations": [
    {{
      "observation_id": "obs_1",
      "tool": "server.tool_name",
      "note": "what this observation supports"
    }}
  ],
  "limitations": ["uncertainty or missing data"],
  "is_final": true
}}

When citing evidence, use only observation IDs that were provided in prior observation messages.
"""

    def _format_tools_for_llm_detailed(self) -> str:
        """Format tools with complete parameter information for LLM."""
        formatted: List[str] = []
        tools_by_server: Dict[str, List[Any]] = {}

        for tool_id, info in self.tools_registry.items():
            server = info["server"]
            if server not in tools_by_server:
                tools_by_server[server] = []
            tools_by_server[server].append((tool_id, info["tool"]))

        for server in sorted(tools_by_server):
            formatted.append(f"\n{server} tools:")

            for tool_id, tool_info in sorted(tools_by_server[server], key=lambda item: item[0]):
                formatted.append(f"\n  {tool_id}:")
                formatted.append(f"    Description: {tool_info.get('description', 'N/A')}")

                schema = tool_info.get("inputSchema", {})
                properties = schema.get("properties", {})
                if not properties:
                    continue

                formatted.append("    Parameters:")
                required = set(schema.get("required", []))
                for param_name, param_info in properties.items():
                    param_type = param_info.get("type", "string")
                    param_desc = param_info.get("description", "No description")
                    is_required = param_name in required
                    if is_required:
                        formatted.append(
                            f"      - {param_name} ({param_type}, REQUIRED): {param_desc}"
                        )

                for param_name, param_info in properties.items():
                    if param_name in required:
                        continue
                    param_type = param_info.get("type", "string")
                    param_desc = param_info.get("description", "No description")
                    default = param_info.get("default", "N/A")
                    formatted.append(
                        f"      - {param_name} ({param_type}, optional, default: {default}): {param_desc}"
                    )

        return "\n".join(formatted)
