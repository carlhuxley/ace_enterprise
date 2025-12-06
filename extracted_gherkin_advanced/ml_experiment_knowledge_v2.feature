Feature: ML Experiment Knowledge Management
  Captures a decision made during ML experimentation.

  Scenario: Create decision with required fields
    Given a experiment decision with decision_id='dec_001', timestamp=datetime(2025, 12, 6, 10, 30), question='Which optimizer to use?', decision='Adam with lr=0.001', rationale='SGD was unstable in pilot runs'
    Then decision.decision id should be 'dec_001'
    Then decision.question should be 'Which optimizer to use?'
    Then decision.decision should be 'Adam with lr=0.001'
    Then decision.rationale should be 'SGD was unstable in pilot runs'

  Scenario: Create decision with alternatives
    Given a experiment decision with decision_id='dec_002', timestamp=datetime.now(), question='Which batch size?', decision='128', rationale='Good balance of speed and stability', alternatives_considered=['64', '256', '512']
    Then decision.alternatives considered should be ['64', '256', '512']
    Then len(decision.alternatives considered) should be 3

  Scenario: Decision with outcome tracking
    Given a experiment decision with decision_id='dec_003', timestamp=datetime.now(), question='Use dropout?', decision='Yes, 0.5 rate', rationale='Prevent overfitting', outcome='successful', learned_insight='Dropout improved validation accuracy by 3%'
    Then decision.outcome should be 'successful'
    Then decision.learned insight should be 'Dropout improved validation accuracy by 3%'

  Scenario: Decision serialization to dict
    Given a experiment decision with decision_id='dec_004', timestamp=datetime(2025, 12, 6, 10, 30), question='Test question', decision='Test decision', rationale='Test rationale'
    Then decision dict['decision id'] should be 'dec_004'
    Then decision dict['question'] should be 'Test question'
    Then decision dict['decision'] should be 'Test decision'
    Then decision_dict should contain 'timestamp'

  Scenario: Decision deserialization from dict
    Then decision.decision id should be 'dec_005'
    Then decision.question should be 'Original question'
    Then decision.alternatives considered should be ['alt1', 'alt2']

  Scenario: Create pattern with success metrics
    Given a experiment pattern with pattern_id='pat_001', pattern_name='Learning rate warmup', description='Gradually increase LR for first epoch', observed_in_experiments=['run_123', 'run_456', 'run_789'], success_rate=0.85, avg_improvement=0.03, when_to_apply='When batch_size > 256', implementation='Use lr_scheduler.LinearLR(start_factor=0.1)', discovered_date=datetime(2025, 12, 1)
    Then pattern.pattern name should be 'Learning rate warmup'
    Then pattern.success rate should be 0.85
    Then pattern.avg improvement should be 0.03
    Then len(pattern.observed in experiments) should be 3

  Scenario: Pattern with domain tags
    Given a experiment pattern with pattern_id='pat_002', pattern_name='Differential privacy for HIPAA', description='Add noise to protect patient data', observed_in_experiments=['healthcare_01'], success_rate=1.0, when_to_apply='When handling healthcare data', implementation='Use opacus library', domain_tags=['healthcare', 'privacy', 'compliance'], discovered_date=datetime.now()
    Then pattern.domain_tags should contain 'healthcare'
    Then pattern.domain_tags should contain 'privacy'
    Then pattern.domain_tags should contain 'compliance'

  Scenario: Pattern with antipatterns
    Given a experiment pattern with pattern_id='pat_003', pattern_name='Batch normalization', description='Normalize activations', observed_in_experiments=['exp_01'], success_rate=0.9, when_to_apply='Deep networks', implementation='Add BatchNorm2d layers', antipatterns=["Don't use with very small batches (< 4)", "Don't combine with dropout in same layer"], discovered_date=datetime.now()
    Then len(pattern.antipatterns) should be 2
    Then pattern.antipatterns[0] should contain "Don't use with very small batches"

  Scenario: Create empty knowledge base
    Given a m l experiment knowledge with experiment_name='test_experiment'
    Then knowledge.experiment name should be 'test_experiment'
    Then len(knowledge.decisions) should be 0
    Then len(knowledge.patterns) should be 0

  Scenario: Add decision to knowledge base
    Given a m l experiment knowledge with experiment_name='test_experiment'
    Given a experiment decision with decision_id='dec_001', timestamp=datetime.now(), question='Which optimizer?', decision='Adam', rationale='Best for this problem'
    When I add decision with decision
    Then len(knowledge.decisions) should be 1
    Then knowledge.decisions[0].decision id should be 'dec_001'

  Scenario: Add multiple decisions
    Given a m l experiment knowledge with experiment_name='test_experiment'
    Then len(knowledge.decisions) should be 5

  Scenario: Get decisions for specific run
    Given a m l experiment knowledge with experiment_name='test_experiment', mlflow_experiment_id='exp_123'
    Given a experiment decision with decision_id='dec_001', timestamp=datetime.now(), question='Q1', decision='D1', rationale='R1', context={'mlflow_run_id': 'run_001'}
    Given a experiment decision with decision_id='dec_002', timestamp=datetime.now(), question='Q2', decision='D2', rationale='R2', context={'mlflow_run_id': 'run_002'}
    When I add decision with decision1
    Then len(run 001 decisions) should be 1
    Then run 001 decisions[0].decision id should be 'dec_001'

  Scenario: Add pattern to knowledge base
    Given a m l experiment knowledge with experiment_name='test_experiment'
    Given a experiment pattern with pattern_id='pat_001', pattern_name='Test pattern', description='Test description', observed_in_experiments=['run_001'], success_rate=0.8, when_to_apply='Test condition', implementation='Test implementation', discovered_date=datetime.now()
    When I add pattern with pattern
    Then len(knowledge.patterns) should be 1
    Then knowledge.patterns[0].pattern id should be 'pat_001'

  Scenario: Get patterns by domain
    Given a m l experiment knowledge with experiment_name='test_experiment'
    Given a experiment pattern with pattern_id='pat_cv', pattern_name='Data augmentation', description='Augment training images', observed_in_experiments=['run_001'], success_rate=0.9, when_to_apply='Image classification', implementation='Use torchvision.transforms', domain_tags=['computer_vision', 'image_classification'], discovered_date=datetime.now()
    Given a experiment pattern with pattern_id='pat_nlp', pattern_name='Tokenization', description='Subword tokenization', observed_in_experiments=['run_002'], success_rate=0.85, when_to_apply='Text processing', implementation='Use transformers.AutoTokenizer', domain_tags=['nlp', 'text_processing'], discovered_date=datetime.now()
    When I add pattern with cv_pattern
    Then len(cv patterns) should be 1
    Then cv patterns[0].pattern id should be 'pat_cv'

  Scenario: Get successful patterns above threshold
    Given a m l experiment knowledge with experiment_name='test_experiment'
    Given a experiment pattern with pattern_id='pat_high', pattern_name='High success pattern', description='Works great', observed_in_experiments=['run_001'], success_rate=0.95, when_to_apply='Always', implementation='Do this', discovered_date=datetime.now()
    Given a experiment pattern with pattern_id='pat_low', pattern_name='Low success pattern', description='Sometimes works', observed_in_experiments=['run_002'], success_rate=0.55, when_to_apply='Rarely', implementation='Try this', discovered_date=datetime.now()
    When I add pattern with high_success
    Then len(successful patterns) should be 1
    Then successful patterns[0].pattern id should be 'pat_high'

  Scenario: Save and load knowledge base
    Given a m l experiment knowledge with experiment_name='test_experiment'
    Given a experiment decision with decision_id='dec_001', timestamp=datetime.now(), question='Test', decision='Test decision', rationale='Test rationale'
    When I add decision with decision
    Then loaded knowledge.experiment name should be 'test_experiment'
    Then len(loaded knowledge.decisions) should be 1
    Then loaded knowledge.decisions[0].decision id should be 'dec_001'

