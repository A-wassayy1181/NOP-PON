"""Membership and donation guidance tool."""

from langchain_core.tools import tool


# NOP website URLs
NOP_URLS = {
    "join": "https://northernontarioparty.org/join-the-party/",
    "donate": "https://northernontarioparty.org/donate-today/",
    "contact": "https://northernontarioparty.org/contact/",
    "home": "https://northernontarioparty.org/",
    "about": "https://northernontarioparty.org/about/",
}


@tool
def membership_tool(intent: str) -> str:
    """Provide guidance for membership, donation, and contact inquiries.

    Use this tool when the user wants to:
    - Join the Northern Ontario Party
    - Become a member
    - Donate to the party
    - Make a contribution
    - Contact the party directly
    - Get involved with the party

    Args:
        intent: The user's intent - one of: 'join', 'donate', 'contact', 'involvement'

    Returns:
        Guidance with relevant URLs and information
    """
    intent = intent.lower().strip()

    if intent in ["join", "membership", "member", "sign up", "register"]:
        return f"""To join the Northern Ontario Party:

1. Visit the membership page: {NOP_URLS['join']}

Membership Details:
- Current membership price: $20.00 (discounted from $30.00)
- Membership duration: 1-3 years
- You can join through the website's online system or contact the party directly

Benefits of membership:
- Support Northern Ontario's regional representation
- Participate in party activities and events
- Have a voice in party decisions
- Connect with like-minded Northerners

If you have questions about membership, you can also contact the party directly at: {NOP_URLS['contact']}"""

    elif intent in ["donate", "donation", "contribute", "contribution", "support", "fund"]:
        return f"""To donate to the Northern Ontario Party:

1. Visit the donation page: {NOP_URLS['donate']}

Donation Information:
- Online donations are processed securely through the website
- Current suggested donation: $20.00
- Your contribution supports the party's advocacy for Northern Ontario

Political donations in Ontario may be eligible for tax credits. Consult the Elections Ontario website for current rules on political contributions.

For questions about donations, contact the party at: {NOP_URLS['contact']}"""

    elif intent in ["contact", "reach out", "speak", "talk", "call", "email"]:
        return f"""To contact the Northern Ontario Party:

Visit the contact page: {NOP_URLS['contact']}

The party is based in Thunder Bay, Ontario and serves all of Northern Ontario.

You can also reach out regarding:
- Membership inquiries
- Donation questions
- Volunteer opportunities
- General questions about the party
- Media inquiries

Email: Northernontarioparty@hotmail.com"""

    elif intent in ["involvement", "volunteer", "get involved", "participate", "help"]:
        return f"""To get involved with the Northern Ontario Party:

There are several ways to participate:

1. **Become a Member**: {NOP_URLS['join']}
   Join the party to have a voice in decisions and participate in activities.

2. **Donate**: {NOP_URLS['donate']}
   Financial contributions support the party's campaigns and advocacy work.

3. **Volunteer**: {NOP_URLS['contact']}
   Contact the party to learn about volunteer opportunities in your area.

4. **Stay Informed**: {NOP_URLS['home']}
   Visit the website regularly for news, events, and updates.

The party has representatives throughout Northern Ontario's 14 electoral ridings, so there may be local activities in your area."""

    else:
        return f"""For information about the Northern Ontario Party:

- Join the Party: {NOP_URLS['join']}
- Make a Donation: {NOP_URLS['donate']}
- Contact Us: {NOP_URLS['contact']}
- Learn More: {NOP_URLS['about']}

Please let me know specifically if you'd like to join, donate, or contact the party, and I can provide more detailed guidance."""
