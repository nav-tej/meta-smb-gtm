"""Unit and parity tests for brand tone normalization, starter plans, and creator.js parity."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from src.models.content_plan import ContentPlanDraft, ContentPlanRequest, ContentPost, PlanProduct
from src.services.brand_tone import (
    BRAND_TONES,
    LEGACY_TONE_MAP,
    normalize_tone,
    tone_prompt_line,
)
from src.services.content_plan import ContentPlanService, starter_plan

REPO_ROOT = Path(__file__).resolve().parent.parent
BANNED_PATTERNS = [
    re.compile(r"\bbest\b", re.I),
    re.compile(r"\blimited\b", re.I),
    re.compile(r"only a few left", re.I),
    re.compile(r"\bguaranteed?\b", re.I),
    re.compile(r"\bdiscount\b", re.I),
    re.compile(r"—"),
]


def test_normalize_tone_canonical_legacy_and_ignored() -> None:
    for key in ("warm_story", "expert_clear", "polished_premium", "direct_offer"):
        assert normalize_tone(key) == key
        assert normalize_tone(f"  {key.upper()}  ") == key

    assert normalize_tone("collector_gallery") == "polished_premium"
    assert normalize_tone("direct_gift") == "direct_offer"
    assert normalize_tone("COLLECTOR_GALLERY") == "polished_premium"

    # Voice-profile tones and unknown values must be ignored.
    for ignored in ("casual", "formal", "neutral", "", "   ", "unknown_tone", None):
        assert normalize_tone(ignored) is None


def test_content_plan_request_ignores_unknown_tone_without_422() -> None:
    req = ContentPlanRequest(
        product=PlanProduct(title="Advisory Audit"),
        channels=["instagram"],
        business_type="services",
        tone="casual",
    )
    assert req.tone == "casual"
    plan = starter_plan(req)
    baseline = starter_plan(
        ContentPlanRequest(
            product=PlanProduct(title="Advisory Audit"),
            channels=["instagram"],
            business_type="services",
            tone=None,
        )
    )
    assert plan == baseline


@pytest.mark.parametrize("business_type", ["products", "services", "both"])
def test_starter_plan_differs_by_tone_and_follows_wording_rules(business_type: str) -> None:
    hooks_by_tone: dict[str, tuple[str, ...]] = {}
    ctas_by_tone: dict[str, str] = {}

    for tone in ("warm_story", "expert_clear", "polished_premium", "direct_offer"):
        req = ContentPlanRequest(
            product=PlanProduct(
                title="30-Day Growth Audit",
                description="A practical review of your channels and next steps.",
                destination_url="https://northstar.test/audit",
                seller="North Star Advisory",
            ),
            channels=["instagram", "facebook", "x"],
            goal="visits",
            business_type=business_type,
            tone=tone,
        )
        plan = starter_plan(req)
        hooks_by_tone[tone] = tuple(post.hook for post in plan.posts)
        ctas_by_tone[tone] = plan.posts[0].cta

        for post in plan.posts:
            combined = f"{post.hook} {post.caption} {post.cta}"
            for pattern in BANNED_PATTERNS:
                assert not pattern.search(combined), (
                    f"{business_type}/{tone} matched {pattern.pattern}: {combined}"
                )

    # Every tone produces distinct hooks and distinct CTAs.
    assert len(set(hooks_by_tone.values())) == 4
    assert len(set(ctas_by_tone.values())) == 4


def test_starter_plan_x_length_stays_under_230_for_all_tones() -> None:
    long_title = "Handcrafted Stoneware Pour-Over Coffee Set With Brass Stand And Matching Carafe"
    for btype in ("products", "services", "both"):
        for tone in ("warm_story", "expert_clear", "polished_premium", "direct_offer"):
            req = ContentPlanRequest(
                product=PlanProduct(
                    title=long_title,
                    destination_url="https://example.test/item",
                ),
                channels=["x"],
                goal="visits",
                business_type=btype,
                tone=tone,
            )
            plan = starter_plan(req)
            for post in plan.posts:
                assert len(f"{post.hook}\n{post.caption}\n{post.cta}") <= 230


def test_sample_business_type_none_ignores_tone_byte_for_byte() -> None:
    base = starter_plan(
        ContentPlanRequest(
            product=PlanProduct(
                title="Ek Onkar",
                description="Hand-painted Sikh calligraphy print.",
                destination_url="https://www.artofsarabjitsingh.com/ekonkar.html",
            ),
            channels=["instagram", "facebook"],
            goal="visits",
            business_type=None,
            tone=None,
        )
    )
    for tone in (
        "warm_story",
        "expert_clear",
        "polished_premium",
        "direct_offer",
        "collector_gallery",
        "direct_gift",
    ):
        with_tone = starter_plan(
            ContentPlanRequest(
                product=PlanProduct(
                    title="Ek Onkar",
                    description="Hand-painted Sikh calligraphy print.",
                    destination_url="https://www.artofsarabjitsingh.com/ekonkar.html",
                ),
                channels=["instagram", "facebook"],
                goal="visits",
                business_type=None,
                tone=tone,
            )
        )
        assert with_tone.model_dump_json() == base.model_dump_json()


@pytest.mark.asyncio
async def test_muse_prompt_includes_tone_for_own_and_omits_for_sample() -> None:
    captured: list[list[dict[str, Any]]] = []

    class FakeClient:
        async def chat_structured(self, *, messages, response_model, max_output_tokens):
            captured.append(messages)
            return ContentPlanDraft(
                recommended_channel="instagram",
                recommended_format="image",
                reason="Test plan.",
                posts=[
                    ContentPost(
                        day_offset=offset,
                        channel="instagram",
                        format="image",
                        hook=f"Hook {offset}",
                        caption="Short caption.",
                        cta="Learn more.",
                        visual_direction="Clear photo.",
                        posting_tip="Post once.",
                    )
                    for offset in (0, 2, 4)
                ],
            )

    svc = ContentPlanService(client=FakeClient())  # type: ignore[arg-type]

    await svc.generate(
        ContentPlanRequest(
            product=PlanProduct(title="Growth Audit"),
            channels=["instagram"],
            business_type="services",
            tone="expert_clear",
            use_muse=True,
        )
    )
    own_msg = captured[-1][1]["content"]
    assert tone_prompt_line("expert_clear") in own_msg

    # Sample shop (business_type=None) must never receive a tone directive.
    await svc.generate(
        ContentPlanRequest(
            product=PlanProduct(title="Ek Onkar"),
            channels=["instagram"],
            business_type=None,
            tone="expert_clear",
            use_muse=True,
        )
    )
    sample_msg = captured[-1][1]["content"]
    assert "brand_tone" not in sample_msg


def test_creator_js_and_welcome_html_brand_tone_parity() -> None:
    """creator.js labels/guides and welcome.html options must match brand_tone.py."""
    creator_js = (REPO_ROOT / "src/api/static/creator.js").read_text(encoding="utf-8")
    m = re.search(r"const BRAND_TONES = \{([\s\S]*?)\n  \};", creator_js)
    assert m, "BRAND_TONES object not found in creator.js"
    js_tones: dict[str, tuple[str, str]] = {}
    for entry in re.finditer(
        r"(\w+):\s*\{\s*label:\s*'([^']+)',\s*guide:\s*'([^']+)'\s*\}",
        m.group(1),
    ):
        js_tones[entry.group(1)] = (entry.group(2), entry.group(3))

    py_tones = {k: (v.label, v.guide) for k, v in BRAND_TONES.items()}
    assert js_tones == py_tones

    m_legacy = re.search(r"const LEGACY_TONE_MAP = \{([^}]+)\};", creator_js)
    assert m_legacy, "LEGACY_TONE_MAP not found in creator.js"
    js_legacy = dict(re.findall(r"(\w+):\s*'([^']+)'", m_legacy.group(1)))
    assert js_legacy == LEGACY_TONE_MAP

    welcome_html = (REPO_ROOT / "src/api/static/welcome.html").read_text(encoding="utf-8")
    for key, tone in BRAND_TONES.items():
        escaped_label = tone.label.replace("&", "&amp;")
        assert f'value="{key}"' in welcome_html
        assert escaped_label in welcome_html
    assert "Shapes the wording of your starter posts and drafts." in welcome_html
    assert json.dumps(list(BRAND_TONES))  # sanity check serializable
