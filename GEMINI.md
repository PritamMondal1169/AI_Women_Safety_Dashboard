<!-- GSD:project-start source:PROJECT.md -->
## Project

**SafeSphere**

SafeSphere is a privacy-first, edge-AI-powered safety ecosystem that transforms existing public and road CCTV cameras into an intelligent, proactive guardian network. It provides women with threat-aware route guidance, real-time tracking during journeys, and instant multi-stakeholder alerts when potential dangers like following or encirclement are detected, keeping all video processing local.

**Core Value:** Proactive, multi-stakeholder real-time protection powered by purely local edge AI that guarantees privacy while significantly reducing response times.

### Constraints

- **Performance**: Edge nodes must guarantee >= 25 FPS with auto frame-skip dynamically handling drops.
- **Latency**: Alerts must fire <= 4 seconds from the moment a detection anomaly escalates to MEDIUM/HIGH threat.
- **Privacy**: No video processing in the cloud; only anonymized metadata and snapshot evidence is sent.
- **Scalability**: MVP requires support for 2-10 cameras but needs an architecture scalable up to 50+.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.agent/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
