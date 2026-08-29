Feature: Playbook-backed Q&A

  Scenario: Asking a question when relevant playbook bullets exist
    Given a PlaybookQA instance with a playbook containing bullets relevant to "How do I handle exceptions in Python?"
    When I ask "How do I handle exceptions in Python?"
    Then the returned answer's question is "How do I handle exceptions in Python?"
    And the returned answer's sources list is not empty
    And the returned answer's confidence is between 0.3 and 0.95
    And the returned answer's model_id is "ollama/qwen2.5-coder:1.5b"
    And the returned answer's consensus is None

  Scenario: Asking a question with no matching playbook knowledge
    Given a PlaybookQA instance with no playbooks loaded
    When I ask "What is the capital of France?"
    Then the returned answer's sources list is empty
    And the returned answer's confidence is 0.3
    And the returned answer's playbook_coverage is 0.0
    And the returned answer's model_id is "ollama/qwen2.5-coder:1.5b"

  Scenario: Filtering playbook knowledge by domain
    Given a PlaybookQA instance with playbooks in domains "python_development" and "javascript_development"
    When I ask "How do I write a decorator?" with domain "python_development"
    Then the returned answer's sources only include bullets from the "python_development" domain

  Scenario: Playbook coverage reflects the ratio of retrieved bullets to requested top_k
    Given a PlaybookQA instance with a playbook containing 3 relevant bullets
    When I ask "How do I test async code?" with top_k 5
    Then the returned answer's playbook_coverage is 0.6

  Scenario: Requesting an ensemble answer from multiple models
    Given a PlaybookQA instance with a playbook containing relevant bullets
    When I ask_ensemble "How do I write a REST API?" using models [("ollama", "qwen2.5-coder:1.5b"), ("openai", "gpt-4")]
    Then the returned answer's consensus contains the keys "models", "answers", "selected", and "agreement"
    And the returned answer's consensus "models" list contains "ollama/qwen2.5-coder:1.5b" and "openai/gpt-4"
    And the returned answer's model_id is None

  Scenario: Ensemble consensus agreement is perfect when only one model answers successfully
    Given a PlaybookQA instance with a playbook containing relevant bullets
    When I ask_ensemble "How do I write a REST API?" using a single model [("ollama", "qwen2.5-coder:1.5b")]
    Then the returned answer's consensus "agreement" is 1.0
    And the returned answer's consensus "selected" is "ollama/qwen2.5-coder:1.5b"

  Scenario: Custom default model is used when none specified at call time
    Given a PlaybookQA instance constructed with default_model ("openai", "gpt-4o")
    When I ask "How do I write a decorator?"
    Then the returned answer's model_id is "openai/gpt-4o"