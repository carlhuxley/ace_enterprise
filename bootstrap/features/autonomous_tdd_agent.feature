Feature: Autonomous TDD Agent
  As a software development system
  I want to build features autonomously using Test-Driven Development
  So that I can produce tested, working code incrementally

  Scenario: Build a simple feature from natural language requirement
    Given an autonomous TDD agent configured with a test directory and source directory
    And a natural language requirement "Calculator that adds two numbers"
    When I call build_feature with the requirement
    Then the agent should create test files in the test directory
    And the agent should create implementation files in the source directory
    And all tests should pass
    And the TDD result should indicate cycles were executed
    And the TDD result should indicate all tests passed

  Scenario: Build feature with explicit file path constraint
    Given an autonomous TDD agent configured with project directories
    And a Gherkin feature file with Background specifying "Implementation file: src/broker/oauth.py"
    And a requirement "OAuth client for authorization"
    When I call build_feature with the requirement and gherkin directory
    Then the implementation file should be created at "src/broker/oauth.py"
    And the implementation should contain the specified class
    And all tests should pass

  Scenario: Build feature with explicit class name constraint
    Given an autonomous TDD agent configured with project directories
    And a Gherkin feature file with Background specifying "Class name: OAuthClient"
    And a requirement "OAuth authentication handler"
    When I call build_feature with the requirement and gherkin directory
    Then the implementation should contain a class named "OAuthClient"
    And all tests should pass

  Scenario: Skip redundant test during pre-check
    Given an autonomous TDD agent with existing tests
    And existing test "test_calculator_can_be_created" that creates a Calculator instance
    And a proposed test "test_calculator_instance_creation" with description "Test that Calculator can be instantiated"
    When the agent determines the next increment
    Then the cycle should be skipped
    And the skip reason should indicate redundancy
    And no new test code should be written

  Scenario: Refine test that passes unexpectedly in RED phase
    Given an autonomous TDD agent in a TDD cycle
    And a test that passes immediately when it should fail
    And the test has been refined fewer than 3 times
    When the RED phase detects the unexpected pass
    Then the agent should analyze the redundancy pattern
    And the agent should refine the test to make it more specific
    And the agent should store a redundancy pattern bullet in the playbook
    And the refined test should be reloaded and executed

  Scenario: Stop after maximum iterations reached
    Given an autonomous TDD agent with max_iterations set to 5
    And a requirement that would need 10 cycles to complete
    When I call build_feature with the requirement
    Then the agent should execute exactly 5 cycles
    And the agent should log a warning about reaching max_iterations
    And the TDD result should show 5 cycles executed

  Scenario: Retry GREEN phase on implementation failure
    Given an autonomous TDD agent in GREEN phase
    And an implementation that fails to pass the test
    And fewer than 3 GREEN retry attempts have been made
    When the GREEN phase detects test failure
    Then the agent should analyze the failure
    And the agent should store a failure analysis bullet in the playbook
    And the agent should retry implementation with failure context
    And the retry attempt counter should increment

  Scenario: Rollback implementation on regression
    Given an autonomous TDD agent with passing tests from previous cycles
    And a new implementation that breaks an existing test
    When the GREEN phase detects the regression
    Then the agent should restore the previous implementation code
    And the cycle should be marked as skipped
    And the skip reason should indicate regression with test count
    And the rolled-back implementation should be returned in the cycle result

  Scenario: Learn patterns from successful cycle
    Given an autonomous TDD agent with ensemble learning enabled
    And a completed TDD cycle with passing tests
    And test quality score above the review threshold
    When the LEARN phase executes
    Then the agent should extract reusable patterns from the cycle
    And approved patterns should be added to the playbook
    And the cycle result should include the learned bullets

  Scenario: Retrieve playbook guidance for test planning
    Given an autonomous TDD agent with a populated playbook
    And the playbook contains bullets about "test redundancy anti-patterns"
    When the agent determines the next test increment
    Then the agent should retrieve relevant bullets from the playbook
    And the retrieved bullets should be injected into the planning prompt
    And the planning should avoid patterns flagged in the playbook

  Scenario: Complete feature when LLM signals COMPLETE
    Given an autonomous TDD agent executing cycles
    And all core functionality has been implemented
    And all tests are passing
    When the agent determines the next increment
    And the LLM response contains "COMPLETE"
    Then the agent should stop executing cycles
    And the TDD result should indicate the requirement is satisfied
    And the final test count should match all created tests

  Scenario: Handle subprocess-style Gherkin scenarios
    Given an autonomous TDD agent with a Gherkin feature file
    And the Gherkin contains steps like "When I run python -m task_manager add Buy milk"
    When the agent parses the Gherkin scenarios
    Then the agent should detect it as a subprocess feature
    And the agent should generate subprocess integration tests
    And the tests should use subprocess.run with sys.executable
    And the tests should pass cwd and isolated tmp_path

  Scenario: Validate and fix import paths in generated code
    Given an autonomous TDD agent generating implementation code
    And the generated code contains an invalid import path
    When the agent writes the implementation file
    Then the import validator should detect the invalid import
    And the import validator should fix the import path
    And the corrected import should be written to the file
    And the agent should log the correction

  Scenario: Emit audit events for TDD cycles
    Given an autonomous TDD agent with audit client configured
    And a TDD cycle completes successfully
    When the cycle logging executes
    Then an audit event should be emitted
    And the event should include cycle number and test name
    And the event should include playbook ID and project ID
    And the event should include model and provider information

  Scenario: Promote session bullet after GREEN success
    Given an autonomous TDD agent with playbook manager
    And a TDD cycle completes GREEN phase successfully
    When the session bullet promotion executes
    Then a session-wins bullet should be created
    And the bullet should contain cycle number and test name
    And the bullet should be added to the playbook via curator
    And the bullet should be tagged with "tdd" and "session-win"

  Scenario: Load existing test context from disk
    Given an autonomous TDD agent starting a new session
    And test files exist in the test directory from a previous run
    And the test files contain valid Python syntax
    And the test files have resolvable imports
    When the agent loads existing context
    Then the agent should parse existing test functions
    And the agent should track them in test_functions dictionary
    And the agent should log the count of loaded tests

  Scenario: Skip loading broken test files from disk
    Given an autonomous TDD agent starting a new session
    And a test file exists with syntax errors
    When the agent loads existing context
    Then the agent should skip the broken file
    And the agent should log a warning about the syntax error
    And the broken file should not be added to test_functions

  Scenario: Assemble test file with proper imports
    Given an autonomous TDD agent with tracked test functions
    And an implementation file at "src/calculator.py"
    When the agent assembles the test file
    Then the test file should include pytest imports
    And the test file should include Mock and patch imports
    And the test file should import from the correct module path
    And the test file should contain all tracked test functions

  Scenario: Determine implementation path with explicit constraint
    Given an autonomous TDD agent with explicit_file_path set to "src/broker/oauth.py"
    When the agent determines the implementation path
    Then the path should be "src/broker/oauth.py" relative to project root
    And the path should ignore the LLM-suggested filename
    And the parent directories should be created if they don't exist

  Scenario: Determine implementation path without constraint
    Given an autonomous TDD agent with no explicit file path
    And a test description "OAuth client for authorization"
    When the agent determines the implementation path
    Then the path should be determined by project structure analysis
    And the path should use the LLM-suggested filename
    And the file should be placed in an appropriate subdirectory

  Scenario: Count functions in generated code
    Given an autonomous TDD agent validating generated code
    And code containing 3 function definitions
    When the agent counts functions in the code
    Then the count should be 3

  Scenario: Extract single function from multi-function code
    Given an autonomous TDD agent with code containing multiple functions
    And the target function name is "test_calculator_add"
    When the agent extracts the single function
    Then only the "test_calculator_add" function should be returned
    And other functions should be excluded

  Scenario: Run tests with pytest
    Given an autonomous TDD agent with test files in the test directory
    When the agent runs tests
    Then pytest should be invoked with the test directory
    And the PYTHONPATH should include the project root
    And the result should include pass/fail status
    And the result should include test count and failed count
    And the result should include output and error messages

  Scenario: Handle test execution timeout
    Given an autonomous TDD agent running tests
    And the tests take longer than 30 seconds
    When the test execution times out
    Then the result should indicate failure
    And the error should mention timeout

  Scenario: Get module path from file path
    Given an autonomous TDD agent with a file path "src/playbook/markdown_importer.py"
    When the agent gets the module path
    Then the module path should be "src.playbook.markdown_importer"

  Scenario: Get module path with explicit constraint
    Given an autonomous TDD agent with explicit_file_path set to "src/broker/oauth.py"
    When the agent gets the module path
    Then the module path should be "src.broker.oauth"
    And the explicit constraint should take precedence over the file path argument

  Scenario: Map open-source provider to license type
    Given an autonomous TDD agent using provider "ollama" and model "qwen2.5-coder"
    When the agent determines the license type
    Then the license type should be "apache-2.0"

  Scenario: Map proprietary provider to license type
    Given an autonomous TDD agent using provider "openai" and model "gpt-4"
    When the agent determines the license type
    Then the license type should be "proprietary"
    And a warning should be logged about proprietary provider

  Scenario: Raise error for unknown provider
    Given an autonomous TDD agent using provider "unknown_provider"
    When the agent determines the license type
    Then a ValueError should be raised
    And the error message should list allowed providers

  Scenario: Collect test files from test directory
    Given an autonomous TDD agent with test files created
    And files named "test_calculator.py" and "test_oauth.py" exist
    When the agent collects test files
    Then the list should contain both test files
    And the files should be Path objects

  Scenario: Collect implementation files from source directory
    Given an autonomous TDD agent with implementation files created
    And files named "calculator.py" and "oauth.py" exist in src
    When the agent collects implementation files
    Then the list should contain both implementation files
    And the files should be Path objects

  Scenario: Parse Gherkin scenarios into structured format
    Given an autonomous TDD agent with Gherkin content containing 2 scenarios
    And each scenario has Given, When, Then steps
    When the agent parses the Gherkin scenarios
    Then the result should be a list of 2 scenario dictionaries
    And each scenario should have a name and steps list
    And each step should have a type and text

  Scenario: Handle And and But steps in Gherkin parsing
    Given an autonomous TDD agent with Gherkin content
    And a scenario with "Given X" followed by "And Y"
    When the agent parses the Gherkin scenarios
    Then the "And Y" step should have type "Given"
    And the "And Y" step should preserve the continuation context

  Scenario: Build session bullet for successful cycle
    Given an autonomous TDD agent with a completed cycle
    And the cycle number is 3
    And the test name is "test_oauth_generate_url"
    When the agent builds a session bullet
    Then the bullet should be in "session-wins" section
    And the bullet content should include cycle number and test name
    And the bullet should be tagged with "tdd" and "session-win"

  Scenario: Analyze redundancy pattern with semantic learning
    Given an autonomous TDD agent with a test that passed unexpectedly
    And the test code and implementation state
    When the agent analyzes the redundancy pattern
    Then the analysis should identify the pattern name
    And the analysis should explain the redundancy type
    And the analysis should provide guidance on how to avoid it
    And the analysis should include good and bad examples

  Scenario: Apply test correction for malformed test
    Given an autonomous TDD agent with a malformed test
    And a correction description from failure analysis
    When the agent applies the test correction
    Then the test function should be updated in test_functions
    And the test file should be reassembled with the correction
    And the method should return True on success

  Scenario: Get implementation context from context map
    Given an autonomous TDD agent with a context map configured
    And failing test IDs that reference specific modules
    When the agent gets implementation context
    Then the context should include AST signatures for relevant modules
    And the signatures should be compact without function bodies

  Scenario: Return empty context when no context map configured
    Given an autonomous TDD agent with no context map
    When the agent gets implementation context
    Then the result should be an empty string

  Scenario: Write minimal code using ACE pipeline
    Given an autonomous TDD agent in GREEN phase
    And a failing test result from RED phase
    When the agent writes minimal code
    Then the Generator should retrieve playbook bullets
    And the generated code should be extracted from the response
    And import paths should be validated and fixed
    And the code should be written to the implementation file
    And the method should return the code and bullet IDs used

  Scenario: Refine test to fail after unexpected pass
    Given an autonomous TDD agent with a test that passed in RED
    And redundancy analysis explaining why it passed
    And the current implementation code
    When the agent refines the test to fail
    Then the refined test should have stricter assertions
    And the refined test should test deeper behavior
    And the refined test should keep the same test name
    And the refined test should be valid Python code

  Scenario: Analyze GREEN failure for test quality issues
    Given an autonomous TDD agent after multiple GREEN failures
    And test code and implementation code
    And an error message from the failure
    When the agent analyzes the GREEN failure
    Then the analysis should detect if the test is malformed
    And the analysis should identify the technical domain
    And the analysis should provide a knowledge summary
    And the analysis should indicate if the test needs correction

  Scenario: Skip learning when test quality is below threshold
    Given an autonomous TDD agent with review_threshold set to 0.7
    And a completed cycle with test quality score of 0.5
    When the LEARN phase executes
    Then the agent should skip learning
    And the agent should log a warning about low test quality
    And the learned bullets list should be empty

  Scenario: Record failure context for self-healing
    Given an autonomous TDD agent with failure recorder
    And a GREEN phase failure after max retries
    When the cycle fails
    Then a failure context should be recorded
    And the context should include feature requirement and cycle number
    And the context should include error message and error type
    And the context should include test and implementation file paths
    And the context should include model and provider information

  Scenario: Override directories for build_feature
    Given an autonomous TDD agent with default directories
    And custom project_root, source_dir, and test_dir provided
    When I call build_feature with directory overrides
    Then the agent should use the provided project_root
    And the agent should use the provided source_dir
    And the agent should use the provided test_dir
    And files should be created in the overridden directories

  Scenario: Read Gherkin scenarios from feature file
    Given an autonomous TDD agent with a gherkin directory
    And a feature file exists in the directory
    When the agent reads Gherkin scenarios
    Then the content should be returned as a string
    And the content should contain scenario definitions

  Scenario: Handle missing Gherkin feature file gracefully
    Given an autonomous TDD agent with a gherkin directory
    And no feature files exist in the directory
    When the agent attempts to read Gherkin scenarios
    Then the agent should log that no feature file was found
    And the agent should proceed with emergent planning

  Scenario: Extract explicit constraints from Gherkin Background
    Given an autonomous TDD agent with Gherkin content
    And the Gherkin Background specifies "Class name: OAuthClient"
    And the G