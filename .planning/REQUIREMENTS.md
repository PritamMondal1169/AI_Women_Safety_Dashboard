# SafeSphere v1 Requirements

## Overview
MVP capabilities required for the Hackathon + Phase 1 pilot of SafeSphere.

## v1 Requirements

### Journey
- [ ] **JOUR-01**: User can create account, login, and add trusted family contacts.
- [ ] **JOUR-02**: User can plan journeys (start/destination) and receive threat-aware route suggestions.

### Edge AI
- [ ] **EDG-01**: Real-time person detection and persistent tracking using YOLOv8n + BoT-SORT on edge hardware.
- [ ] **EDG-02**: Threat scoring engine calculates a live threat score (0-1) using 12 spatial-temporal features + XGBoost + heuristics.
- [ ] **EDG-03**: Journey-aware threat boosting (increases threat scores for active tracked journeys on route segments).

### Multi-Camera & Blind-Spot
- [ ] **BLND-01**: Blind-spot anomaly detection extrapolates expected transit times and flags delays between cameras.

### Alerting & Communication
- [ ] **ALRT-01**: Multi-stakeholder alerting dispatches instant push notifications (Woman, Family, Security) on Medium/High threats.
- [ ] **ALRT-02**: Emails sent with snapshot evidence + coordinates.

### Dashboard & Privacy
- [ ] **DASH-01**: React-based Security Dashboard for live monitoring of active journeys, threats, and alert history.
- [ ] **PRIV-01**: User privacy & consent controls (pause location sharing, control specific family visibility, journey-based consent).

## v2 Requirements (Deferred)
- Hardware GPS modules on cameras
- Full audio analytics
- On-device AI on mobile phones
- Payment/monetization features
- Nationwide central command center

## Out of Scope
- **Cloud Video Processing**: All visual AI stays at the edge; cloud only brokers coordinates/messages for adherence to privacy compliance.

## Traceability
*(To be populated by Roadmap)*
