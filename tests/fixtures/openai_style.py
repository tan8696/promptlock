"""Fixture: an OpenAI-style call site. Never imported or executed."""

from openai import OpenAI

SUMMARY_PROMPT = """Summarise the support ticket below in exactly one line.

<ticket>
{ticket}
</ticket>
"""


def summarise(ticket: str) -> str:
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": SUMMARY_PROMPT.format(ticket=ticket)}],
    )
    return resp.choices[0].message.content
