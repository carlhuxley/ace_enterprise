Feature: Query String Parser
  As a backend service
  I want to parse raw URL query strings into structured dictionaries
  So that application routes can easily read incoming request parameters

  Scenario: Extracting parameters from a standard web request query
    Given a raw query string "page=2&sort=desc&category=tools"
    When the parsing function executes
    Then it must return a flat dictionary:
      | key      | value |
      | page     | 2     |
      | sort     | desc  |
      | category | tools |

  Scenario: Handling empty values and boolean flags safely
    Given a raw query string "active&beta=true&search="
    When the parsing function executes
    Then keys without values must default to true
    And empty trailing values must result in an empty string value

  Scenario: Decoding URL-encoded characters
    Given a raw query string "title=Sourdough%20Baps&user=carl%40zbk"
    When the parsing function executes
    Then special character sequences must be decoded back to plaintext values:
      | key   | value          |
      | title | Sourdough Baps |
      | user  | carl@zbk       |
