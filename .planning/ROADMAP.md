# Roadmap

**4 phases** | **11 requirements mapped** | All v1 requirements covered ✓

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 1 | Mobile & Coordinator Back-end | Establish Flutter app and FastAPI layer for tracking | [JOUR-01, JOUR-02, PRIV-01] | 3 |
| 2 | Edge AI Upgrades | Blind-spot calculation and journey-aware boosting | [EDG-01, EDG-02, EDG-03, BLND-01] | 3 |
| 3 | Alerting & Dashboard | Push notifications and React Security UI | [ALRT-01, ALRT-02, DASH-01] | 3 |
| 4 | MVP Integration | Integrated end-to-end simulation across components | [All above] | 2 |

## Phase Details

### Phase 1: Mobile & Coordinator Back-end
**Goal:** Establish Flutter app auth, journey planning, and the FastAPI coordinator
**Requirements:** JOUR-01, JOUR-02, PRIV-01
**Success Criteria:**
1. Users can successfully register, log in, and manage family contacts in an MVP mobile shell.
2. Users can create a journey, defining start and end points.
3. FastAPI coordinator correctly ingests journey status and handles user location privacy settings.
**UI hint:** yes

### Phase 2: Edge AI Upgrades
**Goal:** Implement blind-spot monitoring and incorporate journey sensitivity
**Requirements:** EDG-01, EDG-02, EDG-03, BLND-01
**Success Criteria:**
1. The codebase accurately infers if a user goes missing beyond the calculated expected transit time (blind spot).
2. Existing Edge AI pipeline properly lowers threat activation threshold (boosting) when a journey is active.
3. Edge pipeline remains capable of >= 25 FPS locally while utilizing XGBoost checks.
**UI hint:** no

### Phase 3: Alerting & Dashboard
**Goal:** Overhaul the Streamlit web app to a React Dashboard and wire Firebase pushes
**Requirements:** ALRT-01, ALRT-02, DASH-01
**Success Criteria:**
1. Re-implementation of UI in React, displaying the active journeys and anomalies.
2. Simulated medium/high threats trigger a multi-channel Firebase push to user, family, and security.
3. E-mail dispatch still successfully delivers snapshots.
**UI hint:** yes

### Phase 4: MVP Integration
**Goal:** Perform an end-to-end local demo spanning mobile, coordinator, edge AI, and web dashboard
**Requirements:** All
**Success Criteria:**
1. Starting a journey in the app lights up the Coordinator and arms the Edge AI nodes.
2. Simulating a delay immediately triggers an anomaly that reaches the mobile alerts and dashboard flawlessly.
**UI hint:** yes
