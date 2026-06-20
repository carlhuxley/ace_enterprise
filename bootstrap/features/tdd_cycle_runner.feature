Feature: TDD Cycle Runner
  The TDD Cycle Runner orchestrates a complete RED-GREEN-REFACTOR cycle for a single feature,
  with retry logic for the GREEN phase and optional learning integration.

  Scenario: Successful RED-GREEN-REFACTOR cycle on first GREEN attempt
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a pod that returns passed=True for RED phase
    And a pod that returns passed=True for GREEN phase on first attempt
    And a pod that returns passed=True for REFACTOR phase
    When run is called with a PodSpec containing feature_requirement "Add user login"
    Then the returned CycleResult has success=True
    And the CycleResult has green_attempts=1
    And the CycleResult has error=None
    And the CycleResult contains red_result with passed=True
    And the CycleResult contains green_result with passed=True
    And the CycleResult contains refactor_result with passed=True

  Scenario: GREEN phase succeeds after retry with error feedback
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a pod that returns passed=True for RED phase
    And a pod that returns passed=False with output "NameError: x undefined" for GREEN phase on first attempt
    And a pod that returns passed=True for GREEN phase on second attempt
    And a pod that returns passed=True for REFACTOR phase
    When run is called with a PodSpec
    Then the returned CycleResult has success=True
    And the CycleResult has green_attempts=2
    And the CycleResult has error=None

  Scenario: GREEN phase fails after exhausting all retry attempts
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a pod that returns passed=True for RED phase
    And a pod that returns passed=False with error "SyntaxError" for GREEN phase on all attempts
    When run is called with a PodSpec
    Then the returned CycleResult has success=False
    And the CycleResult has green_attempts=3
    And the CycleResult has error="SyntaxError"
    And the CycleResult has refactor_result=None

  Scenario: RED phase aborts on security violation
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a pod that returns passed=False with error "ForbiddenImport: os.system detected" for RED phase
    When run is called with a PodSpec
    Then the returned CycleResult has success=False
    And the CycleResult has green_attempts=0
    And the CycleResult has error="RED aborted: ForbiddenImport: os.system detected"
    And the CycleResult green_result has error="skipped"
    And the CycleResult has refactor_result=None

  Scenario: GREEN phase aborts immediately on security breach without retry
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a pod that returns passed=True for RED phase
    And a pod that returns passed=False with error "SecurityBreach: eval() usage" for GREEN phase
    When run is called with a PodSpec
    Then the returned CycleResult has success=False
    And the CycleResult has green_attempts=1
    And the CycleResult has error="SecurityBreach: eval() usage"
    And the CycleResult has refactor_result=None

  Scenario: REFACTOR phase fails after successful GREEN
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a pod that returns passed=True for RED phase
    And a pod that returns passed=True for GREEN phase
    And a pod that returns passed=False with error "Linting failed" for REFACTOR phase
    When run is called with a PodSpec
    Then the returned CycleResult has success=False
    And the CycleResult has green_attempts=1
    And the CycleResult has error="Linting failed"
    And the CycleResult green_result has passed=True
    And the CycleResult refactor_result has passed=False

  Scenario: Learning loop executes after successful GREEN phase
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a reflector that produces reflection output
    And a curator that produces 2 delta bullets
    And a playbook_id set to "test_playbook"
    And a pod that returns passed=True for RED, GREEN, and REFACTOR phases
    When run is called with a PodSpec
    Then the returned CycleResult has success=True
    And the CycleResult learned_bullets contains 2 items

  Scenario: Token usage is captured across all phases
    Given a TDDCycleRunner with max_green_attempts set to 3
    And a pod that accumulates token usage with 100 input tokens and 50 output tokens for RED
    And a pod that accumulates token usage with 200 input tokens and 150 output tokens for GREEN
    And a pod that accumulates token usage with 80 input tokens and 40 output tokens for REFACTOR
    When run is called with a PodSpec
    Then the returned CycleResult token_usage list contains 3 TokenUsage entries
    And the total tokens across all entries equals 620