Feature: Context Map API

  Scenario: Build context map from empty file list
    Given a ContextMapBuilder instance
    When build is called with an empty list
    Then a ContextMap is returned with no files

  Scenario: Build context map from non-existent file
    Given a ContextMapBuilder instance
    When build is called with a list containing Path("nonexistent.py")
    Then a ContextMap is returned with no files

  Scenario: Build context map from file with function
    Given a Python file "example.py" containing a function "calculate" with parameters "x: int, y: int" and return annotation "int" at lines 1-2
    And a ContextMapBuilder instance
    When build is called with a list containing Path("example.py")
    Then the returned ContextMap contains 1 file
    And allSignatures returns 1 signature
    And the signature has name "calculate"
    And the signature has qualifiedName "calculate"
    And the signature has kind "function"
    And the signature has parameters ["x: int", "y: int"]
    And the signature has returnAnnotation "int"

  Scenario: Build context map from file with class and method
    Given a Python file "shapes.py" containing class "Circle" at lines 1-3 with method "area" at line 2
    And a ContextMapBuilder instance
    When build is called with a list containing Path("shapes.py")
    Then allSignatures returns 2 signatures
    And one signature has name "Circle" and kind "class"
    And one signature has name "area" and qualifiedName "Circle.area" and kind "method"

  Scenario: Format compact signature representation
    Given an ASTSignature with name "foo", qualifiedName "MyClass.foo", parameters ["self", "x: int"], returnAnnotation "str", sourceFile Path("test.py"), and lineStart 10
    When formatCompact is called
    Then the result is "MyClass.foo(self, x: int) -> str  # test.py:10"

  Scenario: Get nodes relevant to test IDs with empty list
    Given a ContextMap with signatures
    When nodesRelevantTo is called with an empty list
    Then an empty list is returned

  Scenario: Get nodes relevant to specific test function
    Given a Python test file "test_calc.py" containing function "test_add" that references name "add"
    And a ContextMap containing a signature with name "add"
    When nodesRelevantTo is called with ["test_calc.py::test_add"]
    Then the returned list contains the signature with name "add"

  Scenario: Get all signatures from multiple files
    Given a ContextMap with 2 files each containing 2 signatures
    When allSignatures is called
    Then a list of 4 signatures is returned