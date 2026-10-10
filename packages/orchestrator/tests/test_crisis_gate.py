"""Unit tests for the crisis detection gate (TRD-SAFETY-1).

Tests cover:
1. First-person crisis expressions → detect_crisis returns True
2. Policy/training/third-person context → detect_crisis returns False
3. Ordinary policy questions → detect_crisis returns False
4. Response formatting
"""

import pytest

from ask_bpl_orchestrator.services.crisis_gate import (
    CrisisConfig,
    CrisisResource,
    DEFAULT_CRISIS_CONFIG,
    detect_crisis,
    format_crisis_response,
    get_crisis_config,
)


class TestCrisisDetection:
    """Test detect_crisis() correctly identifies crisis vs. non-crisis input."""

    # First-person suicidal ideation — should trigger
    @pytest.mark.parametrize(
        "text",
        [
            "I'm thinking about ending my life",
            "I am thinking about ending it all",
            "I've been considering suicide",
            "I want to die",
            "I want to end it",
            "I want to kill myself",
            "I don't want to live anymore",
            "I don't want to be here anymore",
            "I don't want to exist",
            "I'm going to kill myself",
            "I am suicidal",
            "I'm going to end it",
            "How do I kill myself",
            "How can I end my life",
            "I have no reason to live",
            "I see no point in living",
            "No one would miss me if I was gone",
            "Nobody would care if I died",
        ],
    )
    def test_detects_first_person_suicidal_ideation(self, text: str) -> None:
        assert detect_crisis(text) is True, f"Should detect crisis in: {text!r}"

    # First-person self-harm intent — should trigger
    @pytest.mark.parametrize(
        "text",
        [
            "I'm thinking about hurting myself",
            "I want to hurt myself",
            "I'm planning to cut myself",
            "I want to harm myself",
            "I'm going to hurt myself tonight",
        ],
    )
    def test_detects_first_person_self_harm(self, text: str) -> None:
        assert detect_crisis(text) is True, f"Should detect crisis in: {text!r}"

    # Policy/training context — should NOT trigger
    @pytest.mark.parametrize(
        "text",
        [
            "What is BPL's policy on suicide prevention?",
            "What is the procedure for suicide prevention training?",
            "What are the guidelines for handling patron self-harm?",
            "Tell me about the crisis intervention protocol",
            "What training do staff receive about suicide awareness?",
            "What is the policy on mental health crisis situations?",
        ],
    )
    def test_does_not_trigger_on_policy_questions(self, text: str) -> None:
        assert detect_crisis(text) is False, f"Should NOT detect crisis in: {text!r}"

    # Third-person / patron context — should NOT trigger
    @pytest.mark.parametrize(
        "text",
        [
            "If a patron mentions suicide, what should I do?",
            "What if someone expresses suicidal thoughts?",
            "How do we help a patron who is suicidal?",
            "What should staff do if a person mentions self-harm?",
            "A patron told me they want to die. What's the procedure?",
            "What if they say they want to end it all?",
            "How should we respond when someone mentions suicide?",
        ],
    )
    def test_does_not_trigger_on_third_person(self, text: str) -> None:
        assert detect_crisis(text) is False, f"Should NOT detect crisis in: {text!r}"

    # Ordinary policy questions — should NOT trigger
    @pytest.mark.parametrize(
        "text",
        [
            "What is the annual leave policy?",
            "How do I request vacation time?",
            "What are the gift acceptance rules?",
            "Tell me about the conflict of interest policy",
            "What is the procedure for materials selection?",
            "What are the technology usage guidelines?",
            "How should I handle unattended children?",
            "What is the fundraising policy?",
            "Can I volunteer at the library?",
            "What is the policy on computer use?",
        ],
    )
    def test_does_not_trigger_on_ordinary_questions(self, text: str) -> None:
        assert detect_crisis(text) is False, f"Should NOT detect crisis in: {text!r}"

    # Edge cases
    def test_empty_string(self) -> None:
        assert detect_crisis("") is False

    def test_whitespace_only(self) -> None:
        assert detect_crisis("   \n\t  ") is False

    def test_none_like_edge(self) -> None:
        # Technically string, but effectively empty
        assert detect_crisis("   ") is False


class TestCrisisConfig:
    """Test crisis configuration structure."""

    def test_default_config_has_required_fields(self) -> None:
        config = get_crisis_config()
        assert config.opening_message
        assert config.closing_message
        assert len(config.resources) >= 1

    def test_default_config_has_988_lifeline(self) -> None:
        config = get_crisis_config()
        resource_names = [r.name for r in config.resources]
        assert any("988" in name for name in resource_names)

    def test_default_config_has_bpl_placeholder(self) -> None:
        config = get_crisis_config()
        resource_names = [r.name for r in config.resources]
        assert any("BPL" in name or "EAP" in name for name in resource_names)


class TestCrisisResponse:
    """Test crisis response formatting."""

    def test_format_uses_default_config(self) -> None:
        response = format_crisis_response()
        assert response["type"] == "crisis_resource"
        assert "message" in response
        assert "resources" in response
        assert "closing" in response

    def test_format_uses_custom_config(self) -> None:
        custom = CrisisConfig(
            opening_message="Custom opening",
            resources=(
                CrisisResource(name="Test Resource", contact="1-800-TEST", description="Test"),
            ),
            closing_message="Custom closing",
        )
        response = format_crisis_response(custom)
        assert response["type"] == "crisis_resource"
        assert response["message"] == "Custom opening"
        assert response["closing"] == "Custom closing"
        assert len(response["resources"]) == 1
        assert response["resources"][0]["name"] == "Test Resource"
        assert response["resources"][0]["contact"] == "1-800-TEST"

    def test_response_type_is_crisis_resource(self) -> None:
        response = format_crisis_response()
        assert response["type"] == "crisis_resource"

    def test_resources_are_list_of_dicts(self) -> None:
        response = format_crisis_response()
        assert isinstance(response["resources"], list)
        for resource in response["resources"]:
            assert isinstance(resource, dict)
            assert "name" in resource
            assert "contact" in resource
            assert "description" in resource


class TestCrisisWithPolicyWording:
    """A first-person expression of intent must not be suppressed by policy words (SAF-3, AC-6)."""

    @pytest.mark.parametrize(
        "text",
        [
            "I want to die. Is there a suicide prevention policy I can read?",
            "I'm thinking about ending my life and need the crisis policy",
            "I want to end it all, what should staff do if they feel this way",
            "I want to kill myself. What does the crisis procedure say?",
            "I don't want to live anymore, what is the EAP procedure",
        ],
    )
    def test_first_person_intent_plus_policy_words_still_triggers(self, text: str) -> None:
        assert detect_crisis(text) is True, f"Should detect crisis in: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "What is the crisis management policy?",
            "A patron said he is suicidal, what should I do?",
            "What does the suicide prevention training cover?",
            "What should staff do if a patron says they want to die?",
        ],
    )
    def test_policy_and_third_person_questions_still_pass(self, text: str) -> None:
        assert detect_crisis(text) is False, f"Should not trigger on: {text!r}"
