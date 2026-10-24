#!/usr/bin/env python3
"""Regenerate the synthetic mailbox fixture (mailbox.json). All data is fictional.

    python3 generate.py

"Now" for the fixture is 2026-10-25T12:00:00Z.
"""
import json
import os
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
GOOD_AUTH = "mx.example; spf=pass smtp.mailfrom=x; dkim=pass header.d=x; dmarc=pass header.from=x"
BAD_AUTH = "mx.example; spf=fail smtp.mailfrom=x; dkim=fail header.d=x; dmarc=fail header.from=x"

messages = []


def add(sender, subject, count, read_pattern, auth=GOOD_AUTH, step=6, **extra):
    """read_pattern: string of 'R'/'U' cycled across messages (R=read)."""
    for i in range(count):
        headers = {"From": sender, "Subject": f"{subject} #{i + 1}", "Authentication-Results": auth,
                   "Date": (NOW - timedelta(days=2 + i * step)).strftime("%a, %d %b %Y %H:%M:%S +0000")}
        headers.update(extra)
        messages.append({"headers": headers, "read": read_pattern[i % len(read_pattern)] == "R"})


ONECLICK = {"List-Unsubscribe": "<https://mail.shopping.example/u/8f3a9c1d2b7e4f60>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}

# 1. Promotional, never opened, verified one-click -> unsubscribe
add("Shopping Site <deals@shopping.example>", "Weekend sale", 12, "U", **ONECLICK)
# 2. Airline deals, often opened -> keep
add("Airline Deals <fares@airline.example>", "Fare alert", 8, "RRRU",
    **{"List-Unsubscribe": "<https://mail.airline.example/u/aa11bb22cc33dd44>",
       "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
# 3. Unknown offers: failed auth, plain http unsubscribe link -> block/report, never visit
add("Unknown Offers <win@unknown-offers.example>", "You won a prize", 10, "U", auth=BAD_AUTH,
    **{"List-Unsubscribe": "<http://track.unknown-offers.example/out?id=991823>"})
# 4. Local club mailing list, mailto only, often opened -> keep
add("Local Club <list@localclub.example>", "Club news", 4, "RRU", step=20,
    **{"List-Id": "<club.localclub.example>",
       "List-Unsubscribe": "<mailto:list-leave@localclub.example?subject=unsubscribe>"})
# 5. Receipts with promotional language -> excluded
add("Shopping Site <receipts@store.example>", "Your receipt and 20% off your next order", 5, "U",
    **{"List-Unsubscribe": "<https://mail.store.example/u/1234567890abcdef>",
       "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
# 6. Security alerts -> excluded
add("Example Bank <alerts@bank.example>", "Security alert: new sign-in", 5, "U",
    **{"List-Unsubscribe": "<mailto:stop@bank.example>"})
# 7. Spoofed display name from a mismatched domain, failing auth -> block/report
add("PayPal support paypal.com <help@random-mail.example>", "Verify your account", 6, "U",
    auth=BAD_AUTH, **{"List-Unsubscribe": "<https://random-mail.example/u/0a1b2c3d4e5f6a7b>"})
# 8. One publisher, two addresses (same registrable domain)
add("Daily Pub <news@pub.example>", "Daily digest", 9, "UUR",
    **{"List-Unsubscribe": "<https://mail.pub.example/u/f00dfeed12345678>",
       "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
add("Daily Pub Offers <offers@mail.pub.example>", "Subscriber offer", 6, "U",
    **{"List-Unsubscribe": "<https://mail.pub.example/u/beefcafe87654321>",
       "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
# 9. Preference page only (no one-click header)
add("Gadget Hub <promo@gadgets.example>", "New gadgets", 7, "U",
    **{"List-Unsubscribe": "<https://gadgets.example/preferences?user=42>"})
# 10. Bulk mail with no unsubscribe method -> mailbox rule
add("Blast Co <blast@nounsub.example>", "Big news", 8, "U", **{"Precedence": "bulk"})
# 11. Unsupported scheme / javascript link -> unsafe
add("Odd Sender <hello@oddsender.example>", "Hello friend", 5, "U", auth=BAD_AUTH,
    **{"List-Unsubscribe": "<javascript:alert(1)>"})
# 12. Old messages outside the 90-day window only
messages.append({"headers": {"From": "Ancient <old@ancient.example>", "Subject": "Old",
                             "Date": "Mon, 01 Jan 2024 10:00:00 +0000", "Precedence": "bulk",
                             "Authentication-Results": GOOD_AUTH}, "read": False})

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mailbox.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"now": NOW.isoformat(), "messages": messages}, fh, indent=1)
print(f"wrote {len(messages)} messages to {out}")
