Feature: Tiered Energy Tariff Calculator
  As a utility platform billing engine
  I want to calculate total consumer costs based on variable tiered usage
  So that invoices accurately reflect tiered consumption brackets

  Scenario: Basic consumption within the baseline allowance
    Given a flat standing charge of 5.00
    And a baseline tier rate of 0.15 per kWh up to 100 kWh
    When a consumer uses 40 kWh
    Then the calculated total bill must be exactly 11.00

  Scenario: Consumption breaching the baseline into the premium bracket
    Given a baseline tier up to 100 kWh at 0.15 per kWh
    And a secondary premium tier for usage above 100 kWh at 0.25 per kWh
    When a consumer uses 150 kWh
    Then the baseline tier must cap at 15.00
    And the excess 50 kWh must charge at the premium rate
    And the total bill (including the 5.00 standing charge) must be exactly 32.50

  Scenario: Zero consumption fallback
    When a consumer uses 0 kWh
    Then the total bill must equal exactly the 5.00 standing charge
