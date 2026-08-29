Feature: Polyglot pod kwargs builder

  Scenario: Build pod kwargs for Python
    Given a project root directory "/repo/myproject" containing Python source files
    And a valid LLM client instance
    When I call build_pod_kwargs with language "python", the project root, and the LLM client
    Then the returned dictionary contains keys "worker", "project_root", and "orchestrator"
    And "project_root" equals "/repo/myproject"

  Scenario: Build pod kwargs for TypeScript
    Given a project root directory "/repo/myproject"
    And a valid LLM client instance
    When I call build_pod_kwargs with language "typescript", the project root, and the LLM client
    Then the returned dictionary contains keys "worker", "project_root", and "orchestrator"
    And "project_root" equals "/repo/myproject"

  Scenario: Build pod kwargs for Go
    Given a project root directory "/repo/myproject"
    And a valid LLM client instance
    When I call build_pod_kwargs with language "go", the project root, and the LLM client
    Then the returned dictionary contains keys "llm_client", "project_root", and "orchestrator"
    And "llm_client" equals the provided LLM client instance
    And "project_root" equals "/repo/myproject"

  Scenario: Requesting an unsupported language raises an error
    Given a project root directory "/repo/myproject"
    And a valid LLM client instance
    When I call build_pod_kwargs with language "ruby", the project root, and the LLM client
    Then a ValueError is raised
    And the error message mentions "Unsupported language" and "ruby"
    And the error message lists "python", "typescript", and "go" as supported languages

  Scenario: Building kwargs for multiple languages at once
    Given a project root directory "/repo/myproject"
    And a valid LLM client instance
    When I call build_all_pod_kwargs with languages ["python", "typescript", "go"], the project root, and the LLM client
    Then the returned dictionary has keys "python", "typescript", and "go"
    And each value is the same dictionary that build_pod_kwargs would return for that language

  Scenario: build_all_pod_kwargs propagates errors for unsupported languages
    Given a project root directory "/repo/myproject"
    And a valid LLM client instance
    When I call build_all_pod_kwargs with languages ["python", "cobol"], the project root, and the LLM client
    Then a ValueError is raised
    And the error message mentions "Unsupported language" and "cobol"

  Scenario: Custom src_dir is accepted for Python without changing the returned keys
    Given a project root directory "/repo/myproject"
    And a separate source directory "/repo/myproject/src" containing Python files
    And a valid LLM client instance
    When I call build_pod_kwargs with language "python", the project root, the LLM client, and src_dir "/repo/myproject/src"
    Then the returned dictionary contains keys "worker", "project_root", and "orchestrator"
    And "project_root" equals "/repo/myproject"

  Scenario: Omitting src_dir defaults to using the project root
    Given a project root directory "/repo/myproject" containing Python source files
    And a valid LLM client instance
    When I call build_pod_kwargs with language "python", the project root, and the LLM client, without specifying src_dir
    Then the returned dictionary contains keys "worker", "project_root", and "orchestrator"
    And "project_root" equals "/repo/myproject"