# Test file for semantic_analyzer
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.broker.semantic_analyzer import *

def test_detect_sql_concatenation():
    analyzer = SemanticCodeAnalyzer()
    code = """
    def execute_query(user_input):
        query = "SELECT * FROM users WHERE name = '" + user_input + "'"
        return query
    """
    issues = analyzer.analyze(code)
    sql_issues = [issue for issue in issues if issue["type"] == "sql_concatenation"]
    assert len(sql_issues) == 1
    assert sql_issues[0]["severity"] == "critical"

def test_detect_eval_usage():
    analyzer = SemanticCodeAnalyzer()
    code = """
    def risky_code():
        eval("print('dangerous')")
    """
    issues = analyzer.analyze(code)
    eval_issues = [issue for issue in issues if issue["type"] == "eval_usage"]
    assert len(eval_issues) == 1
    assert eval_issues[0]["severity"] == "critical"
    assert eval_issues[0]["line"] == 3  # new assertion for line number
    assert eval_issues[0]["column"] == 9  # new assertion for column position
    assert "dangerous" in eval_issues[0]["context"]  # new assertion for context

def test_detect_exec_usage():
    analyzer = SemanticCodeAnalyzer()
    code = """
    def risky_code():
        exec("print('dangerous')")
    """
    issues = analyzer.analyze(code)
    exec_issues = [issue for issue in issues if issue["type"] == "exec_usage"]
    assert len(exec_issues) == 1
    assert exec_issues[0]["severity"] == "critical"
    assert exec_issues[0]["line"] == 3
    assert exec_issues[0]["column"] == 9
    assert "dangerous" in exec_issues[0]["context"]

def test_detect_hardcoded_secret():
    analyzer = SemanticCodeAnalyzer()
    code = """
    def login():
        password = "hardcoded_secret_123"
        return password
    """
    issues = analyzer.analyze(code)
    secret_issues = [issue for issue in issues if issue["type"] == "hardcoded_secret"]
    assert len(secret_issues) == 1
    assert secret_issues[0]["severity"] == "high"
    assert secret_issues[0]["line"] == 3
    assert secret_issues[0]["column"] == 18
    assert "hardcoded_secret_123" in secret_issues[0]["context"]