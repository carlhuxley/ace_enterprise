Feature: Curator synthesizes reflector insights into playbook delta bullets

  Scenario: Curating insights for an existing playbook produces delta bullets and reasoning
    Given a playbook manager containing playbook "playbook-123" with domain "backend-development"
    And a reflector output with key insight "Always validate input before processing"
    When the curator curates insights for playbook "playbook-123"
    Then the result contains a list of delta bullets
    And the result contains a non-empty reasoning string

  Scenario: Curating insights for a playbook that does not exist raises an error
    Given a playbook manager with no playbook registered under id "missing-playbook"
    And a reflector output with key insight "Cache results to avoid repeated calls"
    When the curator curates insights for playbook "missing-playbook"
    Then a ValueError is raised indicating playbook "missing-playbook" was not found

  Scenario: Task context values are stamped onto every generated delta bullet
    Given a playbook manager containing playbook "playbook-123"
    And a reflector output with root cause "Missing null check in parser"
    And a task context with team_id "team-alpha", project_ids ["proj-1", "proj-2"], applicable_domains ["parsing"], and tech_context "python"
    When the curator curates insights for playbook "playbook-123" with that task context
    Then every delta bullet in the result has team_id "team-alpha"
    And every delta bullet in the result has project_ids ["proj-1", "proj-2"]
    And every delta bullet in the result has applicable_domains ["parsing"]
    And every delta bullet in the result has tech_context "python"

  Scenario: LLM synthesis failure yields an empty bullet list and a failure reasoning message
    Given a playbook manager containing playbook "playbook-123"
    And an LLM client that raises an error when generating a response
    And a reflector output with error identification "Timeout during API call"
    When the curator curates insights for playbook "playbook-123"
    Then the result contains zero delta bullets
    And the reasoning string contains "Synthesis failed"

  Scenario: Applying curator output adds delta bullets to the playbook and returns their new ids
    Given a playbook manager containing playbook "playbook-123"
    And a curator output with 2 delta bullets
    When the curator applies the updates to playbook "playbook-123"
    Then the playbook manager records 2 new bullets added to playbook "playbook-123"
    And the curator returns a list of 2 bullet ids

  Scenario: Curator statistics report the configured LLM provider, model, and budget settings
    Given a curator configured with token_budget_per_section 500 and enable_redundancy_checking true
    When the caller requests curator statistics
    Then the statistics include the LLM provider name
    And the statistics include the LLM model name
    And the statistics include token_budget_per_section 500
    And the statistics include enable_redundancy_checking true

  Scenario: Curating with no task context still returns delta bullets with unset provenance fields
    Given a playbook manager containing playbook "playbook-123"
    And a reflector output with correct approach "Use retries with exponential backoff"
    When the curator curates insights for playbook "playbook-123" without supplying a task context
    Then every delta bullet in the result has no team_id set
    And every delta bullet in the result has no project_ids set