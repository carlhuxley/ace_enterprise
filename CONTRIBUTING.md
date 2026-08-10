# Contributing to ACE Enterprise

First off, thank you for considering contributing to ACE Enterprise! This project aims to build institutional knowledge infrastructure for software development, and we welcome contributions from everyone.

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on what's best for the project and community
- Accept constructive criticism gracefully
- Show empathy towards other community members

### Unacceptable Behavior

- Harassment, trolling, or discriminatory language
- Publishing others' private information
- Unprofessional conduct or personal attacks

## How to Contribute

### Reporting Bugs

**Before submitting a bug report:**
- Check existing issues to avoid duplicates
- Collect information about your environment (OS, Python version, dependencies)
- Try to reproduce the bug with minimal steps

**Bug Report Template:**
```markdown
**Description**: Clear description of the bug

**Steps to Reproduce**:
1. Step one
2. Step two
3. ...

**Expected Behavior**: What should happen

**Actual Behavior**: What actually happened

**Environment**:
- OS: [e.g., Ubuntu 22.04]
- Python: [e.g., 3.11.4]
- ACE Version: [e.g., 0.1.0]
```

### Suggesting Enhancements

We love feature ideas! Please:
- Use a clear, descriptive title
- Explain the problem this enhancement would solve
- Describe the proposed solution
- Consider alternative solutions
- Explain why this would be useful to most users

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following our code standards
3. **Add tests** for new functionality
4. **Update documentation** if needed
5. **Ensure tests pass**: `pytest`
6. **Submit your PR** with a clear description

**PR Template:**
```markdown
**What does this PR do?**
Brief description of changes

**Why is this needed?**
Problem this solves or feature this adds

**How was it tested?**
- [ ] Added unit tests
- [ ] Tested manually
- [ ] Updated documentation

**Related Issues**: #123
```

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- (Optional but recommended) [uv](https://github.com/astral-sh/uv) for faster package management

### Quick Setup with uv (Recommended - 10-100x Faster)

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/ace_enterprise.git
cd ace_enterprise

# 3. Install ACE in editable mode with all dependencies
uv pip install -e ".[dev,ml]"

# That's it! Run tests to verify
pytest
```

**What gets installed:**
- Core ACE dependencies (pydantic, httpx, pyyaml, python-dotenv)
- `[dev]` - Testing & code quality tools (pytest, ruff, black, mypy)
- `[ml]` - MLflow integration (mlflow, scikit-learn, numpy)

**Install options:**
```bash
# Core only (minimal)
uv pip install -e .

# Core + development tools
uv pip install -e ".[dev]"

# Core + MLflow integration
uv pip install -e ".[ml]"

# Everything (recommended for contributors)
uv pip install -e ".[dev,ml]"
```

### Traditional Setup with pip

```bash
# 1. Clone your fork
git clone https://github.com/YOUR_USERNAME/ace_enterprise.git
cd ace_enterprise

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install ACE in editable mode
pip install -e ".[dev,ml]"

# 4. Run tests
pytest
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_autonomous_tdd_agent.py

# Run with verbose output
pytest -v
```

### Code Quality Tools

```bash
# Format code with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Type checking with mypy
mypy src/
```

## Code Standards

### Python Style

- Follow **PEP 8** style guide
- Use **type hints** for function signatures
- Write **docstrings** for public functions and classes
- Maximum line length: **100 characters** (black default)

**Example:**
```python
def build_feature(
    gherkin_dir: Path,
    project_root: Path,
    source_dir: Path,
    test_dir: Path
) -> TDDResult:
    """Build feature using Gherkin-driven TDD.

    Args:
        gherkin_dir: Directory containing .feature files
        project_root: Root directory of target project
        source_dir: Directory for generated source code
        test_dir: Directory for generated tests

    Returns:
        TDDResult with build outcomes

    Raises:
        ValueError: If gherkin_dir does not exist
    """
    # Implementation here
```

### Testing Standards

- Write tests for all new functionality
- Use **pytest** framework
- Aim for **80%+ code coverage**
- Test both success and failure cases
- Use descriptive test names

**Example:**
```python
def test_project_detector_finds_src_directory():
    """Test that ProjectDetector correctly identifies src/ directory."""
    detector = ProjectDetector()
    project_info = detector.detect()
    assert project_info.src_dir.name == "src"
```

### Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `chore`: Maintenance tasks

**Examples:**
```
feat(cli): add status command to show project configuration

Add 'ace status' command that displays current ACE configuration,
project information, and decision record count.

Closes #42
```

## AI-Assisted Development

### Policy

ACE Enterprise welcomes contributions developed with AI assistance (ChatGPT, Claude, Copilot, etc.). However:

**Requirements:**
1. **Human Review**: All code must be reviewed and understood by a human
2. **Disclosure**: Mention AI assistance in PR description (optional but appreciated)
3. **Responsibility**: You take full responsibility for contributed code
4. **Testing**: AI-generated code must have tests like any other code

**Example PR Note:**
```markdown
**Development Notes:**
This feature was developed with AI assistance (Claude Code) for initial
implementation. All code has been reviewed, tested, and modified by human
contributors.
```

### Philosophy

We believe:
- AI is a tool that augments human capability
- Humans remain responsible for architecture, design, and quality
- Transparency builds trust
- The outcome matters more than the process
- AI-assisted development can be high quality when properly reviewed

**Questions about AI contributions?** See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for our full philosophy and citation guidance.

## Project Structure

```
ace_enterprise/
├── src/                    # Source code
│   ├── agents/            # TDD and test review agents
│   ├── ensemble/          # Model ensemble and learning
│   ├── playbook/          # Playbook management
│   ├── project/           # Project detection and config
│   ├── storage/           # Data schemas and storage
│   └── utils/             # Utilities (LLM client, etc.)
├── tests/                 # Test suite
├── docs/                  # Documentation
├── features/              # Example Gherkin features
├── data/                  # Playbooks and knowledge
│   └── playbooks/         # Domain-specific playbooks
├── ace_cli.py            # Main CLI interface
├── demo_*.py             # Demo scripts
├── requirements.txt       # Core dependencies
└── requirements-ml.txt    # ML/MLflow dependencies
```

## Documentation

### When to Update Docs

Update documentation when:
- Adding new features or commands
- Changing public APIs
- Modifying configuration options
- Adding new concepts or workflows

### Documentation Locations

- **README.md**: Overview, quick start, basic usage
- **docs/**: Detailed guides and architectural docs
- **Docstrings**: API documentation in code
- **ACKNOWLEDGMENTS.md**: Attribution and citations

## Release Process

(For maintainers)

1. Update version in `setup.py` or `pyproject.toml`
2. Update CHANGELOG.md
3. Create git tag: `git tag -a v0.2.0 -m "Release v0.2.0"`
4. Push tag: `git push origin v0.2.0`
5. GitHub Actions will create release (future automation)

## Getting Help

- **GitHub Issues**: https://github.com/carlhuxley/ace_enterprise/issues
- **Discussions**: https://github.com/carlhuxley/ace_enterprise/discussions
- **Security issues**: See [SECURITY.md](SECURITY.md) — do not file these as public issues

## Recognition

Contributors will be:
- Listed in ACKNOWLEDGMENTS.md
- Credited in release notes
- Recognized in commit history

Thank you for making ACE Enterprise better!

---

## License

By contributing to ACE Enterprise, you agree that your contributions will be licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

## Acknowledgments

This project builds on research and methodologies from:
- ACE Framework (arXiv:2510.04618)
- Dave Farley's ATDD methodology
- The broader TDD and DevOps communities

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for complete attribution.

---

*Last Updated: December 04, 2025*
