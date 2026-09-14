"""Tests for src/utils/embedding.py.

Every other test in this repo that touches embeddings fakes EmbeddingService
entirely (see tests/test_playbook_manager.py's _FakeEmbeddingService) --
before this file, the real sentence-transformers model was never actually
exercised by the test suite. That's exactly the gap that let a dependency
bump silently change embedding output without any test noticing
(ace_enterprise#49): sentence-transformers 5.4.1 -> 6.0.1 turned out to
produce bit-identical vectors for this model, verified by hand across both
embed_text()'s and embed_batch()'s exact call shapes, but nothing would
have caught it if it hadn't.

Golden vectors below were computed with the real model and locked in as a
regression check -- skipped, not failed, if the model/network isn't
available (matching src/utils/embedding.py's own _HAS_TORCH fallback), so
this never makes CI hard-depend on a Hugging Face Hub download succeeding.
"""
import math

import pytest

from src.utils.embedding import EmbeddingService

_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _real_service() -> EmbeddingService:
    service = EmbeddingService(model_name=_MODEL, device="cpu")
    if service.model is None:
        pytest.skip("sentence-transformers model unavailable (no torch, or no network to fetch it)")
    return service


# Computed with the real model, sentence-transformers 6.0.1 -- confirmed
# bit-for-bit identical against 5.4.1 in an isolated venv while
# investigating #49. If these ever change, that's exactly the "did a
# dependency bump silently change embedding output" signal this test
# exists to catch.
_GOLDEN_TEXT = "Never log secrets or API keys in plaintext."
_GOLDEN_DIM = 384
_GOLDEN_FIRST_5 = [
    -0.02192922867834568,
    0.04203682392835617,
    -0.033296894282102585,
    0.004880063235759735,
    0.019015008583664894,
]


class TestRealModelGoldenVector:
    def test_embedding_dimension_matches_known_model_output(self):
        service = _real_service()
        vec = service.embed_text(_GOLDEN_TEXT)
        assert len(vec) == _GOLDEN_DIM

    def test_embedding_values_match_golden_vector(self):
        """A future dependency bump (sentence-transformers, transformers,
        torch) that silently changes pooling/normalization/precision and
        shifts embedding output should fail here instead of only showing up
        as an unexplained drop in retrieval quality."""
        service = _real_service()
        vec = service.embed_text(_GOLDEN_TEXT)
        for actual, expected in zip(vec[:5], _GOLDEN_FIRST_5, strict=True):
            assert math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-6), (
                f"embedding drifted from the golden vector: {vec[:5]} != {_GOLDEN_FIRST_5}"
            )

    def test_embed_text_and_embed_batch_agree_on_the_same_string(self):
        """embed_text() and embed_batch() go through different encode()
        call shapes (single string vs. list + batch_size/show_progress_bar)
        -- confirm they don't silently diverge for the same input."""
        service = _real_service()
        single = service.embed_text(_GOLDEN_TEXT)
        batch = service.embed_batch([_GOLDEN_TEXT])[0]
        assert single == pytest.approx(batch, rel=1e-5, abs=1e-6)
