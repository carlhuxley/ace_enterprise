Feature: Project-aware TDD with file routing
  As a developer using ACE
  I want the TDD agent to route files to correct directories
  So that code is organized according to project structure

  Scenario: Route files based on feature keywords
    Given a FilePlacementRouter class
    When I call route_file with requirement "Add new broker for routing"
    Then it should return "src/broker" as the target directory

  Scenario: Route agent files to agents directory
    Given a FilePlacementRouter class
    When I call route_file with requirement "Create autonomous agent"
    Then it should return "src/agents" as the target directory

  Scenario: Route storage files to storage directory
    Given a FilePlacementRouter class
    When I call route_file with requirement "Add repository for data"
    Then it should return "src/storage" as the target directory

  Scenario: Default to src for unknown keywords
    Given a FilePlacementRouter class
    When I call route_file with requirement "Add something new"
    Then it should return "src" as the target directory
