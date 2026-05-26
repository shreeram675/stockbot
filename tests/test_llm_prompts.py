from app.services.llm_prompts import (
    portfolio_question_prompt,
    recommendation_note_prompt,
)


def test_recommendation_note_prompt_has_role_and_grounding_rules() -> None:
    prompt = recommendation_note_prompt(
        portfolio={"portfolio_value": 10000, "holdings": [{"symbol": "ABC"}]},
        risk_profile="Aggressive",
        plan_context={"actions": [{"action": "BUY", "symbol": "NIFTYBEES"}]},
        news_status="included",
        news=[{"headline": "Market update"}],
    )

    assert "cautious Indian portfolio analyst" in prompt
    assert "maximize long-term, after-cost, risk-adjusted wealth" in prompt
    assert "Use only the supplied data" in prompt
    assert "Do not invent holdings, prices, news, targets, quantities, or returns" in prompt
    assert "Risk profile: Aggressive" in prompt
    assert "NIFTYBEES" in prompt


def test_portfolio_question_prompt_frames_actions_as_review() -> None:
    prompt = portfolio_question_prompt(
        question="How do I maximize my portfolio?",
        snapshot={"portfolio_value": 5000},
        holdings=[{"symbol": "ABC", "market_value": 5000}],
    )

    assert "long-term risk-adjusted returns" in prompt
    assert "concentration" in prompt
    assert "not an automatic order" in prompt
    assert "How do I maximize my portfolio?" in prompt
