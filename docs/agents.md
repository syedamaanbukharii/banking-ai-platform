# Agents

Every agent subclasses `BaseAgent[TInput, TOutput]`: typed Pydantic input/output,
structured logging, timing, and a uniform `AgentOutcome` (status, latency,
`model_used`, `prompt_version`). `execute()` wraps `run()` and converts errors into a
failed outcome rather than raising, so the workflow runner can record every step
uniformly.

Agents whose output is model-generated call the injected `ModelRouter`. Everything on
the decision path is deterministic and unit-tested.

## Orchestrator

Maps a `workflow_type` to a **plan**: the ordered agents to run and whether the
workflow is approval-gated (and which permission a reviewer must hold). The plan is
static, data-driven, and total over the workflow-type enum, which keeps control flow
auditable. It does not call a model.

## Document agent (deterministic)

Parses `Label: value` pairs from extracted text, checks them against an expected field
set for the document `kind` (`identity`, `proof_of_address`, `bank_statement`,
`generic`), reports missing fields, and produces review notes. Flags
`requires_human_review` when fields are missing or nothing parsed. Binary formats
(PDF/scan) require an upstream extraction/OCR step (documented seam); the agent accepts
already-extracted text so it stays deterministic.

Input: `document_id`, `kind`, `text`, optional `extra_expected_fields`.

## KYC agent (deterministic)

Validates profile completeness, runs cross-field consistency checks (name on document
vs profile, document-number match), derives age from date of birth, and assigns a
transparent risk level. Routes to human review when incomplete, inconsistent, or risk
≥ HIGH. Higher-risk jurisdictions are an explicit list (a real system would back this
with a sanctions/PEP feed behind the same interface).

Input: `profile` (dict), `document_fields` (dict), optional `today` (for deterministic
tests).

## Fraud agent (deterministic, explainable)

Transparent weighted rule scoring. Each rule contributes a documented weight and a
human-readable reason; the score is the clamped sum, mapped to LOW/MEDIUM/HIGH/CRITICAL.
HIGH/CRITICAL set `requires_human_review`. Rules include large absolute amount, anomaly
vs customer average, new account, large transfer to a new beneficiary, high-risk
destination, failed-login burst, and odd-hour large transfers. The block/escalate
decision is never taken autonomously for high-risk cases.

Input: `transaction` (object), optional `customer_avg_amount`.

## Compliance agent (RAG with citations)

Retrieves relevant policy chunks (via the retrieval agent) and produces a grounded
answer with explicit `[n]` citations drawn only from retrieved chunks. Without a
router it returns a deterministic extractive answer; with a router it synthesises over
the cited evidence using the `compliance.v1` prompt. It never cites a source it did not
retrieve.

Input: `question`, optional `top_k`.

## Retrieval agent (deterministic given a deterministic embedder)

Embeds the query and runs cosine search over the vector store, returning ranked
`SearchHit`s. Backs both the `/search` endpoint and the compliance agent.

## Summarization agent (model-backed)

Builds a strict prompt (`summarize.v1`), calls the router, and returns the summary plus
the model used. In tests the router uses a fake/echo provider, so behaviour is
deterministic and offline.

## Loan agent (deterministic)

Computes the monthly payment (amortised; zero-interest handled), debt-to-income ratio,
and disposable income, then recommends against documented thresholds. Always sets
`requires_human_review` — lending decisions require sign-off.

## Notification agent (deterministic)

Renders channel-ready messages from named templates (`decision`, `needs_info`,
`received`). Delivery is a side-effecting integration handled outside the agent, so the
agent stays pure and testable.

## Audit agent (deterministic)

Canonicalises supplied evidence (sorted keys) and computes a SHA-256 digest, producing
a tamper-evident bundle. Persistence of the append-only audit record is handled by the
audit service.

## Versioned prompts

Model-backed agents reference a prompt **version** (e.g. `summarize.v1`,
`compliance.v1`) loaded from `banking_ai/prompts/templates/`. The version flows into
`agent_runs.prompt_version` and `model_calls`, so any output is traceable to the exact
prompt. Changing a prompt means adding a new versioned file and repointing the agent;
historical runs stay attributable to the old version.
