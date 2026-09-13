"""Fixture: prompt templates with no call site in this file.

Covers both qualifying rules: a name that matches /PROMPT|TEMPLATE|SYSTEM/i,
and a long format string whose name matches nothing.
"""

RERANK_TEMPLATE = """Given the query and the {n} candidate documents below,
return the indices of the {k} most relevant, most relevant first.

Query: {query}
Documents:
{documents}
"""

# Name matches nothing, but it is long and carries {placeholders}.
GUIDANCE = (
    "When the ticket mentions {product}, route it to the {team} queue and set "
    "urgency to {urgency}. Otherwise fall back to the triage defaults and let "
    "the on-call engineer decide during the next sweep of the {queue} backlog."
)

# Neither rule applies to these.
LABEL = "billing"
MAX_DOCS = 20
