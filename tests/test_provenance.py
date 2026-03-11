"""Tests for provenance matching in prompt-level distillation."""

import pytest

from src.playbook.distillation_router import (
    LicenseCategory,
    Provenance,
    Supplier,
    classify_license,
    detect_supplier,
    filter_bullets_by_provenance,
)
from src.storage.schemas import Bullet
from datetime import datetime


def make_bullet(
    content: str,
    created_by_model: str | None = None,
    model_provider: str | None = None,
    license_type: str | None = None,
) -> Bullet:
    """Factory for test bullets with provenance."""
    return Bullet(
        id=f"test-{hash(content) % 10000}",
        content=content,
        section="strategies_and_hard_rules",
        tags=[],
        created_by_model=created_by_model,
        model_provider=model_provider,
        license_type=license_type,
        created_at=datetime.now(),
    )


class TestSupplierDetection:
    """Tests for detect_supplier function."""

    def test_openai_models(self):
        assert detect_supplier("gpt-4o") == Supplier.OPENAI
        assert detect_supplier("gpt-4-turbo") == Supplier.OPENAI
        assert detect_supplier("o1-mini") == Supplier.OPENAI
        assert detect_supplier(None, "openai") == Supplier.OPENAI

    def test_anthropic_models(self):
        assert detect_supplier("claude-3-opus") == Supplier.ANTHROPIC
        assert detect_supplier("claude-sonnet") == Supplier.ANTHROPIC
        assert detect_supplier(None, "anthropic") == Supplier.ANTHROPIC

    def test_google_models(self):
        assert detect_supplier("gemini-pro") == Supplier.GOOGLE
        assert detect_supplier("gemini-flash") == Supplier.GOOGLE
        assert detect_supplier("gemma-7b") == Supplier.GOOGLE  # Open source, still Google
        assert detect_supplier(None, "google") == Supplier.GOOGLE

    def test_meta_models(self):
        assert detect_supplier("llama-3.1-70b") == Supplier.META
        assert detect_supplier("llama2") == Supplier.META
        assert detect_supplier("codellama") == Supplier.META

    def test_alibaba_models(self):
        assert detect_supplier("qwen2.5-72b") == Supplier.ALIBABA
        assert detect_supplier("qwen-coder") == Supplier.ALIBABA

    def test_mistral_models(self):
        assert detect_supplier("mistral-7b") == Supplier.MISTRAL
        assert detect_supplier("mixtral-8x7b") == Supplier.MISTRAL

    def test_microsoft_models(self):
        assert detect_supplier("phi-3") == Supplier.MICROSOFT
        assert detect_supplier("phi-4") == Supplier.MICROSOFT

    def test_unknown_models(self):
        assert detect_supplier("some-random-model") == Supplier.UNKNOWN
        assert detect_supplier(None, None) == Supplier.UNKNOWN


class TestLicenseClassification:
    """Tests for classify_license function."""

    def test_explicit_open_source_license(self):
        assert classify_license(license_type="apache-2.0") == LicenseCategory.OPEN_SOURCE
        assert classify_license(license_type="MIT") == LicenseCategory.OPEN_SOURCE
        assert classify_license(license_type="GPL-3.0") == LicenseCategory.OPEN_SOURCE

    def test_explicit_proprietary_license(self):
        assert classify_license(license_type="proprietary") == LicenseCategory.PROPRIETARY
        assert classify_license(license_type="commercial") == LicenseCategory.PROPRIETARY

    def test_open_source_models(self):
        assert classify_license(model_name="llama-3.1-70b") == LicenseCategory.OPEN_SOURCE
        assert classify_license(model_name="qwen2.5-coder") == LicenseCategory.OPEN_SOURCE
        assert classify_license(model_name="gemma-7b") == LicenseCategory.OPEN_SOURCE
        assert classify_license(model_name="mistral-7b") == LicenseCategory.OPEN_SOURCE

    def test_proprietary_models(self):
        assert classify_license(model_name="gpt-4o") == LicenseCategory.PROPRIETARY
        assert classify_license(model_name="claude-3-opus") == LicenseCategory.PROPRIETARY
        assert classify_license(model_name="gemini-pro") == LicenseCategory.PROPRIETARY

    def test_ollama_provider_implies_open_source(self):
        assert classify_license(provider="ollama") == LicenseCategory.OPEN_SOURCE

    def test_unknown(self):
        assert classify_license() == LicenseCategory.UNKNOWN
        assert classify_license(model_name="mystery-model") == LicenseCategory.UNKNOWN


class TestProvenance:
    """Tests for Provenance class."""

    def test_from_model(self):
        prov = Provenance.from_model("gpt-4o", "openai")
        assert prov.supplier == Supplier.OPENAI
        assert prov.license_category == LicenseCategory.PROPRIETARY

    def test_from_bullet(self):
        bullet = make_bullet(
            "test",
            created_by_model="claude-3-opus",
            model_provider="anthropic",
        )
        prov = Provenance.from_bullet(bullet)
        assert prov.supplier == Supplier.ANTHROPIC
        assert prov.license_category == LicenseCategory.PROPRIETARY


class TestProvenanceCanTeach:
    """Tests for Provenance.can_teach method."""

    def test_same_supplier_always_allowed(self):
        """Google Gemini can teach Google Gemma."""
        teacher = Provenance(Supplier.GOOGLE, LicenseCategory.PROPRIETARY)
        student = Provenance(Supplier.GOOGLE, LicenseCategory.OPEN_SOURCE)
        assert teacher.can_teach(student, allow_cross_supplier_proprietary=False)

    def test_open_source_can_teach_anyone(self):
        """Llama can teach Qwen (cross-supplier, both open)."""
        teacher = Provenance(Supplier.META, LicenseCategory.OPEN_SOURCE)
        student = Provenance(Supplier.ALIBABA, LicenseCategory.OPEN_SOURCE)
        assert teacher.can_teach(student, allow_cross_supplier_proprietary=False)

    def test_open_source_can_teach_proprietary(self):
        """Llama can teach Claude (open → proprietary OK)."""
        teacher = Provenance(Supplier.META, LicenseCategory.OPEN_SOURCE)
        student = Provenance(Supplier.ANTHROPIC, LicenseCategory.PROPRIETARY)
        assert teacher.can_teach(student, allow_cross_supplier_proprietary=False)

    def test_cross_supplier_proprietary_blocked_by_default(self):
        """GPT-4 cannot teach Claude by default."""
        teacher = Provenance(Supplier.OPENAI, LicenseCategory.PROPRIETARY)
        student = Provenance(Supplier.ANTHROPIC, LicenseCategory.PROPRIETARY)
        assert not teacher.can_teach(student, allow_cross_supplier_proprietary=False)

    def test_cross_supplier_proprietary_allowed_when_configured(self):
        """GPT-4 can teach Claude when configured."""
        teacher = Provenance(Supplier.OPENAI, LicenseCategory.PROPRIETARY)
        student = Provenance(Supplier.ANTHROPIC, LicenseCategory.PROPRIETARY)
        assert teacher.can_teach(student, allow_cross_supplier_proprietary=True)

    def test_proprietary_cannot_teach_cross_supplier_open_source(self):
        """GPT-4 cannot teach Qwen (proprietary → cross-supplier open)."""
        teacher = Provenance(Supplier.OPENAI, LicenseCategory.PROPRIETARY)
        student = Provenance(Supplier.ALIBABA, LicenseCategory.OPEN_SOURCE)
        assert not teacher.can_teach(student, allow_cross_supplier_proprietary=False)

    def test_unknown_supplier_is_permissive(self):
        """Unknown supplier allows teaching."""
        teacher = Provenance(Supplier.UNKNOWN, LicenseCategory.UNKNOWN)
        student = Provenance(Supplier.OPENAI, LicenseCategory.PROPRIETARY)
        assert teacher.can_teach(student, allow_cross_supplier_proprietary=False)


class TestFilterBulletsByProvenance:
    """Tests for filter_bullets_by_provenance function."""

    def test_filters_cross_supplier_proprietary(self):
        """Should filter out cross-supplier proprietary bullets."""
        bullets = [
            make_bullet("OpenAI tip", created_by_model="gpt-4o", model_provider="openai"),
            make_bullet("Anthropic tip", created_by_model="claude-3", model_provider="anthropic"),
            make_bullet("Llama tip", created_by_model="llama-3", model_provider="ollama"),
        ]

        # Anthropic student
        student = Provenance(Supplier.ANTHROPIC, LicenseCategory.PROPRIETARY)
        filtered = filter_bullets_by_provenance(
            bullets, student, allow_cross_supplier_proprietary=False
        )

        # Should only include Anthropic and open source (Llama)
        assert len(filtered) == 2
        contents = [b.content for b in filtered]
        assert "Anthropic tip" in contents
        assert "Llama tip" in contents
        assert "OpenAI tip" not in contents

    def test_allows_same_supplier_mixed_license(self):
        """Same supplier can mix proprietary and open source."""
        bullets = [
            make_bullet("Gemini tip", created_by_model="gemini-pro"),
            make_bullet("Gemma tip", created_by_model="gemma-7b"),
        ]

        # Google open source student (Gemma)
        student = Provenance(Supplier.GOOGLE, LicenseCategory.OPEN_SOURCE)
        filtered = filter_bullets_by_provenance(
            bullets, student, allow_cross_supplier_proprietary=False
        )

        # Both should be included (same supplier)
        assert len(filtered) == 2

    def test_open_source_ecosystem_interoperable(self):
        """Open source bullets can flow freely across suppliers."""
        bullets = [
            make_bullet("Llama tip", created_by_model="llama-3"),
            make_bullet("Qwen tip", created_by_model="qwen2.5"),
            make_bullet("Mistral tip", created_by_model="mistral-7b"),
        ]

        # Any open source student
        student = Provenance(Supplier.DEEPSEEK, LicenseCategory.OPEN_SOURCE)
        filtered = filter_bullets_by_provenance(
            bullets, student, allow_cross_supplier_proprietary=False
        )

        # All should be included
        assert len(filtered) == 3

    def test_respects_allow_cross_supplier_flag(self):
        """Flag enables cross-supplier proprietary."""
        bullets = [
            make_bullet("GPT tip", created_by_model="gpt-4o"),
        ]

        student = Provenance(Supplier.ANTHROPIC, LicenseCategory.PROPRIETARY)

        # Without flag: filtered out
        filtered_strict = filter_bullets_by_provenance(
            bullets, student, allow_cross_supplier_proprietary=False
        )
        assert len(filtered_strict) == 0

        # With flag: included
        filtered_permissive = filter_bullets_by_provenance(
            bullets, student, allow_cross_supplier_proprietary=True
        )
        assert len(filtered_permissive) == 1
