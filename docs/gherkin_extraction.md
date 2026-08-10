# Gherkin Extraction — Reverse Engineering for Safe Refactoring

The Gherkin Extraction Agent reverse-engineers Gherkin acceptance tests from
existing Python code and tests. This enables:

1. **Safe refactoring** — extract specs, rebuild with a clean implementation
2. **Cross-language migration** — Python → Go, verified against the same specs
3. **Documentation generation** — auto-generate business-readable docs
4. **Legacy system understanding** — understand what code actually does

## The problem

Organizations have valuable code that needs refactoring, migration, or
documentation, but traditional approaches risk breaking existing behavior,
losing institutional knowledge, or shipping an incomplete migration with no
way to verify correctness.

## The solution

```
Existing Code + Tests
    ↓
Extract Gherkin (language-agnostic specification)
    ↓
Use as blueprint for reimplementation
    ↓
Validate new implementation passes same specs
    ↓
Behavior preserved!
```

## Architecture

**`GherkinExtractionAgent`** (`src/agents/gherkin_extraction_agent.py`)
- Analyzes Python code and tests
- Extracts business scenarios
- Generates Gherkin feature files and step definitions

**`CodeAnalyzer`** — parses Python AST, extracts classes, method signatures,
and API contracts.

**`TestAnalyzer`** — analyzes pytest/unittest tests, identifies
Given/When/Then patterns, extracts assertions and expectations.

**`GoStepGenerator`** (`src/agents/go_step_generator.py`) — the one
implemented cross-language target today: generates Go/Cucumber (`godog`)
step definitions, a test runner, and `go.mod` scaffolding from an extracted
feature file.

## Workflow

### 1. Extract from Python

```bash
python3 demo_gherkin_extraction.py
```

Given Python source and its tests, the agent extracts a Gherkin feature file
and matching step definitions:

```python
# oauth.py
class OAuthClient:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id

    def generate_authorization_url(self, redirect_uri, scope):
        return f"https://auth.example.com?client_id={self.client_id}"
```

```gherkin
Feature: OAuth Authentication
  OAuth 2.0 client for authorization code flow.

  Scenario: Create oauth client
    Given an OAuth client with client_id and client_secret
    Then the client should be properly configured

  Scenario: Generate authorization url
    Given an OAuth client
    When I generate an authorization URL
    Then the URL should contain the client_id parameter
```

### 2. Generate the Go implementation

```bash
python3 demo_cross_language_migration.py
```

Produces a scaffolded Go package (`steps/oauth_steps.go`, `steps/oauth_test.go`,
`go.mod`) with `godog` step bindings ready to implement:

```go
package steps

type OauthContext struct {
    client *OAuthClient
    url    string
}

func (ctx *OauthContext) InitializeScenario(sc *godog.ScenarioContext) {
    sc.Step(`^an OAuth client with (.+)$`, ctx.anOAuthClientWith)
    sc.Step(`^I generate an authorization URL$`, ctx.iGenerateAuthURL)
    sc.Step(`^the URL should contain (.+)$`, ctx.urlShouldContain)
}
```

### 3. Implement and validate

```bash
# Implement the generated Go steps, then run both suites against
# the same feature file:
behave features/oauth.feature   # Python
go test -v                      # Go

# Both pass = behavior preserved.
```

Both demo scripts write their output into untracked local directories
(`extracted_gherkin/`, `go_oauth_implementation/`) — they're regenerated on
each run and aren't committed.

## Confidence scoring

The agent scores each extraction based on: has tests? (40%), test coverage
(30%), has docstrings? (20%), clear assertions? (10%).

- **100%** — excellent, comprehensive tests and docs
- **70–99%** — good, some tests, partial coverage
- **40–69%** — fair, minimal tests, may need manual review
- **<40%** — low, code without tests — extraction is speculative

## Analysis strategies

**Code analysis** extracts class names, method signatures (names,
parameters, return types), constructor parameters, docstrings, and type
hints.

**Test analysis** extracts test function names, setup actions (Given),
actions under test (When), assertions (Then), and test docstrings — matched
against the pattern table below.

| Test Pattern | Gherkin Step |
|---|---|
| `obj = Class(params)` | `Given a {class} with {params}` |
| `result = obj.method(args)` | `When I {method} with {args}` |
| `assert result == expected` | `Then {result} should be {expected}` |
| `assert value in collection` | `Then {collection} should contain {value}` |
| `assert value is not None` | `Then {value} should not be empty` |

## Current scope and limitations

- **Python AST only** as the extraction source — no other source languages
  are analyzed today.
- **Go is the only generated target** (`GoStepGenerator`). Extending to
  other Cucumber-family targets (Rust, Java, TypeScript, C#) would follow
  the same generator pattern but isn't implemented.
- **Simple pattern matching**, not LLM-based semantic understanding, drives
  test → Gherkin conversion.
- Generated step implementations are scaffolds — a human (or the TDD agent)
  still has to fill them in.
- Single-file analysis only; no fixture/parametrized-test support yet.

## Quick start

```python
from src.agents.gherkin_extraction_agent import GherkinExtractionAgent

agent = GherkinExtractionAgent()
result = agent.extract_from_codebase(
    code_path=Path("my_module.py"),
    test_path=Path("test_my_module.py"),
)

agent.write_gherkin_file(result.feature, Path("my_module.feature"))
agent.write_step_definitions(
    result.step_definitions,
    result.code_analysis,
    Path("steps/my_module_steps.py"),
)
```

```python
from src.agents.go_step_generator import GoStepGenerator

generator = GoStepGenerator(package_name="steps")
generator.generate_from_feature_file(
    feature_path=Path("my_module.feature"),
    output_dir=Path("go_impl/steps"),
)
generator.generate_test_runner(
    output_dir=Path("go_impl/steps"),
    feature_name="my_module",
)
```
