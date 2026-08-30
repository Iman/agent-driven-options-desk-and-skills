"""Prompt assembly, and whether the reporting rules survive it.

The rules are compiled into the prompt precisely so a caller cannot forget
them. A prompt that drops them still renders, still answers, and answers
without the constraints the rest of the package exists to enforce, so that
is the failure these tests are aimed at.
"""

import pytest

from optiondesk_agent.prompts import (
    REPORTING_RULES,
    build_answer_prompt,
    build_router_prompt,
)
from optiondesk_agent.tools import SPECS


def system_text(prompt, **values):
    """The rendered system message, which is what the model actually reads."""
    values.setdefault("context", "an artifact summary")
    values.setdefault("question", "what is the gamma flip")
    return prompt.format_messages(**values)[0].content


# --------------------------------------------------------------------------
# The rules reach the model.
# --------------------------------------------------------------------------

def test_the_reporting_rules_are_embedded_verbatim_in_the_prompt():
    """Catches the rules being summarised, truncated, or dropped entirely.

    This is the failure that matters: the prompt still renders and still
    answers, so nothing looks broken while every constraint is gone. The
    whole block is asserted, not a phrase from it, because a paraphrase
    passes a keyword check and still loses the rules.
    """
    assert REPORTING_RULES in system_text(build_answer_prompt())


def test_the_rules_survive_rendering_with_context_and_question():
    """Catches the rules being lost at format time rather than build time.

    A template can hold the text and still drop it when rendered, for
    instance if the block were treated as a variable rather than a literal.
    """
    text = system_text(build_answer_prompt(),
                       context="chain for SPY, generated 2026-08-30",
                       question="is the sampler converged")

    assert REPORTING_RULES in text


@pytest.mark.parametrize("rule", [
    "If an artifact is marked degraded, say so and give the reason "
    "before any\n   number from it.",
    "never substitute a\n   volatility to complete a picture",
    "They\n   are not fills.",
    'Report it as that\n   word, never as a number.',
    "Quote\n   the assumption whenever you quote a wall or a flip level.",
    "do not quote its quantiles",
    "Never recommend a trade, an entry, an exit or a size.",
])
def test_each_individual_rule_reaches_the_model(rule):
    """Catches one rule being edited out while the block still looks whole.

    Losing rule 8 alone turns the desk into an advice service; losing rule
    1 alone lets degraded numbers be quoted clean. Each is load bearing on
    its own, so each is asserted on its own.
    """
    assert rule in system_text(build_answer_prompt())


def test_the_units_paragraph_reaches_the_model():
    """Catches the units guidance being dropped as boilerplate.

    Vega is per 1.00 of volatility. Quoted without that, a vega of 3.0 is
    read as three dollars a point when it is three cents.
    """
    text = system_text(build_answer_prompt())

    assert "Volatility is per 1.00" in text
    assert "Vega is\nper 1.00 of volatility" in text


def test_the_question_and_context_both_reach_the_human_message():
    """Catches a placeholder renamed so the artifacts never arrive.

    An answer prompt whose context slot is empty is a model answering from
    memory, which is the one thing this package is built to prevent.
    """
    messages = build_answer_prompt().format_messages(
        context="chain for SPY, generated 2026-08-30",
        question="where is the put wall")
    human = messages[-1].content

    assert "chain for SPY, generated 2026-08-30" in human
    assert "where is the put wall" in human


def test_the_prompt_declares_the_two_variables_it_needs():
    """Catches a silently unfilled slot at call time.

    A template that no longer declares context will render without it and
    raise nothing, leaving the model ungrounded.
    """
    assert set(build_answer_prompt().input_variables) == {"context",
                                                          "question"}


# --------------------------------------------------------------------------
# Extra rules add to the block, they do not replace it.
# --------------------------------------------------------------------------

def test_extra_rules_are_appended_and_the_base_rules_kept():
    """Catches a deployment override wiping the rules it meant to extend.

    The parameter is named extra_rules. A caller adding one house rule must
    not silently lose the eight that ship with the package.
    """
    text = system_text(build_answer_prompt(
        extra_rules="Never name a counterparty."))

    assert REPORTING_RULES in text
    assert "Never name a counterparty." in text
    assert "Additional rules for this deployment:" in text


def test_extra_rules_come_after_the_base_rules():
    """Catches an override being buried above the rules it qualifies.

    Later text qualifies earlier text in a system message, so a deployment
    rule placed first reads as the one being overridden.
    """
    text = system_text(build_answer_prompt(extra_rules="House rule."))

    assert text.index("House rule.") > text.index("Never recommend a trade")


def test_omitting_extra_rules_adds_no_empty_section():
    """Catches a dangling heading with nothing under it.

    An empty "Additional rules" heading reads as rules that failed to load,
    which is worse than no heading at all.
    """
    assert "Additional rules" not in system_text(build_answer_prompt())


def test_building_the_prompt_does_not_mutate_the_shared_rules():
    """Catches extra_rules being concatenated onto the module constant.

    In-place growth would make every later prompt in the process carry one
    deployment's private rules, and the leak would follow process lifetime
    rather than anything visible in the call.
    """
    before = REPORTING_RULES
    build_answer_prompt(extra_rules="House rule.")

    from optiondesk_agent import prompts

    assert prompts.REPORTING_RULES == before
    assert "House rule." not in prompts.REPORTING_RULES


# --------------------------------------------------------------------------
# The router prompt.
# --------------------------------------------------------------------------

def test_the_router_prompt_names_every_tool_in_the_spec_table():
    """Catches a capability added to SPECS and never advertised.

    A tool the router has never heard of is a tool the router cannot pick,
    so the capability ships and is unreachable.
    """
    text = system_text(build_router_prompt())
    missing = [spec["name"] for spec in SPECS if spec["name"] not in text]

    assert missing == []


def test_the_router_refuses_to_be_an_advice_router():
    """Catches the one refusal in the router prompt being dropped.

    Without it the router answers "what should I do" by picking the tool
    that sounds closest, which dresses a recommendation as an analysis.
    """
    text = system_text(build_router_prompt())

    assert "Nothing here answers a question about what someone should do." \
        in text


def test_the_router_prompt_takes_only_the_question():
    """Catches the router quietly gaining a slot no caller fills."""
    assert build_router_prompt().input_variables == ["question"]
