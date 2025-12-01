Feature: Role-Based Access Control
  As a system administrator
  I want to control access to resources based on user roles
  So that users can only perform actions they are authorized for

  Scenario: User with admin role can access admin resources
    Given a user with role "admin"
    When they attempt to access an admin resource
    Then access should be granted
    And the action should be logged

  Scenario: User without required role is denied access
    Given a user with role "viewer"
    When they attempt to modify a resource
    Then access should be denied
    And an unauthorized error should be returned

  Scenario: User with multiple roles has combined permissions
    Given a user with roles "editor" and "viewer"
    When they check their permissions
    Then they should have both read and write access
    And they should not have admin access

  Scenario: Permissions can be checked before performing actions
    Given a user with role "editor"
    When I check if they can perform action "write" on resource "document"
    Then the permission check should return true
    When I check if they can perform action "delete" on resource "document"
    Then the permission check should return false
 