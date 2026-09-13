"""The thing under test: a support-ticket classifier.

PROMPT is the only line PromptLock cares about. Edit it and run
`promptlock check` to see which cases move.
"""

PROMPT = """You are a support triage assistant.

Classify the ticket below.

<ticket>
{ticket}
</ticket>

Return category (one of: billing, bug, feature_request, account, other),
urgency (one of: low, medium, high), and a one-line summary.

Respond with ONLY valid JSON. No prose, no markdown fence.
"""


def render(case_input: dict) -> str:
    return PROMPT.format(ticket=case_input["ticket"])
