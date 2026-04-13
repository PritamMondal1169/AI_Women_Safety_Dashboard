# SafeSphere

## What This Is

SafeSphere is a privacy-first, edge-AI-powered safety ecosystem that transforms existing public and road CCTV cameras into an intelligent, proactive guardian network. It provides women with threat-aware route guidance, real-time tracking during journeys, and instant multi-stakeholder alerts when potential dangers like following or encirclement are detected, keeping all video processing local.

## Core Value

Proactive, multi-stakeholder real-time protection powered by purely local edge AI that guarantees privacy while significantly reducing response times.

## Requirements

### Validated

- ✓ Edge AI person detection and tracking (YOLOv8n + BoT-SORT) — existing in codebase
- ✓ Hybrid threat detection engine (XGBoost + heuristics, 12 features) — existing in codebase
- ✓ Multi-channel asynchronous alerting (Email + Sound) — existing in codebase
- ✓ Local Streamlit Dashboard — existing in codebase

### Active

- [ ] FR-01: Mobile App (Flutter) for user authentication & journey management
- [ ] FR-04: Blind-Spot Anomaly Detection (expected transit time + delay threshold)
- [ ] FR-05: Journey-Aware Threat Boosting for active route segments
- [ ] FR-06: Expand alerting to include Push Notifications (Firebase) + Rerouting
- [ ] FR-07: Production Security Dashboard (React-based) with Live monitoring 
- [ ] FR-08: Privacy & Consent Controls 

### Out of Scope

- Hardware GPS modules on cameras — Rely on static mapping or external tracking.
- Full audio analytics — Focus entirely on spatial-temporal visual kinematics.
- On-device AI on mobile phones — Inference runs solely on the edge nodes connected to cameras.
- Payment/monetization features — Not prioritized for the current MVP/Phase 1.
- Nationwide central command center — Out of scope for MVP; local coordinator layer preferred.

## Context

- Building on an existing monolithic architecture that successfully implemented YOLO + Tracker + Threat Engine (Days 1–5 scope).
- Intended for deployment on standard CPUs or Jetson Nano hardware.
- The next step is a Hackathon MVP (Phase 0) extending the capabilities to include mobile journey planning and blind-spot detection across 2 simulated cameras.
- The system must remain privacy-compliant with the DPDP Act. Let video data remain on the edge nodes while only transmitting anonymized metadata.

## Constraints

- **Performance**: Edge nodes must guarantee >= 25 FPS with auto frame-skip dynamically handling drops.
- **Latency**: Alerts must fire <= 4 seconds from the moment a detection anomaly escalates to MEDIUM/HIGH threat.
- **Privacy**: No video processing in the cloud; only anonymized metadata and snapshot evidence is sent.
- **Scalability**: MVP requires support for 2-10 cameras but needs an architecture scalable up to 50+.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Cloud metadata only | Strictly adhering to privacy constraints by ensuring video frames stay local | — Pending |
| Flutter for Mobile | Enables rapid cross-platform development for MVP | — Pending |
| FastAPI Coordinator | Best for high-performance WebSocket messaging for live journey tracking | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-14 after initialization*
