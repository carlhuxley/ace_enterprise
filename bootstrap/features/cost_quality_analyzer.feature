Feature: Cost Quality Analyzer
  Analyzes cost-quality tradeoffs for ML model performance data

  Scenario: Calculate cost efficiency metrics using per-prediction data
    Given a CostQualityAnalyzer is initialized with performance data:
      | modelName | accuracy | costPerPrediction |
      | GPT-4      | 0.95     | 0.0002              |
    When calculateCostEfficiencyMetrics is called
    Then the result contains costPerQualityPoint of 0.000211
    And the result contains qualityPerDollar of 4750.0
    And the result contains avgQualityScore of 0.95
    And the result contains efficiencyGrade of "B"
    And the result contains metadata with calculatedAt as an ISO timestamp
    And the result contains metadata with inputHash as a SHA256 hex string

  Scenario: Calculate cost efficiency metrics using total metrics data
    Given a CostQualityAnalyzer is initialized with performance data:
      | totalCostUsd | totalQualityPoints | taskCount |
      | 10.0           | 50000.0              | 100        |
    When calculateCostEfficiencyMetrics is called
    Then the result contains costPerQualityPoint of 0.0002
    And the result contains qualityPerDollar of 5000.0
    And the result contains avgQualityScore of 500.0
    And the result contains efficiencyGrade of "A"

  Scenario: Assign efficiency grade A for high quality per dollar
    Given a CostQualityAnalyzer is initialized with performance data:
      | modelName | accuracy | costPerPrediction |
      | Claude     | 0.98     | 0.0001              |
    When calculateCostEfficiencyMetrics is called
    Then the result contains qualityPerDollar of 9800.0
    And the result contains efficiencyGrade of "A"

  Scenario: Assign efficiency grade C for low quality per dollar
    Given a CostQualityAnalyzer is initialized with performance data:
      | modelName | accuracy | costPerPrediction |
      | Basic      | 0.70     | 0.001               |
    When calculateCostEfficiencyMetrics is called
    Then the result contains qualityPerDollar of 700.0
    And the result contains efficiencyGrade of "C"

  Scenario: Rank models by quality per dollar in descending order
    Given a list of models data:
      | modelName | accuracy | costPerPrediction |
      | ModelA     | 0.90     | 0.0003              |
      | ModelB     | 0.85     | 0.0001              |
      | ModelC     | 0.95     | 0.0005              |
    When rankModelsByQualityPerDollar is called with the models data
    Then the returned list has ModelB first with quality per dollar 8500.0
    And the returned list has ModelA second with quality per dollar 3000.0
    And the returned list has ModelC third with quality per dollar 1900.0

  Scenario: Compute Pareto frontier excluding dominated models
    Given a list of models data:
      | modelName | accuracy | costPerPrediction |
      | Expensive  | 0.95     | 0.001               |
      | Cheap      | 0.80     | 0.0001              |
      | Dominated  | 0.85     | 0.0005              |
    When computeParetoFrontier is called with the models data
    Then the Pareto frontier contains Expensive
    And the Pareto frontier contains Cheap
    And the Pareto frontier does not contain Dominated

  Scenario: Calculate quality delta percentage between two models
    Given a higher quality model with accuracy 0.95
    And a lower quality model with accuracy 0.80
    When calculateQualityDeltaPercentage is called with both models
    Then the result is 18.75

  Scenario: Query best model for high complexity with threshold filtering
    Given a list of models data with complexity levels:
      | modelName | complexity | successRate | valueScore |
      | Premium    | high       | 0.92         | 850.0       |
      | Standard   | high       | 0.88         | 900.0       |
      | Budget     | high       | 0.95         | 800.0       |
    When queryBestModelForComplexity is called with complexityLevel "high"
    Then the result is the model Premium with successRate 0.92 and valueScore 850.0

  Scenario: Query best model for medium complexity
    Given a list of models data with complexity levels:
      | modelName | complexity | successRate | valueScore |
      | MediumA    | medium     | 0.85         | 700.0       |
      | MediumB    | medium     | 0.82         | 750.0       |
    When queryBestModelForComplexity is called with complexityLevel "medium"
    Then the result is the model MediumA with successRate 0.85 and valueScore 700.0

  Scenario: Query best model falls back when no models meet threshold
    Given a list of models data with complexity levels:
      | modelName | complexity | successRate | valueScore |
      | LowA       | low        | 0.65         | 600.0       |
      | LowB       | low        | 0.60         | 650.0       |
    When queryBestModelForComplexity is called with complexityLevel "low"
    Then the result is the model LowB with successRate 0.60 and valueScore 650.0