Feature: Production Data Analyzer

  Scenario: Extract model performance with no experiment data
    Given a ProductionDataAnalyzer instance
    And the repository contains no experiment logs
    When extractModelPerformance is called with days 30
    Then an empty dictionary is returned

  Scenario: Extract model performance from successful TDD cycles
    Given a ProductionDataAnalyzer instance
    And the repository contains an experiment log with:
      | field                          | value                          |
      | timestamp                      | 2024-01-15T10:00:00Z          |
      | result                         | SUCCESS                        |
      | taskData.type                 | tddCycle                      |
      | taskData.testName            | testCreateUser               |
      | generatorData.actualModel    | gemini-2.0-flash-001          |
      | generatorData.requestedModel | google/gemini-2.0-flash:free  |
      | generatorData.latencyMs      | 1500.0                         |
      | generatorData.tokensUsed     | 250                            |
      | generatorData.costUsd        | 0.001                          |
    When extractModelPerformance is called with days 30
    Then the returned dictionary contains key "google/gemini-2.0-flash:free"
    And the ModelPerformance for "google/gemini-2.0-flash:free" has taskCount 1
    And the ModelPerformance for "google/gemini-2.0-flash:free" has successCount 1
    And the ModelPerformance for "google/gemini-2.0-flash:free" has failedCount 0
    And the ModelPerformance for "google/gemini-2.0-flash:free" has totalLatencyMs 1500.0
    And the ModelPerformance for "google/gemini-2.0-flash:free" has totalTokens 250
    And the ModelPerformance for "google/gemini-2.0-flash:free" has totalCostUsd 0.001
    And the ModelPerformance for "google/gemini-2.0-flash:free" has successRate 1.0
    And the ModelPerformance for "google/gemini-2.0-flash:free" has avgLatencyMs 1500.0

  Scenario: Extract model performance with failed and error results
    Given a ProductionDataAnalyzer instance
    And the repository contains experiment logs:
      | timestamp            | result  | taskData.type | generatorData.actualModel |
      | 2024-01-15T10:00:00Z | SUCCESS | tddCycle      | claude-3-opus               |
      | 2024-01-15T11:00:00Z | FAILED  | tddCycle      | claude-3-opus               |
      | 2024-01-15T12:00:00Z | ERROR   | tddCycle      | claude-3-opus               |
    When extractModelPerformance is called with days 30
    Then the ModelPerformance for "anthropic/claude-3-opus" has taskCount 3
    And the ModelPerformance for "anthropic/claude-3-opus" has successCount 1
    And the ModelPerformance for "anthropic/claude-3-opus" has failedCount 1
    And the ModelPerformance for "anthropic/claude-3-opus" has errorCount 1
    And the ModelPerformance for "anthropic/claude-3-opus" has successRate 0.3333333333333333

  Scenario: Extract model performance categorizes tasks by type
    Given a ProductionDataAnalyzer instance
    And the repository contains experiment logs:
      | timestamp            | result  | taskData.type | taskData.testName      | generatorData.actualModel |
      | 2024-01-15T10:00:00Z | SUCCESS | tddCycle      | testCreateUser         | gpt-4                       |
      | 2024-01-15T11:00:00Z | SUCCESS | tddCycle      | testUpdateProfile      | gpt-4                       |
      | 2024-01-15T12:00:00Z | SUCCESS | tddCycle      | testDeleteAccount      | gpt-4                       |
      | 2024-01-15T13:00:00Z | SUCCESS | tddCycle      | testValidateEmail      | gpt-4                       |
    When extractModelPerformance is called with days 30
    Then the ModelPerformance for "openai/gpt-4" has tasksByType containing:
      | taskType  | count |
      | creation   | 1     |
      | update     | 1     |
      | deletion   | 1     |
      | validation | 1     |

  Scenario: Generate production report with multiple models
    Given a ProductionDataAnalyzer instance
    And the repository contains experiment logs:
      | timestamp            | result  | taskData.type | taskData.testName | generatorData.actualModel |
      | 2024-01-15T10:00:00Z | SUCCESS | tddCycle      | testCreateUser    | gemini-2.0-flash            |
      | 2024-01-15T11:00:00Z | SUCCESS | tddCycle      | testCreatePost    | gemini-2.0-flash            |
      | 2024-01-15T12:00:00Z | SUCCESS | tddCycle      | testCreateComment | gemini-2.0-flash            |
      | 2024-01-15T13:00:00Z | SUCCESS | tddCycle      | testUpdateUser    | claude-3-opus               |
      | 2024-01-15T14:00:00Z | FAILED  | tddCycle      | testUpdatePost    | claude-3-opus               |
      | 2024-01-15T15:00:00Z | SUCCESS | tddCycle      | testUpdateComment | claude-3-opus               |
    When generateReport is called with days 30
    Then the ProductionReport has totalCycles 6
    And the ProductionReport has uniqueModels 2
    And the ProductionReport has bestModelOverall "google/gemini-2.0-flash"
    And the ProductionReport has bestModelByTaskType containing:
      | taskType | model                   |
      | creation  | google/gemini-2.0-flash |
      | update    | anthropic/claude-3-opus |

  Scenario: Get raw data returns experiment records
    Given a ProductionDataAnalyzer instance
    And the repository contains an experiment log with:
      | field                          | value                    |
      | experimentId                  | exp-123                  |
      | timestamp                      | 2024-01-15T10:00:00Z    |
      | result                         | SUCCESS                  |
      | taskData.type                 | tddCycle                |
      | taskData.testName            | testCreateUser         |
      | generatorData.actualModel    | gpt-4                    |
      | generatorData.requestedModel | openai/gpt-4             |
      | generatorData.provider        | openai                   |
      | generatorData.latencyMs      | 2000.0                   |
      | generatorData.tokensUsed     | 500                      |
    When getRawData is called with days 30 and limit 100
    Then a list containing 1 dictionary is returned
    And the first dictionary contains:
      | key              | value                |
      | experimentId    | exp-123              |
      | timestamp        | 2024-01-15T10:00:00  |
      | result           | SUCCESS              |
      | testName        | testCreateUser     |
      | actualModel     | gpt-4                |
      | requestedModel  | openai/gpt-4         |
      | provider         | openai               |
      | latencyMs       | 2000.0               |
      | tokensUsed      | 500                  |

  Scenario: Populate model attribution tracker from historical data
    Given a ProductionDataAnalyzer instance
    And the repository contains experiment logs:
      | timestamp            | result  | taskData.type | taskData.testName | generatorData.actualModel | generatorData.provider |
      | 2024-01-15T10:00:00Z | SUCCESS | tddCycle      | testCreateUser    | gemini-2.0-flash            | google                  |
      | 2024-01-15T11:00:00Z | FAILED  | tddCycle      | testUpdateUser    | gemini-2.0-flash            | google                  |
    When populateModelAttribution is called with days 30
    Then a ModelAttributionTracker instance is returned
    And the tracker contains data for model "google/gemini-2.0-flash"

  Scenario: ModelPerformance calculates average metrics correctly
    Given a ModelPerformance instance with modelId "test-model"
    And taskCount is 4
    And successCount is 3
    And totalLatencyMs is 8000.0
    And totalTokens is 1200
    And totalCostUsd is 0.04
    And qualityScores are [85.5, 90.0, 78.5]
    Then successRate returns 0.75
    And avgLatencyMs returns 2000.0
    And avgTokens returns 300.0
    And avgCostUsd returns 0.01
    And avgQualityScore returns 84.66666666666667