import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .mcp_client import MCPServer

load_dotenv()


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    description: str
    capabilities: tuple[str, ...]
    module: str
    default_path: Path


MCP_SERVERS: dict[str, MCPServerConfig] = {
    "opentargets": MCPServerConfig(
        name="opentargets",
        description=(
            "Open Targets Platform - drug target, disease, genetics, evidence, "
            "variant, study, and clinical trial data"
        ),
        capabilities=(
            "targets",
            "diseases",
            "drugs",
            "evidence",
            "variants",
            "studies",
            "genetic_associations",
            "pathways",
            "expression",
            "protein_interactions",
            "tractability",
            "safety",
            "mouse_phenotypes",
            "chemical_probes",
            "literature",
            "clinical_trials",
            "biomarkers",
        ),
        module="opentargets_mcp.server",
        default_path=Path("../opentargets-mcp"),
    ),
    "monarch": MCPServerConfig(
        name="monarch",
        description=(
            "Monarch Initiative - phenotype associations, disease models, "
            "ontology context, and semantic similarity"
        ),
        capabilities=(
            "phenotypes",
            "diseases",
            "genes",
            "genotype_phenotype",
            "disease_phenotype",
            "gene_phenotype",
            "model_organisms",
            "semantic_similarity",
            "hpo_terms",
            "disease_models",
        ),
        module="monarch_mcp.server",
        default_path=Path("../monarch-mcp"),
    ),
    "mychem": MCPServerConfig(
        name="mychem",
        description="MyChem.info - chemical, compound, drug, structure, and identifier data",
        capabilities=(
            "chemicals",
            "drugs",
            "compounds",
            "structures",
            "identifiers",
            "drugbank",
            "chembl",
            "pubchem",
            "pharmgkb",
            "drug_interactions",
            "mechanisms",
            "targets",
            "indications",
            "side_effects",
        ),
        module="mychem_mcp.server",
        default_path=Path("../mychem-mcp"),
    ),
    "mydisease": MCPServerConfig(
        name="mydisease",
        description=(
            "MyDisease.info - disease annotations, symptoms, phenotypes, "
            "genetics, and disease identifiers"
        ),
        capabilities=(
            "diseases",
            "symptoms",
            "phenotypes",
            "genetics",
            "drugs",
            "mondo",
            "omim",
            "orphanet",
            "mesh",
            "umls",
            "hpo",
            "disgenet",
            "ctd",
            "clinical_trials",
        ),
        module="mydisease_mcp.server",
        default_path=Path("../mydisease-mcp"),
    ),
    "mygene": MCPServerConfig(
        name="mygene",
        description="MyGene.info - gene, transcript, protein, variant, and ontology data",
        capabilities=(
            "genes",
            "transcripts",
            "proteins",
            "variants",
            "homologs",
            "pathways",
            "interactions",
            "expression",
            "ontology",
            "entrez",
            "ensembl",
            "uniprot",
            "refseq",
            "go_terms",
        ),
        module="mygene_mcp.server",
        default_path=Path("../mygene-mcp"),
    ),
}


def resolve_server_path(server_name: str) -> Path:
    config = get_server_config(server_name)
    env_var = f"{server_name.upper()}_MCP_PATH"
    return Path(os.getenv(env_var, str(config.default_path))).expanduser()


def get_server_config(server_name: str) -> MCPServerConfig:
    try:
        return MCP_SERVERS[server_name]
    except KeyError as exc:
        raise ValueError(f"Unknown MCP server: {server_name}") from exc


def build_server(server_name: str) -> MCPServer:
    config = get_server_config(server_name)
    return MCPServer(
        name=config.name,
        path=resolve_server_path(server_name),
        command=["uv", "run", "python", "-m", config.module],
        description=config.description,
        capabilities=list(config.capabilities),
    )


def selected_server_names(server_names: list[str] | None) -> list[str]:
    if not server_names:
        return list(MCP_SERVERS)

    unknown = [name for name in server_names if name not in MCP_SERVERS]
    if unknown:
        raise ValueError("Unknown MCP server(s): " + ", ".join(sorted(unknown)))
    return server_names


def split_tool_id(tool_id: str) -> tuple[str, str]:
    server_name, separator, tool_name = tool_id.partition(".")
    if not separator or not server_name or not tool_name:
        raise ValueError("Tool ID must use the form server.tool_name")
    get_server_config(server_name)
    return server_name, tool_name


def group_tools_by_server(
    tools_registry: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    tools_by_server: dict[str, list[dict[str, str]]] = {}
    for tool_id, info in tools_registry.items():
        server_name = str(info["server"])
        tool = info["tool"]
        tools_by_server.setdefault(server_name, []).append(
            {
                "id": tool_id,
                "name": str(tool.get("name", "")),
                "description": str(tool.get("description", "")),
            }
        )

    for server_tools in tools_by_server.values():
        server_tools.sort(key=lambda item: item["id"])
    return tools_by_server


def find_tools_by_capability(
    tools_registry: dict[str, dict[str, Any]],
    capability: str,
) -> list[str]:
    capability_lower = capability.lower()
    matching_tools: set[str] = set()

    for tool_id, info in tools_registry.items():
        tool = info["tool"]
        tool_name = str(tool.get("name", "")).lower()
        tool_description = str(tool.get("description", "")).lower()

        if capability_lower in tool_name or capability_lower in tool_description:
            matching_tools.add(tool_id)
            continue

        server_name = str(info["server"])
        server_capabilities = get_server_config(server_name).capabilities
        if any(capability_lower in item.lower() for item in server_capabilities):
            matching_tools.add(tool_id)

    return sorted(matching_tools)
