---
title: Audit trail independence principle
date: 2026-02-12
type: insight
tags: [security, monitoring, system-design, architecture, audit, independence]
topics:
  - audit trail design
  - monitoring architecture
  - security principles
  - system independence
key_insight: Monitoring systems must be external to monitored systems to maintain integrity
ai_confidence: 0.95
status: fleeting
---

# Audit trail independence principle

Build your audit trail outside the agent's access. If the system you're monitoring controls the monitoring, you have no monitoring.

## Key Principle

For effective monitoring and auditing, the audit mechanism must be:
- **Independent** from the system being monitored
- **External** to prevent tampering or hiding of logs
- **Separate** to ensure integrity and trustworthiness

## Implications

- Centralized logging systems separate from application servers
- External security information and event management (SIEM)
- Immutable audit logs in independent storage
- Separation of concerns in security architecture

## Related Concepts

- Principle of least privilege
- Defense in depth
- Trust but verify
- Security by design
