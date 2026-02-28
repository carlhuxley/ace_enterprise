# ACE Modular Architecture Proposal

## Current State: Monolith

```
src/
├── agents/        → depends on audit, core, ensemble, playbook
├── audit/         → standalone
├── broker/        → depends on audit, storage, playbook
├── config/        → standalone
├── core/          → depends on config, playbook, storage, utils
├── ensemble/      → depends on core, playbook, storage, utils
├── ml/            → depends on storage, playbook
├── playbook/      → depends on storage, utils, config, audit
├── retrieval/     → depends on playbook, storage
├── storage/       → depends on config, utils
└── utils/         → depends on config
```

Everything in one repo. Hard to adopt partially.

---

## Proposed: Core + Packages

### Layer 0: Foundation

```
ace-core
├── config/        # Settings, environment
├── utils/         # LLM client, embedding service
└── schemas/       # Shared interfaces

pip install ace-core
```

Zero dependencies on other ACE packages. The base everything else builds on.

---

### Layer 1: Storage & Audit

```
ace-storage                      ace-audit
├── models/                      ├── client/
├── repository/                  ├── schemas/
└── experiment_logger/           └── store/

pip install ace-storage          pip install ace-audit
depends on: ace-core             depends on: ace-core
```

Independent packages. Install what you need.

---

### Layer 2: Knowledge & Patterns

```
ace-playbook
├── manager/           # Pattern CRUD
├── retrieval/         # Semantic search
├── cgr3/              # Context-aware retrieval
└── postgres_adapter/  # Storage backend

pip install ace-playbook
depends on: ace-core, ace-storage
```

The self-optimizing pattern system. Can be used standalone.

---

### Layer 3: Intelligence

```
ace-ensemble                     ace-tdd
├── consensus/                   ├── module_architect/
├── voting/                      ├── module_tdd_builder/
├── learner/                     ├── autonomous_agent/
└── models/                      └── contract_schema/

pip install ace-ensemble         pip install ace-tdd
depends on: ace-core,            depends on: ace-core,
            ace-playbook                     ace-playbook,
                                             ace-audit
```

The "smart" parts. Ensemble for multi-model consensus, TDD for the build loop.

---

### Layer 4: Integrations

```
ace-mcp                          ace-ml
├── server/                      ├── mlflow_callback/
├── tools/                       ├── experiment_knowledge/
└── handlers/                    └── postgres_callback/

pip install ace-mcp              pip install ace-ml
depends on: ace-core,            depends on: ace-core,
            ace-playbook                     ace-storage
optional: ace-tdd
```

Optional integrations. MCP for agent ecosystems, ML for data science.

---

## Dependency Graph

```
                    ┌─────────────┐
                    │  ace-core   │
                    └─────────────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
     ┌──────────┐  ┌──────────┐  ┌──────────┐
     │ace-audit │  │ace-storage│  │ (direct) │
     └──────────┘  └──────────┘  └──────────┘
            │             │
            └──────┬──────┘
                   ▼
            ┌──────────────┐
            │ ace-playbook │
            └──────────────┘
                   │
         ┌─────────┼─────────┐
         ▼         ▼         ▼
   ┌──────────┐ ┌─────┐ ┌──────────┐
   │ace-ensemble│ │ace-tdd│ │ ace-mcp │
   └──────────┘ └─────┘ └──────────┘
```

---

## Usage Examples

### Minimal: Just the playbook

```python
pip install ace-core ace-playbook

from ace_playbook import PlaybookManager
from ace_core import LLMClient

playbook = PlaybookManager()
patterns = playbook.get_guidance("how to handle errors")
```

### TDD without ML tracking

```python
pip install ace-core ace-playbook ace-tdd

from ace_tdd import ModuleTDDBuilder
# No ace-ml needed
```

### Full stack

```python
pip install ace-core ace-playbook ace-tdd ace-audit ace-mcp ace-ml
# Everything
```

---

## Open Source Strategy with Modules

| Package | License | Why |
|---------|---------|-----|
| ace-core | MIT | Foundation, maximum adoption |
| ace-storage | MIT | Basic infrastructure |
| ace-playbook | MIT | Core differentiator, but drives adoption |
| ace-audit | MIT (basic) / Commercial (dashboards) | Basic free, enterprise dashboards paid |
| ace-tdd | MIT | The TDD loop, drives adoption |
| ace-ensemble | MIT | Advanced but open |
| ace-mcp | MIT | Integration, drives adoption |
| ace-ml | MIT | Nice to have |
| ace-enterprise | Commercial | Team features, SSO, centralized audit |

---

## Applications (Built ON ACE, not IN ACE)

These would be separate repos that depend on ACE packages:

```
ace-digital-twin          # API mock generation
├── depends on: ace-core, ace-tdd
└── separate repo

ace-transpiler            # Cross-language rebuild
├── depends on: ace-core, ace-tdd
└── separate repo

ace-validator             # Bidirectional artifact validation
├── depends on: ace-core, ace-tdd
└── separate repo
```

Not features OF ACE. Tools built WITH ACE.

---

## Migration Path

1. **Phase 1**: Extract `ace-core` (config, utils, shared schemas)
2. **Phase 2**: Extract `ace-storage` and `ace-audit`
3. **Phase 3**: Extract `ace-playbook`
4. **Phase 4**: Extract `ace-tdd` and `ace-ensemble`
5. **Phase 5**: Extract integrations (`ace-mcp`, `ace-ml`)

Each phase: create package, update imports, maintain backwards compat in main repo.

---

## Benefits

- **Adopt what you need**: Don't want ML? Don't install it.
- **Clearer boundaries**: Each package has a job.
- **Easier contribution**: Work on one package without understanding all.
- **Flexible licensing**: Open core, commercial add-ons.
- **Applications separate**: Digital twin isn't ACE bloat, it's a tool using ACE.
