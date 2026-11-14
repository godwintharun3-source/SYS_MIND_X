---
trigger: always_on
description: SYSTEM MIND architecture and cross-platform implementation constraints.
---
# Architecture Rules
- Keep the AI model separate from the privileged execution broker.
- Use typed capability interfaces and platform-specific adapters.
- Keep the digital twin temporal, provenance-aware and freshness-aware.
- Keep policy evaluation deterministic and independent from the LLM.
- All consequential actions require preconditions, postconditions and audit records.
- Implement mock adapters before privileged platform actions.
- Mark unavailable OS/hardware capabilities explicitly.
