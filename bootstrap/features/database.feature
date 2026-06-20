Feature: Database connection and session management

  Scenario: Get a database session that commits successfully
    Given the database is initialized
    When I call get_db to obtain a session
    And I perform operations on the session without errors
    Then the session commits the transaction
    And the session is closed

  Scenario: Get a database session that rolls back on exception
    Given the database is initialized
    When I call get_db to obtain a session
    And an exception occurs during session operations
    Then the session rolls back the transaction
    And the exception is re-raised
    And the session is closed

  Scenario: Initialize database tables
    Given the database engine is configured
    When I call init_db
    Then all tables defined in Base metadata are created in the database

  Scenario: Drop database tables in development environment
    Given the is_development setting is True
    And the database has existing tables
    When I call drop_db
    Then all tables defined in Base metadata are dropped from the database

  Scenario: Prevent dropping database in non-development environment
    Given the is_development setting is False
    When I call drop_db
    Then a RuntimeError is raised with message "Cannot drop database in non-development environment"
    And no tables are dropped from the database

  Scenario: Close database connections
    Given the database engine has active connections
    When I call close_db
    Then all database connections are disposed

  Scenario: Multiple sequential database sessions
    Given the database is initialized
    When I call get_db to obtain a first session
    And the first session completes successfully
    And I call get_db to obtain a second session
    Then the second session is independent from the first session
    And both sessions commit their respective transactions