Feature: Parsing Gherkin .feature files into FeatureSpec objects

  Scenario: Parsing a feature file with a title and one scenario with steps
    Given a file "login.feature" containing:
      """
      Feature: User login
      Scenario: Successful login
      Given a registered user
      When they submit valid credentials
      Then they are logged in
      """
    When the file is parsed
    Then the resulting title is "User login"
    And there is 1 scenario named "Successful login"
    And that scenario has 3 steps

  Scenario: Parsing a feature file with multiple scenarios
    Given a file "checkout.feature" containing:
      """
      Feature: Checkout
      Scenario: Empty cart
      Given an empty cart
      Then checkout is disabled
      Scenario: Cart with items
      Given a cart with 2 items
      When the user proceeds to checkout
      Then the order is created
      """
    When the file is parsed
    Then there are 2 scenarios
    And the scenario named "Empty cart" has 2 steps
    And the scenario named "Cart with items" has 3 steps

  Scenario: "Scenario Outline" lines are treated the same as "Scenario" lines
    Given a file "outline.feature" containing:
      """
      Feature: Discounts
      Scenario Outline: Applying a discount code
      Given a cart total of <total>
      When code <code> is applied
      Then the total becomes <result>
      """
    When the file is parsed
    Then there is 1 scenario named "Applying a discount code"
    And that scenario has 3 steps

  Scenario: Feature and step keywords are recognized case-insensitively
    Given a file "case.feature" containing:
      """
      feature: Case insensitive parsing
      scenario: lowercase keywords
      given a precondition
      when an action occurs
      then an outcome is observed
      """
    When the file is parsed
    Then the resulting title is "Case insensitive parsing"
    And there is 1 scenario named "lowercase keywords"
    And that scenario has 3 steps

  Scenario: Parsing fails when no Feature line is present
    Given a file "broken.feature" containing:
      """
      Scenario: Orphan scenario
      Given something happens
      """
    When the file is parsed
    Then a ValueError is raised mentioning "broken.feature"

  Scenario: Converting a parsed feature with no scenarios into a requirement string
    Given a file "empty.feature" containing:
      """
      Feature: Placeholder feature
      """
    When the file is parsed
    And the resulting FeatureSpec is converted to a requirement string
    Then the requirement string is "Placeholder feature"

  Scenario: Converting a parsed feature with scenarios into a requirement string
    Given a file "summary.feature" containing:
      """
      Feature: Order processing
      Scenario: Valid order
      Given a valid order
      When it is submitted
      Then it is accepted
      Scenario: Invalid order
      Given an invalid order
      Then it is rejected
      """
    When the file is parsed
    And the resulting FeatureSpec is converted to a requirement string
    Then the requirement string is "Order processing. Scenarios: Valid order (2 steps), Invalid order (1 steps)"