# Stage 2 Architecture Decision

Status: approved on 2026-10-15.

## Experiment

The baseline and resolver share parsing, chunking, retrieval, and retrieved evidence. The experimental variable is explicit relationship modeling:

- The baseline asks an LLM to answer directly from retrieved evidence.
- The resolver will extract structured provision events and apply a deterministic state reducer.

This controls for parsing and retrieval quality so measured differences are not caused by giving one system better source material.

## Approved constraints

- Supported attributes remain `LIMIT`, `DEDUCTIBLE`, and `POLICY_PERIOD`.
- PDF, HTML, and TXT inputs are supported.
- OCR is a bounded page-level fallback only when embedded PDF text is unusable.
- No graph database, vector database, agent framework, application database, API, or UI is part of Stage 3.
- The canonical benchmark is frozen and must not be modified without explicit approval.
- Both systems return the same structured result shape.

## Representation

The resolver will use an in-memory provision ledger keyed by attribute and subject. Each provision event will retain its operation, value or partial update, ordering metadata, explicit supersession relationship, evidence, and source locator. A deterministic reducer will apply ordered events and abstain when supplied evidence cannot establish precedence or a required value.

## Stage 3 baseline

The baseline uses the shared retriever and a single direct structured LLM response. It may reason from retrieved amendment text, but it has no provision ledger, relationship edges, deterministic ordering, state reducer, or relationship-driven retrieval expansion.
