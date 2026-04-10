# Test file for file_placement_router
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.broker.file_placement_router import *

def test_route_file_broker_keyword():
    agent = ProjectAwareAgent()
    result = agent.route_file("broker_analyzer.py", "broker routing feature")
    assert result == "src/broker/broker_analyzer.py"

def test_route_file_agent_keyword():
    agent = ProjectAwareAgent()
    result = agent.route_file("project_analyzer.py", "agent feature analyzer")
    assert result == "src/agents/project_analyzer.py"

def test_route_file_default_directory():
    agent = ProjectAwareAgent()
    result = agent.route_file("unknown_feature.py", "feature with no matching keywords")
    assert result == "src/unknown_feature.py"

def test_route_file_storage_keyword():
    agent = ProjectAwareAgent()
    result = agent.route_file("data_repository.py", "storage feature with repository")
    assert result == "src/storage/data_repository.py"