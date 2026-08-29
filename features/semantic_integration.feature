Feature: Semantic Analysis Integration with BlindEvaluator
  As a system administrator
  I want semantic analysis integrated with the BlindEvaluator scoring
  So that code quality scores reflect complexity, security, and design patterns

  Background:
    Given the SemanticCodeAnalyzer is initialized
    And the BlindEvaluator is available with semantic scoring enabled

  Scenario: Integrate semantic score with BlindEvaluator
    Given a code submission with:
      | dimension       | raw_score |
      | syntax          | 20        |
      | structure       | 15        |
      | tests           | 40        |
    And the semantic analysis yields:
      | metric               | value  |
      | complexity_penalty   | -5     |
      | security_penalty     | 0      |
      | di_bonus             | +5     |
      | type_hints_bonus     | +3     |
    When the BlindEvaluator calculates the total score
    Then the semantic score component should be 25 + (-5) + 0 + 5 + 3 = 28
    And the total score should be 20 + 15 + 40 + 28 = 103

  Scenario: Score clean, well-designed code highly
    Given the following well-designed Python code:
      """
      from typing import Optional
      from dataclasses import dataclass

      @dataclass
      class User:
          id: int
          name: str
          email: str

      class UserService:
          def __init__(self, repository: UserRepository):
              self.repository = repository

          def get_user(self, user_id: int) -> Optional[User]:
              return self.repository.find_by_id(user_id)
      """
    When I perform full semantic analysis
    Then the code should have complexity rating "low"
    And the code should have no security issues
    And the code should have design pattern bonuses
    And the overall semantic score should be above 25
