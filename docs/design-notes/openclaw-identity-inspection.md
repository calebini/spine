# OpenClaw Identity Inspection: Initial Evidence

Recorded: 2026-09-05
Status: Non-authoritative report supplied by the user from the staging scheduling agent

## Purpose

Preserve the initial hints that motivated the proposed chat admission boundary without
treating them as verified provider guarantees. No deployed OpenClaw source/configuration
was independently inspected while writing this note. The supplied excerpt does not
identify an exact deployed build. It is not a security qualification or live test result.

## Reported Observations and Inferences

- Sender/conversation information appears to originate in the WhatsApp Web/Baileys
  runtime and pass through normalized OpenClaw context. Names mentioned include
  `ctx.SenderId/E164`, group JID, message ID, session key, and `requesterSenderId` in
  runtime tool options. These names are inspection leads, not pinned public APIs.
- The reporter described a split between minimal trusted system metadata, detailed
  human/chat facts supplied as untrusted prompt text, and runtime-only tool options.
  The precise provenance and mutability of each field were not established.
- Quoted/reply context was reported as untrusted. Mention gating may accept a quoted
  context without granting the quoted sender's authority. The cited provider-relative
  documentation path was `/docs/channels/whatsapp.md`; it is not a local Spine source.
- Ingress allowlists/admission were observed, but end-to-end cryptographic sender
  authenticity beyond the linked-session transport was not proven.
- Spine CLI `actor_subject_id` is currently authored in agent-generated request JSON;
  the reporter did not observe automatic binding to the originating human sender.
- Group members reportedly share an agent session/history. Current-message sender
  facts may differ while the session key remains shared.
- No verified-caller Spine wrapper was found in that inspection. Runtime-only tool
  context appears the strongest candidate integration point; generic `exec` does not
  independently bind a human principal to a Spine request.

## Explicit Unknowns

- Exact raw provider fields and deployed normalization for direct/group senders,
  account aliases, `remoteJid`, participant identity, and forwarded metadata.
- Whether runtime-only context can be substituted by tool arguments, mutable session
  state, concurrent turns, batching, callbacks, or extensions.
- Actual duplicate/edit behavior and recovery across process restarts; no live replay
  test was performed. Documentation claims are not proof of end-to-end idempotency.
- Process/credential isolation between trusted runtime code and model-controlled
  execution, plus every alternate route to Spine and its ledger.
- Private reply, transcript, memory, and tool-output isolation from shared sessions.

## Design Consequence, Not Deployment Claim

The likely weak point is the handoff from runtime origin evidence to model-authored
CLI arguments. The proposed remedy is a qualified message-specific broker/tool bridge
and shared Spine admission, with no bypassable agent ledger path. Upstream origin and
downstream audience isolation remain independent qualification requirements.

See [the consumer qualification draft](../../specs/openclaw-admission.md) and
[the single-operator admission draft](../../specs/single-operator-admission.md).
No sensitive message contents, phone numbers, credentials, or session tokens belong
in the follow-up evidence package.
