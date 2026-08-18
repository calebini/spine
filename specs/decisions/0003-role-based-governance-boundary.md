# Decision 0003: Role-Based Governance Boundary

Status: Proposed
Date: 2026-08-18

## Context

Scheduled contextual advisories introduce a public contract between Spine, an external
authorization and evidence-acceptance system, and an LLM-backed agent runtime. Binding
that contract to a current repository or product name would make an implementation
detail part of Spine's public language and make later renaming or replacement look like
a protocol migration.

The governing component's product identity is not a coordination fact. Spine needs to
know which authority decision and capability grant apply, not what the implementing
project is called.

## Proposed Decision

Spine specifications and public contracts will refer to the role as
`governance_authority`.

Related cross-system roles will likewise use protocol names such as `agent_runtime`,
`tool_provider`, `scheduler_runtime`, and `delivery_adapter`.

Repository, package, deployment, vendor, and product names:

- MUST NOT appear in public schema property names, enum values, identifier preimages,
  command names, reason codes, or persisted authority semantics;
- MAY appear in local configuration that binds a role to a concrete endpoint or
  adapter; and
- MAY appear in non-normative deployment documentation when operators need the mapping.

Changing the component that implements `governance_authority` does not change this
contract when the replacement conforms to the same protocol version.

## Consequences

Spine can develop and audit the cross-system boundary before any component rename or
new repository decision.

The eventual governance implementation may evolve independently without leaking its
brand into Spine's ontology. Cross-system fixtures can use role-neutral participants.

Operational configuration must still make the concrete authority endpoint and trust
root explicit. Role-neutral language does not permit implicit authority discovery or
ambient trust.

Existing Spine prose that names a particular governance implementation should migrate
to role-based language as related documents are updated. This is a documentation and
contract-boundary cleanup, not a runtime compatibility event.
