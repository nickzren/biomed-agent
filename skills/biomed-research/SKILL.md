---
name: biomed-research
description: Use when answering biomedical research questions that need source-backed evidence from local MCP servers, including gene, disease, drug, variant, phenotype, study, or clinical-trial questions
---

# Biomed Research

Use this workflow for biomedical research answers over the five local MCP servers.

## Server Routing

| Need | Start With |
| --- | --- |
| target-disease evidence, drugs, variants, studies, trials | `opentargets` |
| phenotypes, HPO, rare disease, model organisms | `monarch` |
| gene annotation, IDs, expression, GO, orthologs | `mygene` |
| chemical/drug identifiers, mechanisms, structures | `mychem` |
| disease annotation, OMIM, Orphanet, MONDO, HPO | `mydisease` |

Resolve names to stable IDs first. Use the narrowest server that can answer the question. Fan out only when the question spans multiple entity types.

## Evidence Rules

- Prefer curated MCP tools over raw schema queries.
- Use source-backed observations before synthesis.
- Keep result payloads small by requesting specific fields when tools support it.
- Reconcile conflicts explicitly instead of averaging them away.
- Stop after 1-2 follow-up rounds if gaps remain; report the limitation.

## Output Contract

Return:

- `answer`: concise biomedical synthesis.
- `confidence`: `high`, `medium`, or `low`.
- `citations`: up to 8 `{observation_id, tool, note}` entries.
- `limitations`: missing evidence, conflicts, source caveats, and safety notes.
- `safety_note`: included for personalized medical advice requests.

Use low confidence when no MCP evidence was used or sources conflict.

## Safety Boundary

This is research and educational support, not clinical decision support. Do not diagnose, prescribe, dose, or recommend patient-specific treatment.

High-risk phrasing includes `diagnose`, `treatment`, `prescribe`, `dose`, `dosage`, `should I take`, `should I stop`, `medical advice`, `my symptoms`, and `for me personally`.

For those requests, provide only general biomedical context, decline personalized medical advice, and include the safety note in `limitations`.
