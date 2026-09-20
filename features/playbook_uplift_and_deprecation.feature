# Spec/documentation for a hand-implemented change, NOT built via `ace tdd`:
# this feature surgically extends three EXISTING files (src/audit/schemas.py,
# src/reliability/playbook_analyzer.py, src/playbook/manager.py) rather than
# generating one new module from scratch, which is the only shape `ace tdd`'s
# Gherkin-driven IterativeTDDRunner actually supports (one .feature -> one
# fresh {stem}.py/test_{stem}.py pair). See tests/test_reliability.py and
# tests/test_playbook_manager.py for the real pytest coverage.
#
# This is ace_enterprise's half of a two-repo split: dream_rsi's own
# audit_ingestion_and_pruning_driver.feature consumes what this produces
# (the uplift computation and the deprecation event) from the outside, via
# ace_enterprise's real SQLite-backed AuditStore -- it never needs to know
# about DiscoveryTree/ReplayEnvironment, which stay in dream_rsi.

Feature: Playbook bullet causal uplift and deprecation
  As a playbook maintainer
  I want to compute a bullet's true causal uplift, with a real control group,
  and safely deprecate bullets that measurably hurt outcomes
  So that guidance can be pruned on evidence, with the removal itself
  recorded on the tamper-evident audit chain

  Background:
    Given a playbook with bullets that have been retrieved across multiple TDD cycles
    And an audit trail recording each cycle's outcome and which bullets were retrieved

  Scenario: Computing causal uplift for a bullet with both treatment and control cycles
    Given cycles where bullet "b1" was retrieved, some first-pass GREEN and some not
    And cycles where bullet "b1" was NOT retrieved, some first-pass GREEN and some not
    When I compute bullet_uplift for "b1"
    Then the result is P(GREEN | b1 retrieved) minus P(GREEN | b1 not retrieved)

  Scenario: A bullet with no control-group cycles has undefined uplift
    Given every recorded cycle retrieved bullet "b2"
    When I compute bullet_uplift for "b2"
    Then the uplift is reported as unavailable, not a fabricated number

  Scenario: A bullet below the minimum sample threshold is excluded from ranking
    Given bullet "b3" was retrieved in fewer cycles than min_samples requires
    When I compute bullet_uplift with min_samples 3
    Then "b3" is excluded from the ranked results

  Scenario: Deprecating a bullet removes it from the playbook and appends a hash-chained event
    Given an active bullet "b4" in the playbook
    When PlaybookManager.deprecate_bullet is called for "b4" with a reason
    Then "b4" is no longer present in the playbook's active bullets
    And a PLAYBOOK_BULLET_DEPRECATED event is appended to the audit chain
    And every previously recorded audit event remains unmodified and still verifies against the hash chain

  Scenario: Deprecation without an audit client still removes the bullet
    Given an active bullet "b5" in the playbook
    When PlaybookManager.deprecate_bullet is called for "b5" with no audit client
    Then "b5" is no longer present in the playbook's active bullets
    And no error is raised
