"""Fixture: an Anthropic-style call site. Never imported or executed."""

import anthropic

SYSTEM_PROMPT = "You are a support triage assistant. Reply with valid JSON only."


def classify(ticket: str) -> str:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": ticket}],
    )
    return msg.content[0].text
