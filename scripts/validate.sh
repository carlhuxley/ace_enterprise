#!/bin/bash
# Run all validation checks locally
# Use this before committing to catch issues early

set -e

echo "=== Running validation checks ==="
echo ""

echo "1. Ruff (lint)..."
ruff check src/ mcp_server/ || echo "   Lint issues found (see above)"
echo ""

echo "2. Mypy (types)..."
mypy src/ mcp_server/ --ignore-missing-imports || echo "   Type issues found (see above)"
echo ""

echo "3. Pytest (tests)..."
pytest tests/ -v --tb=short || echo "   Test failures (see above)"
echo ""

echo "=== Validation complete ==="
