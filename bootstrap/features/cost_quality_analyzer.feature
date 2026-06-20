Feature: Cost Quality Analyzer
  Analyzes cost-quality tradeoffs for ML model performance data.

  IMPORTANT — export contract: CostQualityAnalyzer is a class. Its static
  methods must ALSO be exported as standalone named functions with camelCase
  names so callers can import them directly:
    export function computeParetoFrontier(...)
    export function rankModelsByQualityPerDollar(...)
    export function calculateQualityDeltaPercentage(...)
    export function queryBestModelForComplexity(...)

  Scenario: Calculate cost efficiency metrics from per-prediction data
    Given a CostQualityAnalyzer initialized with:
      | field             | value  |
      | modelName         | GPT-4  |
      | accuracy          | 0.95   |
      | costPerPrediction | 0.0002 |
    When calculateCostEfficiencyMetrics is called
    Then the result contains qualityPerDollar computed as accuracy / costPerPrediction = 0.95 / 0.0002 = 4750.0
    And the result contains costPerQualityPoint computed as costPerPrediction / accuracy = 0.0002 / 0.95 ≈ 0.000210526
    And the result contains avgQualityScore equal to the accuracy value 0.95
    And the result contains efficiencyGrade "B" because 4750.0 is below 5000 but at or above 1000
    And the result contains metadata with calculatedAt as an ISO 8601 timestamp string
    And the result contains metadata with inputHash as a 64-character lowercase hex SHA-256 string

  Scenario: Calculate cost efficiency metrics from aggregated total data
    Given a CostQualityAnalyzer initialized with:
      | field               | value   |
      | totalCostUsd        | 10.0    |
      | totalQualityPoints  | 50000.0 |
      | taskCount           | 100     |
    When calculateCostEfficiencyMetrics is called
    Then the result contains qualityPerDollar computed as totalQualityPoints / totalCostUsd = 50000.0 / 10.0 = 5000.0
    And the result contains costPerQualityPoint computed as totalCostUsd / totalQualityPoints = 10.0 / 50000.0 = 0.0002
    And the result contains avgQualityScore computed as totalQualityPoints / taskCount = 50000.0 / 100 = 500.0
    And the result contains efficiencyGrade "A" because 5000.0 meets the A threshold of >= 5000

  Scenario: Efficiency grade boundaries — A at or above 5000, B from 1000 to 4999, C below 1000
    Given efficiency grade thresholds:
      | threshold | grade |
      | >= 5000   | A     |
      | >= 1000   | B     |
      | < 1000    | C     |
    Then a CostQualityAnalyzer with accuracy 0.98 and costPerPrediction 0.0001 yields qualityPerDollar 9800.0 and grade "A"
    And a CostQualityAnalyzer with accuracy 0.95 and costPerPrediction 0.0002 yields qualityPerDollar 4750.0 and grade "B"
    And a CostQualityAnalyzer with accuracy 0.70 and costPerPrediction 0.001 yields qualityPerDollar 700.0 and grade "C"

  Scenario: Rank models by quality per dollar in descending order
    Given the standalone function rankModelsByQualityPerDollar is called with:
      | modelName | accuracy | costPerPrediction |
      | ModelA    | 0.90     | 0.0003            |
      | ModelB    | 0.85     | 0.0001            |
      | ModelC    | 0.95     | 0.0005            |
    Then the formula qualityPerDollar = accuracy / costPerPrediction gives:
      | modelName | qualityPerDollar |
      | ModelA    | 3000.0           |
      | ModelB    | 8500.0           |
      | ModelC    | 1900.0           |
    And the returned list is sorted descending: ModelB first (8500.0), ModelA second (3000.0), ModelC third (1900.0)

  Scenario: Pareto frontier excludes models dominated on both cost AND quality
    Given the standalone function computeParetoFrontier is called with:
      | modelName | accuracy | costPerPrediction |
      | Premium   | 0.95     | 0.0005            |
      | Budget    | 0.80     | 0.0001            |
      | Laggard   | 0.75     | 0.0008            |
    Then a model is dominated if another model has BOTH strictly lower costPerPrediction AND strictly higher accuracy
    And Laggard (accuracy=0.75, cost=0.0008) is dominated by Premium (accuracy=0.95 > 0.75 AND cost=0.0005 < 0.0008)
    And Premium is not dominated because no model has accuracy > 0.95 AND cost < 0.0005 simultaneously
    And Budget is not dominated because no model has accuracy > 0.80 AND cost < 0.0001 simultaneously
    And the Pareto frontier contains Premium and Budget
    And the Pareto frontier does not contain Laggard

  Scenario: Quality delta percentage — relative improvement of higher accuracy over lower
    Given the standalone function calculateQualityDeltaPercentage is called with:
      | field    | value |
      | higher   | 0.95  |
      | lower    | 0.80  |
    Then the result uses the formula ((higher - lower) / lower) * 100 = ((0.95 - 0.80) / 0.80) * 100 = 18.75
    And the result is exactly 18.75

  Scenario: Query best model for high complexity — filter by threshold then select highest valueScore
    Given the standalone function queryBestModelForComplexity is called with complexityLevel "high"
    And the models data is:
      | modelName | complexity | successRate | valueScore |
      | Premium   | high       | 0.92        | 850.0      |
      | Standard  | high       | 0.88        | 900.0      |
      | Budget    | high       | 0.95        | 800.0      |
    Then the high complexity threshold is 0.90 (successRate must be >= 0.90 to qualify)
    And Standard (successRate=0.88) does not meet the threshold and is excluded
    And Premium (successRate=0.92) and Budget (successRate=0.95) both qualify
    And among qualifying models the highest valueScore wins: Premium (850.0) > Budget (800.0)
    And the result is Premium with successRate 0.92 and valueScore 850.0

  Scenario: Query best model for medium complexity — threshold 0.80
    Given the standalone function queryBestModelForComplexity is called with complexityLevel "medium"
    And the models data is:
      | modelName | complexity | successRate | valueScore |
      | MediumA   | medium     | 0.85        | 750.0      |
      | MediumB   | medium     | 0.78        | 700.0      |
    Then the medium complexity threshold is 0.80 (successRate must be >= 0.80 to qualify)
    And MediumB (successRate=0.78) does not meet the threshold and is excluded
    And MediumA (successRate=0.85) is the only qualifying model
    And the result is MediumA with successRate 0.85 and valueScore 750.0

  Scenario: Query best model falls back to highest valueScore when no models meet the threshold
    Given the standalone function queryBestModelForComplexity is called with complexityLevel "low"
    And the models data is:
      | modelName | complexity | successRate | valueScore |
      | LowA      | low        | 0.65        | 600.0      |
      | LowB      | low        | 0.60        | 650.0      |
    Then the low complexity threshold is 0.70 (successRate must be >= 0.70 to qualify)
    And neither LowA (0.65) nor LowB (0.60) meets the threshold
    And the fallback selects from all low-complexity models by highest valueScore
    And LowB (valueScore=650.0) beats LowA (valueScore=600.0)
    And the result is LowB with successRate 0.60 and valueScore 650.0
