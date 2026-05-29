Feature: Embedding Service
  Generates vector embeddings for text using a sentence-transformer model

  Scenario: Embed valid text returns a non-empty list of floats
    Given an EmbeddingService instance
    When embed_text is called with "Hello world"
    Then a non-empty list of numbers is returned

  Scenario: Embed empty text returns an empty list
    Given an EmbeddingService instance
    When embed_text is called with an empty string
    Then an empty list is returned

  Scenario: Embed batch returns one vector per text
    Given an EmbeddingService instance
    When embed_batch is called with ["First text", "Second text", "Third text"]
    Then a list of 3 vectors is returned
    And each vector is a non-empty list of numbers

  Scenario: Cosine similarity of identical vectors is 1.0
    Given two vectors [1.0, 0.0, 0.0] and [1.0, 0.0, 0.0]
    When cosine_similarity is called
    Then the result is 1.0

  Scenario: Cosine similarity of orthogonal vectors is 0.0
    Given two vectors [1.0, 0.0, 0.0] and [0.0, 1.0, 0.0]
    When cosine_similarity is called
    Then the result is 0.0

  Scenario: Cosine similarity with an empty vector returns 0.0
    Given two vectors [] and [1.0, 2.0, 3.0]
    When cosine_similarity is called
    Then the result is 0.0
