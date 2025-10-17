# ACE Enterprise

**Agentic Context Engineering for Production LLM Applications**

ACE Enterprise is a production-ready implementation of Agentic Context Engineering (ACE), an adaptive learning system that enables LLM applications to continuously improve through structured context evolution.

## Key Features

- **Self-improving AI agents** that learn from execution feedback
- **10-17% accuracy improvements** on complex tasks through adaptive learning
- **86.9% reduction** in adaptation latency through incremental updates
- **Full auditability** with human oversight of the learning process
- **Production-grade reliability** with automatic regression detection and rollback

## Architecture

ACE Enterprise consists of three core learning modules:

1. **Generator Module**: Executes tasks using a "playbook" (evolving knowledge base)
2. **Reflector Module**: Analyzes what went wrong/right and extracts insights
3. **Curator Module**: Synthesizes insights into actionable playbook updates

Plus enterprise features:
- Checkpoint & Rollback system
- Performance monitoring with regression detection
- Comprehensive audit trails
- Multi-epoch training support (offline, online, hybrid modes)

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Ollama with models installed (or LLM API keys)

### Local Development Setup

1. **Clone the repository**
   ```bash
   cd ace_enterprise
   ```

2. **Set up environment variables**
   ```bash
   make setup
   # .env file created with defaults (uses Ollama + qwen3-coder:30b)
   ```

3. **Start development environment**
   ```bash
   make dev
   ```
   This starts:
   - PostgreSQL with pgvector (port 5432)
   - Redis (port 6379)
   - ACE API (port 8000)

4. **Verify services are running**
   ```bash
   make health
   ```

5. **Access the API**
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Prometheus Metrics: http://localhost:9090/metrics

### With Monitoring (Optional)

Start with Prometheus and Grafana:
```bash
make dev-full
```

Access monitoring dashboards:
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9091

## LLM Configuration

### Using Ollama (Local - Default)

ACE Enterprise is pre-configured to use Ollama with `qwen3-coder:30b`.

**Available models:**
```bash
# List installed models
ollama list

# Pull additional models
ollama pull qwen2.5:14b
ollama pull llama3.1:8b
```

**Change model in `.env`:**
```bash
OLLAMA_DEFAULT_MODEL=qwen3-coder:30b  # or any other model
```

### Using API Providers (Optional)

To use OpenAI, Anthropic, or DeepSeek APIs, update `.env`:
```bash
DEFAULT_LLM_PROVIDER=openai  # or anthropic, deepseek
OPENAI_API_KEY=sk-...
```

## Development Commands

```bash
make help              # Show all available commands
make install           # Install Python dependencies locally
make dev               # Start development environment
make down              # Stop development environment
make logs              # View logs
make test              # Run tests
make test-cov          # Run tests with coverage
make lint              # Run linting
make format            # Format code
make migrate           # Run database migrations
make psql              # Open PostgreSQL shell
make redis-cli         # Open Redis CLI
```

## Configuration

All configuration is managed through environment variables. See `.env.example` for available options.

Key configurations:
- **LLM Providers**: Ollama (local), OpenAI, Anthropic, DeepSeek (API)
- **Embedding Model**: sentence-transformers (local) or OpenAI (API)
- **Adaptation Mode**: offline, online, or hybrid
- **Performance Settings**: checkpoint frequency, regression thresholds

## Project Structure

```
ace_enterprise/
├── src/
│   ├── core/               # ACE core modules
│   │   ├── generator/      # Task execution with playbook
│   │   ├── reflector/      # Error analysis & insights
│   │   └── curator/        # Playbook updates
│   ├── playbook/           # Playbook management
│   ├── reliability/        # Monitoring, checkpoints, rollback
│   ├── storage/            # Database models & storage
│   ├── api/                # REST API endpoints
│   ├── config/             # Configuration
│   └── utils/              # Utilities
├── tests/                  # Test suite
├── docker/                 # Docker configuration
├── docs/                   # Documentation
└── scripts/                # Utility scripts
```

## API Overview

### Core Endpoints (TODO)

- `POST /api/v1/tasks/execute` - Execute task with learning
- `GET /api/v1/playbooks/{id}` - Retrieve playbook
- `POST /api/v1/checkpoints` - Create checkpoint
- `POST /api/v1/rollback` - Rollback to checkpoint
- `GET /api/v1/logs/experiments` - Query experiment logs

See `/docs` for complete API documentation when available.

## Testing

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Run with coverage
make test-cov
```

## Documentation

- [Product Requirements Document](./PRD.md) - Complete system specifications
- [Architecture Guide](./docs/architecture.md) (TODO)
- [API Reference](http://localhost:8000/docs) (when running)
- [Deployment Guide](./docs/deployment.md) (TODO)

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: PostgreSQL 15+ with pgvector
- **Cache**: Redis 7+
- **Embeddings**: sentence-transformers (local)
- **LLM**: Ollama (local) or multi-provider APIs
- **Monitoring**: Prometheus + Grafana
- **Testing**: pytest

## Roadmap

### Phase 1 (Current): Foundation
- [x] Project structure and development environment
- [x] Configuration with Ollama support
- [ ] Data schemas and database migrations
- [ ] Core ACE modules (Generator, Reflector, Curator)

### Phase 2: Reliability
- [ ] Performance monitoring
- [ ] Checkpoint & rollback system
- [ ] Experiment logging and audit trails

### Phase 3: API & Integration
- [ ] REST API endpoints
- [ ] Authentication & authorization
- [ ] Webhook system

### Phase 4: Production Ready
- [ ] Comprehensive testing
- [ ] Documentation
- [ ] Deployment automation

## Contributing

(TODO: Add contribution guidelines)

## License

MIT License (TODO: Add license file)

## Support

For questions or issues:
- Open an issue on GitHub
- Check the documentation in `/docs`
- Review the PRD for detailed requirements

---

**Status**: Early Development (v0.1.0)

Built based on research from Stanford/SambaNova ACE framework and Stanford's Dynamic Cheatsheet.

**References:**
- ACE Paper: arXiv:2510.04618v1
- Dynamic Cheatsheet: arXiv:2504.07952v1
- AppWorld Benchmark: https://appworld.dev
