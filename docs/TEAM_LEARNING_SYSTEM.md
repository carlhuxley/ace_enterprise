# ACE Team Learning System - Design Document

**Status:** Concept / Future Enhancement
**Created:** 2025-10-18
**Priority:** High-value team collaboration feature

---

## 🎯 Executive Summary

Transform ACE from an individual learning system into a **team-wide collective intelligence platform** where:
- All developers share a unified knowledge base
- Quality gates prevent bad patterns from spreading
- New team members instantly benefit from collective experience
- Code quality improves automatically over time

**Key Benefit:** Turn tribal knowledge into executable, quality-gated coding patterns.

---

## 🏗️ Architecture Overview

### Current State (Individual Learning)
```
Developer A → ACE Instance A → Playbook A (isolated)
Developer B → ACE Instance B → Playbook B (isolated)
Developer C → ACE Instance C → Playbook C (isolated)
```

**Problem:** Knowledge silos, repeated mistakes, inconsistent quality

### Proposed State (Team Learning)
```
┌─────────────┐
│ Developer A │──┐
└─────────────┘  │
                 ├──► ┌────────────────────┐
┌─────────────┐  │    │  Team Playbook     │
│ Developer B │──┤    │    Repository      │
└─────────────┘  │    │  + Quality Gates   │
                 ├──► └────────────────────┘
┌─────────────┐  │              ↓
│ Developer C │──┘        ┌────────────┐
└─────────────┘           │ Analytics  │
                          │ Dashboard  │
                          └────────────┘
```

**Benefits:** Shared learning, enforced quality, compound knowledge growth

---

## 📊 Core Components

### 1. Quality Voting System

**Schema Enhancement:**
```python
class Bullet:
    # Existing fields
    id: str
    content: str
    section: str
    tags: list[str]
    embedding: list[float]

    # Quality tracking (already exists!)
    helpful_count: int = 0
    harmful_count: int = 0

    # New fields for team system
    status: Literal["active", "deprecated", "under_review"] = "active"
    replacement_id: Optional[str] = None  # Points to better pattern
    contributor: str = "unknown"  # Who added this pattern
    votes: list[Vote] = []  # Detailed voting history
    confidence_score: float = 0.0  # Calculated from votes
    last_reviewed: datetime = None

class Vote:
    user_id: str
    vote_type: Literal["helpful", "harmful", "neutral"]
    timestamp: datetime
    comment: Optional[str] = None
    context: Optional[str] = None  # What task was this used for?
```

**Quality Metrics:**
```python
def calculate_confidence(bullet: Bullet) -> float:
    """
    Calculate confidence score for a bullet.

    Factors:
    - Vote count (more votes = higher confidence)
    - Helpful ratio (helpful / total votes)
    - Recency (recent votes weighted higher)
    - Consistency (all helpful vs mixed votes)
    """
    total_votes = bullet.helpful_count + bullet.harmful_count

    if total_votes == 0:
        return 0.0  # No confidence without votes

    # Base score from ratio
    helpful_ratio = bullet.helpful_count / total_votes

    # Boost for vote count (plateau at 10 votes)
    vote_confidence = min(total_votes / 10, 1.0)

    # Recency boost (votes in last 30 days weighted 2x)
    recent_votes = [v for v in bullet.votes if (datetime.now() - v.timestamp).days < 30]
    recency_boost = len(recent_votes) / max(total_votes, 1) * 0.2

    # Consistency (penalize if controversial)
    consistency = abs(helpful_ratio - 0.5) * 2  # 1.0 if unanimous, 0.0 if 50/50

    return (helpful_ratio * 0.5 +
            vote_confidence * 0.3 +
            consistency * 0.15 +
            recency_boost * 0.05)
```

---

### 2. Quality Gates

**Retrieval Filtering:**
```python
class QualityGate:
    """Configuration for quality-based filtering."""

    # Minimum thresholds
    min_helpful_ratio: float = 0.7      # 70%+ helpful votes required
    min_vote_count: int = 3             # At least 3 votes for trust
    min_confidence: float = 0.6         # Minimum confidence score

    # Exclusion rules
    exclude_harmful: bool = True        # Never use harmful patterns
    exclude_deprecated: bool = True     # Skip deprecated patterns

    # Context-based gates
    production_mode: bool = False       # Stricter gates for production
    experimental_mode: bool = False     # Relaxed gates for experimentation

def retrieve_with_quality_gate(
    query: str,
    bullets: list[Bullet],
    quality_gate: QualityGate,
) -> list[tuple[Bullet, float]]:
    """Retrieve bullets that pass quality gates."""

    # Filter by quality criteria
    filtered = []
    for bullet in bullets:
        # Skip deprecated
        if quality_gate.exclude_deprecated and bullet.status == "deprecated":
            continue

        # Skip harmful
        total_votes = bullet.helpful_count + bullet.harmful_count
        if total_votes > 0:
            ratio = bullet.helpful_count / total_votes
            if quality_gate.exclude_harmful and ratio < 0.5:
                continue
            if ratio < quality_gate.min_helpful_ratio:
                continue

        # Check vote count
        if total_votes < quality_gate.min_vote_count:
            continue

        # Check confidence
        confidence = calculate_confidence(bullet)
        if confidence < quality_gate.min_confidence:
            continue

        filtered.append(bullet)

    # Normal retrieval on filtered set
    return standard_retrieval(query, filtered)
```

**Production vs Development Gates:**
```python
# Development: Learn from everything
dev_gate = QualityGate(
    min_helpful_ratio=0.3,
    min_vote_count=1,
    min_confidence=0.2,
    experimental_mode=True,
)

# Production: Only proven patterns
prod_gate = QualityGate(
    min_helpful_ratio=0.8,
    min_vote_count=5,
    min_confidence=0.7,
    production_mode=True,
)
```

---

### 3. Team Playbook Sync

**Architecture Options:**

#### Option A: Git-Based Sync (Simplest)
```bash
# Team playbook repository
team-playbooks/
├── .playbook-meta.json         # Team settings, contributors
├── domains/
│   ├── authentication/
│   │   ├── playbook.json       # 45 bullets
│   │   └── analytics.json      # Usage stats
│   ├── database/
│   │   ├── playbook.json       # 67 bullets
│   │   └── analytics.json
│   └── security/
│       ├── playbook.json       # 34 bullets
│       └── analytics.json
└── README.md

# Developer workflow
$ git clone git@github.com:team/playbooks.git
$ ace sync --team-playbooks ./team-playbooks
✓ Synced 146 team patterns
✓ Loaded 4 domain playbooks
```

**Benefits:**
- Version control (see pattern evolution)
- Branch-based experimentation
- Code review for new patterns
- Works with existing workflows

**Implementation:**
```python
class TeamPlaybookSync:
    """Git-based team playbook synchronization."""

    def __init__(self, repo_path: str):
        self.repo = git.Repo(repo_path)
        self.playbook_manager = PlaybookManager()

    def pull_team_playbooks(self) -> dict[str, int]:
        """Pull latest team playbooks from Git."""
        self.repo.remotes.origin.pull()

        synced = {}
        domains_dir = Path(self.repo_path) / "domains"

        for domain_dir in domains_dir.iterdir():
            playbook_file = domain_dir / "playbook.json"
            if playbook_file.exists():
                playbook = self._load_playbook(playbook_file)
                self.playbook_manager.import_playbook(playbook)
                synced[playbook.playbook_id] = playbook.metadata.total_bullets

        return synced

    def push_new_patterns(self, playbook_id: str, commit_msg: str):
        """Push newly learned patterns to team repo."""
        playbook = self.playbook_manager.export_playbook(playbook_id)

        # Save to team repo
        domain_dir = Path(self.repo_path) / "domains" / playbook.metadata.domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        playbook_file = domain_dir / "playbook.json"
        with open(playbook_file, 'w') as f:
            json.dump(playbook, f, indent=2)

        # Commit and push
        self.repo.index.add([str(playbook_file)])
        self.repo.index.commit(commit_msg)
        self.repo.remotes.origin.push()
```

#### Option B: Centralized Server (Scalable)
```
┌──────────────────────────────────────┐
│     ACE Team Server                  │
├──────────────────────────────────────┤
│                                      │
│  PostgreSQL:                         │
│    - Playbook metadata               │
│    - Votes and analytics             │
│    - User permissions                │
│                                      │
│  Vector DB (Pinecone/Weaviate):      │
│    - Bullet embeddings               │
│    - Semantic search                 │
│                                      │
│  Redis Cache:                        │
│    - Hot patterns                    │
│    - Session data                    │
│                                      │
│  API (FastAPI):                      │
│    - /api/bullets/search             │
│    - /api/bullets/vote               │
│    - /api/playbooks/sync             │
│    - /api/analytics/team             │
│                                      │
└──────────────────────────────────────┘
```

**API Examples:**
```python
# Vote on a pattern
POST /api/bullets/{bullet_id}/vote
{
    "vote_type": "helpful",
    "comment": "Used this for user auth, worked perfectly",
    "context": "task_id_12345"
}

# Search team patterns
POST /api/bullets/search
{
    "query": "validate password requirements",
    "quality_gate": {
        "min_helpful_ratio": 0.7,
        "min_vote_count": 3
    },
    "domains": ["authentication", "security"]
}

# Sync local playbook with team
POST /api/playbooks/sync
{
    "playbook_id": "pb_20251018_267",
    "new_bullets": [...],
    "pull_team_patterns": true
}
```

---

### 4. Analytics Dashboard

**Metrics to Track:**

```python
class TeamAnalytics:
    """Analytics for team learning progress."""

    def get_knowledge_growth(self, days: int = 30) -> dict:
        """Track knowledge base growth over time."""
        return {
            "total_bullets": 456,
            "new_bullets_last_30d": 89,
            "avg_quality_score": 0.87,
            "domains_covered": 12,
            "growth_rate": "+23% vs last month"
        }

    def get_top_contributors(self, limit: int = 10) -> list[dict]:
        """Identify top pattern contributors."""
        return [
            {
                "user": "alice@team.com",
                "helpful_patterns": 45,
                "avg_confidence": 0.92,
                "domains": ["auth", "api", "database"]
            },
            {
                "user": "bob@team.com",
                "helpful_patterns": 38,
                "avg_confidence": 0.88,
                "domains": ["frontend", "testing"]
            }
        ]

    def get_pattern_effectiveness(self) -> dict:
        """Track which patterns are most useful."""
        return {
            "most_used": [
                {
                    "bullet_id": "ctx-1234",
                    "content": "Use parameterized SQL queries",
                    "usage_count": 234,
                    "success_rate": 0.96
                },
                {
                    "bullet_id": "ctx-5678",
                    "content": "Validate input length with >=",
                    "usage_count": 189,
                    "success_rate": 0.91
                }
            ],
            "needs_review": [
                {
                    "bullet_id": "ctx-9999",
                    "content": "...",
                    "vote_count": 2,  # Low confidence
                    "helpful_ratio": 0.45
                }
            ]
        }

    def get_velocity_metrics(self) -> dict:
        """Measure impact on development speed."""
        return {
            "avg_iterations_per_task": 1.2,  # Was 2.3 before
            "time_saved_per_week": "~4 hours per developer",
            "code_review_time": "-30% (better initial quality)",
            "regression_incidents": "-60% (known issues prevented)"
        }
```

**Dashboard UI (Conceptual):**
```
┌─────────────────────────────────────────────────────────┐
│  ACE Team Learning Dashboard                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📈 Knowledge Growth (Last 30 Days)                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━             │
│  Total Bullets: 456 (+89)  Avg Quality: 0.87           │
│                                                         │
│  🏆 Top Contributors                                    │
│  1. Alice     45 patterns  (0.92 quality)               │
│  2. Bob       38 patterns  (0.88 quality)               │
│  3. Carol     29 patterns  (0.85 quality)               │
│                                                         │
│  🔥 Most Effective Patterns                             │
│  1. "Parameterized SQL"      234 uses (96% success)     │
│  2. "Input validation >= "   189 uses (91% success)     │
│  3. "Error handling pattern" 156 uses (89% success)     │
│                                                         │
│  ⚠️  Patterns Needing Review (12)                       │
│  - 8 with <3 votes                                      │
│  - 4 with ratio <0.5                                    │
│                                                         │
│  🚀 Team Velocity                                       │
│  Iterations per task: 1.2 (was 2.3) [-48%] 🎉          │
│  Time saved: ~4 hrs/week per dev                        │
│  Code review time: -30%                                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🔄 Workflows

### Workflow 1: New Developer Onboarding
```
Day 1:
┌─────────────────────────────────────────┐
│ 1. Clone team playbook repo             │
│    $ git clone team/playbooks           │
│                                         │
│ 2. Configure ACE to use team patterns   │
│    $ ace config --team-mode enabled     │
│                                         │
│ 3. First task                           │
│    $ ace generate --task "user auth"    │
│    ✓ Retrieved 45 team patterns         │
│    ✓ Code follows team standards        │
│    ✓ Comments explain "why"             │
│                                         │
│ Result: Productive from day 1!          │
└─────────────────────────────────────────┘
```

### Workflow 2: Pattern Quality Review
```
Weekly Team Meeting:
┌─────────────────────────────────────────┐
│ 1. Review new patterns (12 this week)   │
│    - 8 auto-approved (high confidence)  │
│    - 4 need discussion                  │
│                                         │
│ 2. Vote on controversial patterns       │
│    Pattern: "Always use async/await"    │
│    👍 3  👎 2  💬 "Not for CPU-bound"   │
│    → Modify to context-specific         │
│                                         │
│ 3. Deprecate outdated patterns          │
│    Pattern: "Use callbacks for async"   │
│    → Replaced with async/await pattern  │
│                                         │
│ 4. Celebrate wins                       │
│    "SQL injection prevention" pattern   │
│    used 45 times, 0 incidents! 🎉       │
└─────────────────────────────────────────┘
```

### Workflow 3: CI/CD Quality Gate
```
Pull Request Created:
┌─────────────────────────────────────────┐
│ PR #123: Add password reset feature     │
│                                         │
│ ACE Quality Check:                      │
│ ✅ Uses 12 approved team patterns       │
│ ✅ No harmful patterns detected         │
│ ⚠️  Learned 2 new patterns (review)     │
│                                         │
│ New Patterns for Review:                │
│ 1. "Send reset email with token"        │
│    Confidence: 0.45 (needs votes)       │
│                                         │
│ 2. "Expire tokens after 1 hour"         │
│    Confidence: 0.38 (needs votes)       │
│                                         │
│ Action Required:                        │
│ Team members: Vote on new patterns      │
│ before merge.                           │
└─────────────────────────────────────────┘
```

---

## 🛠️ Implementation Roadmap

### Phase 1: Basic Team Sharing (2-3 days)
**Goal:** Enable playbook export/import for manual sharing

**Tasks:**
- [ ] Add playbook export to JSON with full metadata
- [ ] Add playbook import with conflict resolution
- [ ] Create team playbook repo template
- [ ] Documentation for Git-based workflow

**Files to Create/Modify:**
- `src/playbook/export.py` - Export functionality
- `src/playbook/import.py` - Import with validation
- `scripts/sync_team_playbooks.py` - Sync script
- `docs/TEAM_WORKFLOW.md` - Usage guide

### Phase 2: Quality Gates (1 week)
**Goal:** Implement confidence scoring and quality filtering

**Tasks:**
- [ ] Add Vote schema to database
- [ ] Implement confidence calculation
- [ ] Add quality gate configuration
- [ ] Update retrieval to use quality gates
- [ ] Create voting CLI interface

**Files to Create/Modify:**
- `src/storage/schemas.py` - Add Vote, update Bullet
- `src/playbook/quality.py` - Confidence calculation
- `src/playbook/retrieval.py` - Quality-based filtering
- `scripts/vote_on_pattern.py` - Voting interface

### Phase 3: Analytics Dashboard (1-2 weeks)
**Goal:** Track team learning and pattern effectiveness

**Tasks:**
- [ ] Create analytics module
- [ ] Build dashboard backend (FastAPI)
- [ ] Create simple web UI (React/Vue)
- [ ] Add real-time metrics

**Files to Create/Modify:**
- `src/analytics/team_metrics.py` - Analytics engine
- `api/main.py` - FastAPI server
- `dashboard/` - Web UI
- `docker-compose.yml` - Easy deployment

### Phase 4: Centralized Server (2-3 weeks)
**Goal:** Production-ready team server with sync

**Tasks:**
- [ ] Set up PostgreSQL backend
- [ ] Integrate vector database
- [ ] Build sync API
- [ ] Add authentication
- [ ] Deploy to cloud

**Infrastructure:**
- PostgreSQL for metadata
- Pinecone/Weaviate for embeddings
- Redis for caching
- Docker for deployment

---

## 💰 Cost-Benefit Analysis

### Costs (Development Time)
```
Phase 1 (Basic):     2-3 days     (1 developer)
Phase 2 (Quality):   1 week       (1 developer)
Phase 3 (Analytics): 1-2 weeks    (1 developer)
Phase 4 (Server):    2-3 weeks    (1-2 developers)
────────────────────────────────────────────────
Total:               6-8 weeks    (conservative)
```

### Benefits (Team of 10 Developers)
```
Time Savings:
- Onboarding: 2-3 days → 0.5 day per new dev
- Bug prevention: ~2 hrs/week per dev (known issues)
- Code review: 30% faster (better initial quality)
- Knowledge transfer: Automatic vs meetings/docs

Estimated ROI:
- Week 1: 10 devs × 2 hrs saved = 20 hrs/week
- Month 1: ~80 hrs saved
- Year 1: ~1000 hrs saved = $100k+ value

Intangible Benefits:
- Consistent code quality
- Reduced technical debt
- Better team collaboration
- Institutional knowledge preservation
```

---

## 🎯 Success Metrics

### Short-term (1-3 months)
- [ ] 5+ developers actively using team playbooks
- [ ] 100+ team patterns with >3 votes each
- [ ] 50%+ reduction in repeated mistakes
- [ ] 30%+ faster code review process

### Medium-term (3-6 months)
- [ ] 500+ high-quality team patterns
- [ ] 80%+ pattern helpful ratio
- [ ] New devs productive in <1 day
- [ ] 40%+ reduction in average iterations per task

### Long-term (6-12 months)
- [ ] 1000+ patterns across 10+ domains
- [ ] Measurable impact on code quality metrics
- [ ] Team velocity increase >30%
- [ ] Zero repeated critical bugs

---

## 🚨 Risks & Mitigation

### Risk 1: Pattern Quality Degradation
**Risk:** Low-quality patterns pollute knowledge base
**Mitigation:**
- Quality gates with minimum vote thresholds
- Regular pattern review process
- Auto-deprecation of harmful patterns
- Confidence scoring prevents bad pattern usage

### Risk 2: Over-reliance on AI
**Risk:** Developers stop thinking critically
**Mitigation:**
- Patterns are suggestions, not mandates
- Code review still required
- Encourage discussion/voting on patterns
- Dashboard shows "why" behind patterns

### Risk 3: Sync Conflicts
**Risk:** Multiple devs update same pattern
**Mitigation:**
- Git-based workflow handles conflicts naturally
- Last-write-wins with version tracking
- Conflict resolution UI for server-based system

### Risk 4: Privacy/Security
**Risk:** Sensitive patterns exposed
**Mitigation:**
- Pattern sanitization before sharing
- Optional private playbooks
- Access control in server-based system
- Audit logs for compliance

---

## 📚 References & Related Work

### Similar Concepts
- **Copilot Collective Knowledge:** GitHub Copilot learns from public code
- **Team Libraries:** Reusable code components (but not contextual)
- **Style Guides:** Static rules (but not learned/adaptive)
- **Code Review Bots:** Detect issues (but don't learn patterns)

### What Makes ACE Different
- ✅ **Learns from failures**, not just successes
- ✅ **Context-aware** via semantic embeddings
- ✅ **Quality-gated** via team voting
- ✅ **Self-improving** via confidence scoring
- ✅ **Explains "why"** via natural language bullets

---

## 🔮 Future Enhancements

### Advanced Features
1. **A/B Testing of Patterns**
   - Try pattern A vs pattern B
   - Measure which leads to better outcomes
   - Auto-promote winning patterns

2. **Cross-Team Learning**
   - Share sanitized patterns between teams
   - Industry-wide best practices database
   - Open-source playbook marketplace

3. **AI-Assisted Pattern Discovery**
   - Automatically detect emergent patterns in team code
   - Suggest new bullets based on successful PRs
   - Identify contradicting patterns

4. **Domain-Specific Quality Gates**
   - Security: Stricter gates for auth/crypto
   - Performance: Different thresholds for critical paths
   - Compliance: Enforce regulatory patterns

5. **Integration with Tools**
   - IDE plugins (VS Code, JetBrains)
   - Slack/Discord notifications
   - Jira/Linear task integration
   - GitHub/GitLab native apps

---

## 🎬 Next Steps

### To Implement Later:
1. **Review this document** with team for feedback
2. **Prioritize phases** based on team needs
3. **Prototype Phase 1** (Git-based sharing)
4. **Gather user feedback** from real usage
5. **Iterate and expand** based on learnings

### Questions to Answer:
- What domains would benefit most?
- How should voting work (UI/CLI)?
- Self-hosted vs cloud deployment?
- Privacy requirements for patterns?
- Integration priorities (IDE/Git/CI)?

---

**Document Status:** Ready for future implementation
**Estimated Value:** High (10x ROI potential)
**Technical Feasibility:** Medium (builds on existing ACE infrastructure)
**Team Buy-in Required:** Yes (cultural shift to shared learning)

---

_This document captures the vision for ACE Team Learning System. Implementation can be phased based on team priorities and resources._
