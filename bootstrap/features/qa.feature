Feature: Playbook Q&A System
  As a developer using the playbook system
  I want to ask coding questions and get answers informed by playbook knowledge
  So that I can leverage learned patterns and best practices

  Scenario: Ask a question with relevant playbook knowledge available
    Given a PlaybookQA system is initialized with a playbook manager
    And the playbook manager contains bullets in the "python_development" domain
    When I call ask with question "How do I handle exceptions?" and domain "python_development" and topK 5
    Then a QAAnswer is returned
    And the answer question field equals "How do I handle exceptions?"
    And the answer answer field contains generated text
    And the answer confidence is between 0.0 and 1.0
    And the answer sources list contains Bullet objects
    And the answer modelId matches the pattern "provider/model_name"
    And the answer playbookCoverage is calculated as sources length divided by topK

  Scenario: Ask a question when no playbook knowledge is available
    Given a PlaybookQA system is initialized with a playbook manager
    And the playbook manager contains no bullets
    When I call ask with question "What is Python?"
    Then a QAAnswer is returned
    And the answer confidence equals 0.3
    And the answer sources list is empty
    And the answer playbookCoverage equals 0.0
    And the answer answer field contains fallback generated text

  Scenario: Ask a question with custom default model
    Given a PlaybookQA system is initialized with defaultModel tuple ("openai", "gpt-4")
    When I call ask with question "How do I write tests?"
    Then a QAAnswer is returned
    And the answer modelId equals "openai/gpt-4"

  Scenario: Ask a question without specifying domain
    Given a PlaybookQA system is initialized with a playbook manager
    And the playbook manager contains bullets across multiple domains
    When I call ask with question "Best practices?" and domain None
    Then a QAAnswer is returned
    And the answer sources may contain bullets from any domain

  Scenario: Ask ensemble question with multiple models
    Given a PlaybookQA system is initialized with a playbook manager
    And the playbook manager contains bullets
    When I call askEnsemble with question "How to optimize code?" and models list [("ollama", "qwen2.5-coder:1.5b"), ("ollama", "codellama:7b")] and domain None and topK 5
    Then a QAAnswer is returned
    And the answer consensus field is a dictionary
    And the consensus dictionary contains key "models" with list of model IDs
    And the consensus dictionary contains key "answers" with model ID to answer text mapping
    And the consensus dictionary contains key "selected" with the chosen model ID
    And the consensus dictionary contains key "agreement" with float between 0.0 and 1.0
    And the answer answer field equals the answer from the selected model
    And the answer modelId is None

  Scenario: Ask ensemble question when all models fail
    Given a PlaybookQA system is initialized with a playbook manager
    When I call askEnsemble with question "Test question" and models list containing invalid model configurations
    Then a QAAnswer is returned
    And the answer confidence equals 0.3
    And the answer sources list is empty
    And the answer consensus field is None

  Scenario: Calculate confidence based on bullet count and helpful counts
    Given a PlaybookQA system is initialized with a playbook manager
    And the playbook manager contains 5 bullets with helpfulCount values [10, 5, 3, 2, 1]
    When I call ask with question "How do I do X?" and topK 5
    Then a QAAnswer is returned
    And the answer confidence is greater than 0.3
    And the answer confidence reflects both bullet count and average helpfulCount

  Scenario: Calculate playbook coverage ratio
    Given a PlaybookQA system is initialized with a playbook manager
    And the playbook manager contains 3 relevant bullets for a query
    When I call ask with question "Sample question" and topK 10
    Then a QAAnswer is returned
    And the answer playbookCoverage equals 0.3