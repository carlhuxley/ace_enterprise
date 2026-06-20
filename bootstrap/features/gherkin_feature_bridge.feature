Feature: Gherkin Feature Bridge

  Scenario: Parse a feature file with title only
    Given a feature file "simple.feature" containing:
      """
      Feature: User Authentication
      """
    When GherkinFeatureBridge.parse is called with "simple.feature"
    Then a FeatureSpec is returned with title "User Authentication"
    And the FeatureSpec has 0 scenarios

  Scenario: Parse a feature file with one scenario and multiple steps
    Given a feature file "login.feature" containing:
      """
      Feature: Login System
      Scenario: Successful login
        Given a user exists with username "alice"
        When the user logs in with password "secret123"
        Then the user is redirected to the dashboard
      """
    When GherkinFeatureBridge.parse is called with "login.feature"
    Then a FeatureSpec is returned with title "Login System"
    And the FeatureSpec has 1 scenario
    And scenario 0 has name "Successful login"
    And scenario 0 has 3 steps

  Scenario: Parse a feature file with multiple scenarios
    Given a feature file "cart.feature" containing:
      """
      Feature: Shopping Cart
      Scenario: Add item to cart
        Given the cart is empty
        When I add a product
        Then the cart contains 1 item
      Scenario: Remove item from cart
        Given the cart has 2 items
        When I remove one item
        Then the cart contains 1 item
      """
    When GherkinFeatureBridge.parse is called with "cart.feature"
    Then a FeatureSpec is returned with title "Shopping Cart"
    And the FeatureSpec has 2 scenarios
    And scenario 0 has name "Add item to cart"
    And scenario 0 has 3 steps
    And scenario 1 has name "Remove item from cart"
    And scenario 1 has 3 steps

  Scenario: Parse steps with And and But keywords
    Given a feature file "complex.feature" containing:
      """
      Feature: Payment Processing
      Scenario: Process payment with validation
        Given a valid credit card
        And sufficient funds
        When the payment is submitted
        But the network is slow
        Then the payment succeeds
        And a receipt is generated
      """
    When GherkinFeatureBridge.parse is called with "complex.feature"
    Then scenario 0 has 6 steps

  Scenario: Parse Scenario Outline as a scenario
    Given a feature file "outline.feature" containing:
      """
      Feature: Data Validation
      Scenario Outline: Validate email format
        Given an email "<email>"
        When validation runs
        Then the result is "<valid>"
      """
    When GherkinFeatureBridge.parse is called with "outline.feature"
    Then scenario 0 has name "Validate email format"
    And scenario 0 has 3 steps

  Scenario: Generate requirement string from feature with scenarios
    Given a FeatureSpec with title "Order Management"
    And scenario "Create order" with 4 steps
    And scenario "Cancel order" with 2 steps
    When as_requirement is called on the FeatureSpec
    Then the result is "Order Management. Scenarios: Create order (4 steps), Cancel order (2 steps)"

  Scenario: Generate requirement string from feature without scenarios
    Given a FeatureSpec with title "Empty Feature"
    And no scenarios
    When as_requirement is called on the FeatureSpec
    Then the result is "Empty Feature"

  Scenario: Raise error when no Feature line is present
    Given a feature file "invalid.feature" containing:
      """
      Scenario: Orphan scenario
        Given something
      """
    When GherkinFeatureBridge.parse is called with "invalid.feature"
    Then a ValueError is raised with message containing "No 'Feature:' line found"