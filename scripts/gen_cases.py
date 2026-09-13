"""Emit examples/demo_app/cases.yaml — 50 tickets, deliberately including
ambiguous ones so the suite has a realistic noise profile."""

import yaml

T = [
    ("billing", "I was charged twice for my invoice this month, please refund the duplicate payment."),
    ("billing", "My card was declined but the subscription still shows active. What happened?"),
    ("billing", "Can you explain the price increase on my last invoice?"),
    ("billing", "I need a refund for the annual payment, I cancelled two days after renewal."),
    ("billing", "The invoice PDF shows the wrong billing address."),
    ("billing", "Why was I billed in USD when my account currency is EUR?"),
    ("billing", "Please send me all invoices for the last financial year."),
    ("billing", "I upgraded mid-cycle and the charge looks wrong."),
    ("billing", "Subscription renewed even though I cancelled. Need this refunded ASAP."),
    ("billing", "Do you support payment by bank transfer instead of card?"),
    ("bug", "The export button crashes the whole page with a 500 error every time."),
    ("bug", "Uploading a CSV over 10MB fails silently, nothing happens."),
    ("bug", "Dark mode is broken on Safari, the text is invisible."),
    ("bug", "App freezes when I open the settings panel on mobile."),
    ("bug", "I get an exception trace whenever I try to share a report."),
    ("bug", "Search returns no results even for documents I can see in the list."),
    ("bug", "The webhook fires twice for every event, causing duplicate records."),
    ("bug", "Timestamps display in the wrong timezone after the last update."),
    ("bug", "Everything is down, the dashboard will not load at all. Urgent."),
    ("bug", "Pagination skips the last row on every page."),
    ("feature_request", "Would be nice if you could add bulk delete for archived items."),
    ("feature_request", "Please add support for SSO with Okta."),
    ("feature_request", "Any chance of a dark mode for the mobile app?"),
    ("feature_request", "I wish there was a way to schedule reports weekly."),
    ("feature_request", "Suggestion: let us tag teammates in comments."),
    ("feature_request", "Can you add a Slack integration for notifications?"),
    ("feature_request", "It would help a lot to have keyboard shortcuts for navigation."),
    ("feature_request", "Please add an API endpoint for listing workspaces."),
    ("account", "I am locked out after too many login attempts, please reset."),
    ("account", "How do I change the email address on my account?"),
    ("account", "I lost my 2fa device and cannot sign in."),
    ("account", "Please delete my account and all associated data."),
    ("account", "My password reset email never arrives."),
    ("account", "I need to transfer ownership of the workspace to a colleague."),
    ("account", "Can I merge two accounts that use different emails?"),
    ("account", "Login redirects me in a loop and never completes."),
    ("other", "Just wanted to say the new release is great, thanks team."),
    ("other", "Do you have a status page I can subscribe to?"),
    ("other", "Where can I find your data processing agreement?"),
    ("other", "Are you hiring for backend roles right now?"),
    ("other", "What is your uptime guarantee on the business plan?"),
    ("other", "Is there a student discount available?"),
    # Genuinely ambiguous — these are the cases that make the suite noisy.
    ("billing", "The payment page throws an error when I try to update my card."),
    ("bug", "I was charged but the app crashed before confirming, did it go through?"),
    ("account", "Login is broken after I changed my email address."),
    ("feature_request", "The export is so slow it is basically unusable, can you make it faster?"),
    ("bug", "My invoice download link returns a 500."),
    ("account", "Cannot sign in and I am being billed for a seat I cannot use."),
    ("feature_request", "There is no way to cancel a subscription in the UI, please add one."),
    ("other", "Following up on my previous ticket, any update?"),
]

# Reference urgency labels. Stands in for the human labelling you would do
# once, by hand, when building a real suite.
HOT = ["asap", "urgent", "immediately", "locked out", "cannot", "can not",
       "everything is down", "will not load", "basically unusable"]
MED = ["crash", "500", "error", "broken", "fails", "refund", "declined", "loop"]


def urgency_for(text: str) -> str:
    low = text.lower()
    if any(w in low for w in HOT):
        return "high"
    if any(w in low for w in MED):
        return "medium"
    return "low"


cases = [
    {
        "id": f"t{i:03d}",
        "input": {"ticket": text},
        "expect": {"category": cat, "urgency": urgency_for(text)},
    }
    for i, (cat, text) in enumerate(T, 1)
]

with open("examples/demo_app/cases.yaml", "w") as f:
    yaml.safe_dump({"cases": cases}, f, sort_keys=False, width=100)

print(f"wrote {len(cases)} cases")
