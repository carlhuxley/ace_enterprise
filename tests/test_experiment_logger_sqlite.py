"""
Tests for ExperimentLogger SQLite fallback path.

Verifies that when PostgreSQL is unavailable, ExperimentLogger falls back
to a local SQLite database and log_tdd_cycle() still persists records.
"""
from src.storage.experiment_logger import ExperimentLogger, _SQLiteRepo


def test_sqlite_repo_creates_table_and_logs(tmp_path):
    db_path = str(tmp_path / "test_experiments.db")
    repo = _SQLiteRepo(path=db_path)

    logger = ExperimentLogger(playbook_version="test-1.0", repository=repo)
    logger.log_tdd_cycle(
        cycle_number=1,
        requirement="add two numbers",
        test_name="test_add",
        test_code="def test_add(): assert add(1,2)==3",
        implementation_code="def add(a,b): return a+b",
        red_passed=False,
        green_passed=True,
        red_output="1 failed",
        green_output="1 passed",
        learned_bullets=[],
        playbook_id="sqlite-test",
        tokens_used=100,
        retry_count=1,
    )

    with repo.get_session() as session:
        from src.storage.models import ExperimentLogModel
        records = session.query(ExperimentLogModel).all()

    assert len(records) == 1
    assert records[0].result == "SUCCESS"
    assert records[0].task_data["requirement"] == "add two numbers"


def test_experiment_logger_falls_back_to_sqlite_when_postgres_unavailable(tmp_path, monkeypatch):
    """If PlaybookRepository raises on init, _connect_with_fallback uses SQLite."""
    import src.storage.experiment_logger as mod

    original_sqlite = mod._SQLiteRepo

    created = []

    class _CapturingSQLiteRepo(original_sqlite):
        def __init__(self, path="ace_experiments.db"):
            super().__init__(path=str(tmp_path / "fallback.db"))
            created.append(self)

    monkeypatch.setattr(mod, "_SQLiteRepo", _CapturingSQLiteRepo)
    monkeypatch.setattr(
        "src.storage.experiment_logger.PlaybookRepository",
        lambda: (_ for _ in ()).throw(Exception("postgres down")),
    )

    logger = ExperimentLogger(playbook_version="1.0")
    assert len(created) == 1, "Should have fallen back to SQLite"
    assert isinstance(logger.repo, _CapturingSQLiteRepo)


def test_log_tdd_cycle_upserts_on_duplicate_experiment_id(tmp_path):
    """Second call with the same experiment_id must update, not raise."""
    repo = _SQLiteRepo(path=str(tmp_path / "upsert.db"))
    exp_logger = ExperimentLogger(playbook_version="1.0", repository=repo)

    kwargs = dict(
        cycle_number=1,
        requirement="add two numbers",
        test_name="test_add",
        test_code="def test_add(): assert add(1,2)==3",
        implementation_code="def add(a,b): return a+b",
        red_passed=False,
        green_passed=False,
        red_output="1 failed",
        green_output="1 failed",
        learned_bullets=[],
        playbook_id="upsert-test",
        retry_count=1,
    )
    exp_logger.log_tdd_cycle(**kwargs)

    # Second call — same experiment_id, updated outcome
    exp_logger.log_tdd_cycle(**{**kwargs, "green_passed": True, "green_output": "1 passed"})

    from src.storage.models import ExperimentLogModel
    with repo.get_session() as session:
        records = session.query(ExperimentLogModel).all()

    assert len(records) == 1, "upsert must not create a duplicate row"
    assert records[0].result == "SUCCESS"
