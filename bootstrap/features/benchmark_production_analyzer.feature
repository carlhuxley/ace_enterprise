Feature: Production Data Analyzer for TDD Quality Metrics
  As a system operator
  I want to analyze quality data from experiment logs
  So that I can understand which models perform best in production TDD cycles

  Scenario: Extracting model performance from recent experiment logs
    Given experiment logs from the last 30 days containing "tdd_cycle" tasks attributed to model "google/gemini-2.0-flash-001"
    When I extract model performance for the last 30 days
    Then the result includes an entry for model "google/gemini-2.0-flash-001"
    And that entry's task count reflects the number of matching experiment logs

  Scenario: Model names missing a provider prefix are normalized
    Given an experiment log with generator data model "GPT-4"
    When I extract model performance for the last 30 days
    Then the result includes an entry for model "openai/gpt-4"

  Scenario: Requested model with a free-tier suffix takes precedence over actual model
    Given an experiment log with actual_model "google/gemini-2.0-flash" and requested_model "google/gemini-2.0-flash:free"
    When I extract model performance for the last 30 days
    Then the result includes an entry for model "google/gemini-2.0-flash:free"
    And no entry exists for model "google/gemini-2.0-flash"

  Scenario: Experiment logs without any model attribution are skipped
    Given an experiment log with no "actual_model", "requested_model", or "model" fields set
    When I extract model performance for the last 30 days
    Then that experiment log does not contribute to any model's performance entry

  Scenario: Generating a comprehensive production report
    Given experiment logs for 3 different models over the last 30 days
    When I generate a production report for the last 30 days
    Then the report's period spans from 30 days ago to now
    And the report lists the total number of cycles analyzed
    And the report lists the number of unique models observed

  Scenario: Best overall model requires a minimum task count
    Given model "anthropic/claude-3" has completed only 2 tasks with 100% success
    And model "meta-llama/llama-3" has completed 5 tasks with 80% success
    When I generate a production report for the last 30 days
    Then "meta-llama/llama-3" is selected as the best model overall
    And "anthropic/claude-3" is not selected as the best model overall

  Scenario: Backfilling quality scores for cycles with implementation code
    Given 10 recent experiment logs that include non-empty implementation code
    When I backfill quality scores with a limit of 100
    Then the number of cycles evaluated is returned as 10

  Scenario: Retrieving raw experiment data for inspection
    Given experiment logs exist within the last 30 days
    When I request raw data with a limit of 5
    Then at most 5 experiment records are returned
    And each record includes the experiment id, timestamp, result, and model attribution fields