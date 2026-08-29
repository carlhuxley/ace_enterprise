Feature: Database session and lifecycle management

  Scenario: Successful database session commits on completion
    Given a caller requests a database session via get_db
    When the caller performs operations using the yielded session and completes without error
    Then the session's changes are committed
    And the session is closed afterward

  Scenario: Failed database session rolls back on error
    Given a caller requests a database session via get_db
    When an exception is raised while using the yielded session
    Then the session's changes are rolled back
    And the original exception is re-raised to the caller
    And the session is closed afterward

  Scenario: Initializing the database creates all tables
    Given a database with no existing tables
    When init_db is called
    Then all tables defined in the application's metadata are created in the database

  Scenario: Dropping the database in a development environment succeeds
    Given the application is running in a development environment
    And the database contains existing tables
    When drop_db is called
    Then all tables defined in the application's metadata are dropped from the database

  Scenario: Dropping the database outside a development environment is rejected
    Given the application is running in a non-development environment
    When drop_db is called
    Then a RuntimeError is raised with the message "Cannot drop database in non-development environment"
    And no tables are dropped

  Scenario: Closing the database releases all connections
    Given an active database engine with open connections
    When close_db is called
    Then all database connections are disposed of and no longer available for use