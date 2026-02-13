# ACE Audit Service

Independent audit trail following the **Audit Trail Independence Principle**.

> "Build your audit trail outside the agent's access. If the system you're monitoring controls the monitoring, you have no monitoring."

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  ACE Enterprise (main service)                              │
│  ┌─────────────┐       ┌─────────────┐                     │
│  │  TDD Agent  │       │  Playbook   │                     │
│  └──────┬──────┘       └─────────────┘                     │
│         │                                                   │
│         │ POST /events (write-only)                         │
└─────────┼───────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  ACE Audit Service (this service - separate deployment)    │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Audit Collector │    │   Audit API     │                │
│  │   (port 8081)   │    │   (port 8082)   │                │
│  │   Write-only    │    │   Read-only     │                │
│  └────────┬────────┘    └────────┬────────┘                │
│           │                      │                          │
│           └──────────┬───────────┘                          │
│                      ▼                                      │
│           ┌─────────────────────┐                           │
│           │    Audit Database   │                           │
│           │   (separate from    │                           │
│           │    main ACE DB)     │                           │
│           └─────────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

## Key Constraints

| Constraint | Enforcement |
|------------|-------------|
| Agents can't read audit | Collector has no query endpoints |
| Agents can't modify audit | Store is append-only (no UPDATE/DELETE) |
| Agents can't delete audit | No delete endpoints exist |
| Tamper evidence | Hash chain links all events |
| Separate credentials | Different database, different users |

## Services

### Audit Collector (port 8081)
- **Write-only** - accepts POST /events only
- Used by ACE agents to emit audit events
- Returns minimal response (no data leakage)

### Audit API (port 8082)
- **Read-only** - GET endpoints only
- Used by compliance officers, admins
- Includes hash chain verification

## Deployment

```bash
# Start the audit service (separate from main ACE)
cd services/ace-audit
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIT_DB_PASSWORD` | `audit_secret` | Audit database password |
| `AUDIT_DATABASE_URL` | (constructed) | Full database URL |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |

## Connecting ACE to Audit Service

In the main ACE service, set:

```bash
AUDIT_ENDPOINT=http://audit-collector:8081
```

Or if running locally:

```bash
AUDIT_ENDPOINT=http://localhost:8081
```

## Hash Chain Verification

Each audit event includes:
- `prev_hash`: SHA-256 hash of the previous event
- `event_hash`: SHA-256 hash of this event

To verify the chain:

```bash
curl http://localhost:8082/verify
```

Response:
```json
{
  "chain_valid": true,
  "first_invalid_event": null,
  "verified_at": "2026-02-13T..."
}
```

## Event Types

| Type | Description |
|------|-------------|
| `knowledge_added` | Manual knowledge via CLI |
| `pattern_learned` | AI-extracted pattern |
| `pattern_applied` | Pattern used in generation |
| `test_generated` | Test code written |
| `implementation_generated` | Implementation code written |
| `cycle_completed` | Full TDD cycle done |
| `agent_started` | Agent session began |
| `agent_completed` | Agent session ended |

## Security Notes

1. **Separate Database**: Audit DB runs on port 5433, not 5432
2. **No Shared Credentials**: ACE agents don't have audit DB credentials
3. **Append-Only**: No UPDATE or DELETE at application level
4. **Network Isolation**: Consider network policies in production
