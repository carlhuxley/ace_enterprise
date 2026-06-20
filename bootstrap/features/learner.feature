Feature: Ensemble Learner

  Scenario: Initialize ensemble learner with multiple models
    Given a list of models [("ollama", "qwen2.5-coder:7b"), ("ollama", "llama3.1:8b")]
    And a playbook ID "test-playbook-123"
    When I create an EnsembleLearner with these models and playbook ID
    Then the ensemble learner is initialized with 2 models
    And model performance tracking is initialized for "ollama/qwen2.5-coder:7b"
    And model performance tracking is initialized for "ollama/llama3.1:8b"

  Scenario: Initialize ensemble learner with custom voting strategy and deliberation settings
    Given a list of models [("ollama", "qwen2.5-coder:7b")]
    And a playbook ID "test-playbook-456"
    And a voting strategy of type "supermajority"
    And similarity threshold 0.90
    And deliberation enabled with thresholds 0.35 to 0.65
    And max deliberation rounds 3
    When I create an EnsembleLearner with these parameters
    Then the ensemble learner uses the supermajority voting strategy
    And the consensus builder uses similarity threshold 0.90
    And deliberation is enabled with low threshold 0.35 and high threshold 0.65
    And max deliberation rounds is set to 3

  Scenario: Execute ensemble learning cycle in parallel mode
    Given an initialized EnsembleLearner with 2 models
    And a TaskInput with query "Write a function to validate email addresses"
    And EnvironmentFeedback with success True and output "Tests passed"
    When I call learnFromTask with parallel=True
    Then an EnsembleResult is returned
    And the result contains taskDescription "Write a function to validate email addresses"
    And the result contains 2 modelsUsed
    And the result contains consensus bullets with votes from all models
    And the result contains voteResults with totalBullets count
    And the result contains modelPerformance for each model
    And the result has startedAt and completedAt timestamps
    And the result has durationSeconds greater than 0
    And the result has diversityScore between 0.0 and 1.0
    And the result has consensusStrength between 0.0 and 1.0

  Scenario: Execute ensemble learning cycle in sequential mode
    Given an initialized EnsembleLearner with 2 models
    And a TaskInput with query "Implement binary search"
    And EnvironmentFeedback with success False and error "Index out of bounds"
    When I call learnFromTask with parallel=False
    Then an EnsembleResult is returned
    And the result contains consensus bullets from sequential execution
    And each model's proposals are collected in order

  Scenario: Conduct cross-voting on consensus bullets
    Given an EnsembleLearner with 3 models
    And a learning cycle produces 5 consensus bullets
    When cross-voting is conducted
    Then each bullet receives 3 votes (one from each model)
    And each vote contains modelId, vote type, reasoning, and confidence
    And model performance votesCast is incremented for each model
    And model performance avgConfidence is updated

  Scenario: Conduct deliberation on contested bullets
    Given an EnsembleLearner with deliberation enabled
    And a consensus bullet with approval rate 0.45 (contested)
    When deliberation is conducted
    Then the bullet undergoes deliberative discussion
    And models reconsider their votes based on others' reasoning
    And the bullet's deliberationRounds count is incremented
    And deliberation stops when consensus is reached or max rounds exceeded
    And the number of contested bullets is returned

  Scenario: Apply voting strategy to approve or reject bullets
    Given an EnsembleLearner with majority voting strategy
    And consensus bullets with various approval rates
    When the voting system evaluates the bullets
    Then bullets with approvalRate >= 0.5 are approved
    And bullets with approvalRate < 0.5 are rejected
    And voteResults contains counts of approved and rejected bullets
    And voteResults contains strategy-specific counts

  Scenario: Add approved bullets to playbook with provenance
    Given an EnsembleResult with 3 approved bullets
    And bullets proposed by "ollama/qwen2.5-coder:7b"
    When I call addApprovedBulletsToPlaybook
    Then bullets are added to the playbook with model provenance
    And each bullet has createdByModel set to "qwen2.5-coder:7b"
    And each bullet has modelProvider set to "ollama"
    And each bullet has licenseType set to "apache-2.0"
    And each bullet has confidenceScore set to 0.6
    And the method returns the count of bullets added

  Scenario: Calculate vote results with quality metrics
    Given consensus bullets with mixed approval outcomes
    And bullets with various approval rates and confidence scores
    When vote results are calculated
    Then VoteResults contains totalBullets count
    And VoteResults contains approved, rejected, and pending counts
    And VoteResults contains avgApprovalRate across all bullets
    And VoteResults contains avgConfidence across all votes
    And VoteResults contains avgDeliberationRounds
    And VoteResults contains highlyContested count (approval 0.4-0.6)
    And VoteResults contains unanimousDecisions count (approval 0.0 or 1.0)

  Scenario: Update model performance based on voting outcomes
    Given consensus bullets with final approval decisions
    And models that proposed and voted on bullets
    When model performance is updated
    Then proposer's proposalsApproved is incremented for approved bullets
    And proposer's proposalsRejected is incremented for rejected bullets
    And voter's votesWithMajority is incremented when vote matched outcome
    And each model's accuracyScore is calculated as agreementRate
    And each model's votingWeight is updated based on accuracyScore

  Scenario: Determine license type for different providers
    Given a model with provider "ollama" and model "qwen2.5-coder:7b"
    When license type is determined
    Then the licenseType is "apache-2.0"
    
  Scenario: Determine license type for proprietary provider
    Given a model with provider "openai" and model "gpt-4"
    When license type is determined
    Then the licenseType is "proprietary"

  Scenario: Initialize with vLLM models using custom baseUrl
    Given a list of models [("vllm", "Qwen/Qwen2.5-Coder-32B-Instruct", "http://localhost:8000")]
    And a playbook ID "vllm-playbook"
    When I create an EnsembleLearner with these models
    Then the ensemble learner is initialized with 1 model
    And the model configuration includes baseUrl "http://localhost:8000"

<budget:tokenBudget>
Tokens used this turn: 9878
Tokens used in context: 0
Total tokens used: 9878
Remaining budget: 990122
</budget:tokenBudget>