Feature: Generator task execution using playbook context

  Scenario: Execute a task successfully using an existing playbook
    Given a playbook with id "playbook-123" exists
    And a task with id "task-1" and query "How do I fix a null pointer exception?"
    When the generator executes the task against playbook "playbook-123"
    Then a generator output is returned with a non-empty solution
    And the output includes a latency measurement in milliseconds
    And the output includes a token usage count

  Scenario: Executing a task against a non-existent playbook raises an error
    Given no playbook exists with id "missing-playbook"
    And a task with id "task-2" and query "Summarize this document"
    When the generator executes the task against playbook "missing-playbook"
    Then a ValueError is raised with message "Playbook missing-playbook not found"

  Scenario: Executed task tracks which playbook bullets were used
    Given a playbook with id "playbook-123" contains bullets relevant to "database timeouts"
    And a task with id "task-3" and query "Why is my database timing out?"
    When the generator executes the task against playbook "playbook-123"
    Then the generator output includes a list of bullet ids that were used
    And each used bullet has an associated feedback value of "neutral"

  Scenario: Generation failure is handled gracefully instead of raising
    Given a playbook with id "playbook-123" exists
    And a task with id "task-4" and query "Trigger a generation failure"
    And the underlying language model will fail to generate a response
    When the generator executes the task against playbook "playbook-123"
    Then a generator output is still returned instead of an exception
    And the output solution contains the text "Error: LLM generation failed"
    And the output token usage is 0

  Scenario: Updating bullet feedback after a task outcome
    Given a playbook with id "playbook-123" exists
    And bullet "bullet-42" was used in a previous task execution
    When the generator updates bullet feedback for playbook "playbook-123" with bullet "bullet-42" marked as "helpful"
    Then no error is raised and the feedback update completes

  Scenario: Updating bullet feedback for an unknown bullet does not raise
    Given a playbook with id "playbook-123" exists
    And bullet id "bullet-unknown" does not exist in the playbook
    When the generator updates bullet feedback for playbook "playbook-123" with bullet "bullet-unknown" marked as "harmful"
    Then no exception propagates to the caller

  Scenario: Retrieving generator statistics
    Given a generator has been initialized with a configured language model client and retriever
    When the caller requests generator statistics
    Then the statistics include the provider name
    And the statistics include the model name
    And the statistics include the retriever's top_k value
    And the statistics include the retriever's similarity threshold