Feature: Go Language Pod TDD Cycle Management

  Scenario: RED phase generates failing test code and runs go test
    Given an LLM client that returns Go test code with 150 tokens used
    And a PodSpec with cycle_number 1, feature_requirement "calculate sum", test_file "calc_test.go", and implementation_file "calc.go"
    When run_red is called with the PodSpec
    Then the test file is created with the generated Go test code
    And go test is executed in the test file's parent directory
    And a PhaseResult is returned with passed status matching the test exit code
    And token_usage returns a list containing one TokenUsage entry with cycle_number 1 and input_tokens 150

  Scenario: RED phase handles LLM generation failure
    Given an LLM client that raises an exception "API timeout"
    And a PodSpec with cycle_number 2, feature_requirement "parse JSON", test_file "parser_test.go", and implementation_file "parser.go"
    When run_red is called with the PodSpec
    Then a PhaseResult is returned with passed False, empty output, and error "API timeout"
    And token_usage returns a list containing one TokenUsage entry with cycle_number 2

  Scenario: GREEN phase generates implementation code with default Go bullets
    Given an LLM client that returns Go implementation code with 200 tokens used
    And a PodSpec with cycle_number 3, feature_requirement "validate email", test_file "email_test.go", and implementation_file "email.go"
    And no playbook manager is provided
    When run_green is called with the PodSpec
    Then the implementation file is created with the generated Go code
    And the GREEN prompt includes default Go idioms about errors.New, implicit interfaces, and channels
    And go test is executed in the implementation file's parent directory
    And a PhaseResult is returned with passed status matching the test exit code
    And token_usage returns a list containing one TokenUsage entry with cycle_number 3 and input_tokens 200

  Scenario: GREEN phase uses custom bullets from playbook manager
    Given an LLM client that returns Go implementation code with 180 tokens used
    And a playbook manager that returns bullets "avoid global state" and "use context.Context for cancellation" for section "global-go-bullets"
    And a PodSpec with cycle_number 4, feature_requirement "fetch data", test_file "fetch_test.go", and implementation_file "fetch.go"
    When run_green is called with the PodSpec
    Then the GREEN prompt includes the custom Go idioms from the playbook manager
    And the implementation file is created with the generated Go code
    And token_usage returns a list containing one TokenUsage entry with cycle_number 4 and input_tokens 180

  Scenario: GREEN phase falls back to default bullets when playbook manager returns empty
    Given an LLM client that returns Go implementation code with 175 tokens used
    And a playbook manager that returns an empty list for section "global-go-bullets"
    And a PodSpec with cycle_number 5, feature_requirement "encode base64", test_file "encode_test.go", and implementation_file "encode.go"
    When run_green is called with the PodSpec
    Then the GREEN prompt includes default Go idioms about errors.New, implicit interfaces, and channels
    And token_usage returns a list containing one TokenUsage entry with cycle_number 5 and input_tokens 175

  Scenario: REFACTOR phase runs gofmt and go vet then executes tests
    Given a PodSpec with cycle_number 6, feature_requirement "sort items", test_file "sort_test.go", and implementation_file "sort.go"
    And the implementation file exists on disk
    When run_refactor is called with the PodSpec
    Then gofmt is executed with -w flag on the implementation file
    And go vet is executed with ./... in the implementation file's parent directory
    And go test is executed in the implementation file's parent directory
    And a PhaseResult is returned with passed status matching the test exit code
    And token_usage returns a list containing one TokenUsage entry with cycle_number 6 and input_tokens 0

  Scenario: Token usage accumulates across multiple TDD cycles
    Given an LLM client that returns code with varying token counts
    And a PodSpec with cycle_number 7
    When run_red is called and uses 100 tokens
    And run_green is called and uses 250 tokens
    And run_refactor is called and uses 0 tokens
    Then token_usage returns a list with three TokenUsage entries
    And the entries have cycle_number 7 and input_tokens 100, 250, and 0 respectively

  Scenario: Code extraction handles markdown fenced code blocks
    Given an LLM client that returns content wrapped in ```go and ``` markers
    And a PodSpec with cycle_number 8, feature_requirement "multiply numbers", test_file "mult_test.go", and implementation_file "mult.go"
    When run_red is called with the PodSpec
    Then the test file contains only the code between the fences without the markers