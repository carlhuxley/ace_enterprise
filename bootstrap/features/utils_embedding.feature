Feature: Embedding Service
  As a caller of the embedding service
  I want to generate vector embeddings for text and compare them
  So that I can measure semantic similarity between playbook bullets

  Scenario: Generate an embedding for a single non-empty text
    Given an EmbeddingService with a loaded model
    When I call embed_text with "Rotate credentials after every incident"
    Then I receive a non-empty list of floats representing the embedding vector

  Scenario: Generate embedding for empty text returns empty list
    Given an EmbeddingService with a loaded model
    When I call embed_text with ""
    Then I receive an empty list

  Scenario: Generate embedding for whitespace-only text returns empty list
    Given an EmbeddingService with a loaded model
    When I call embed_text with "   "
    Then I receive an empty list

  Scenario: Batch embed multiple valid texts
    Given an EmbeddingService with a loaded model
    When I call embed_batch with ["Restart the service", "Check the logs", "Notify the on-call engineer"]
    Then I receive a list of 3 embedding vectors, each a non-empty list of floats

  Scenario: Batch embed preserves output length when some texts are empty
    Given an EmbeddingService with a loaded model
    When I call embed_batch with ["Rotate keys", "", "   "]
    Then I receive a list of 3 results

  Scenario: Batch embed an empty list returns an empty list
    Given an EmbeddingService with a loaded model
    When I call embed_batch with []
    Then I receive an empty list

  Scenario: Retrieve the embedding dimension of the loaded model
    Given an EmbeddingService with a loaded model
    When I call get_embedding_dimension
    Then I receive a positive integer representing the vector dimension

  Scenario: Compute cosine similarity between two identical vectors
    Given the vectors [1.0, 0.0, 0.0] and [1.0, 0.0, 0.0]
    When I call cosine_similarity with these vectors
    Then I receive a similarity score of 1.0

  Scenario: Compute cosine similarity between two orthogonal vectors
    Given the vectors [1.0, 0.0] and [0.0, 1.0]
    When I call cosine_similarity with these vectors
    Then I receive a similarity score of 0.0

  Scenario: Compute cosine similarity when one vector is empty
    Given the vectors [] and [1.0, 0.0]
    When I call cosine_similarity with these vectors
    Then I receive a similarity score of 0.0

  Scenario: Retrieve the shared embedding service instance
    When I call get_embedding_service twice
    Then both calls return the same EmbeddingService instance