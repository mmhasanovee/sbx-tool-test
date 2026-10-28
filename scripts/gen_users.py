"""Writes data/users.csv: Chatter Free users and API-only integration users for the SBX test org.

Run from the project root:  python -I scripts/gen_users.py <chatter_free_profile_id> <integration_profile_id>
"""
import csv
import os
import random
import sys

CHATTER_USERS = 50
INTEGRATION_USERS = 2
DOMAIN = "hscodehub-sbxtest.example.com"
FIRST = ["Aisha", "Omar", "Lina", "Yousef", "Sara", "Karim", "Noor", "Hadi", "Maya", "Tariq", "Rania", "Ali", "Dana", "Fahad", "Huda"]
LAST = ["Haddad", "Rahman", "Saleh", "Nasser", "Khalil", "Farouk", "Aziz", "Mansour", "Qasim", "Darwish", "Hamdan", "Jaber"]


def main(chatter_profile, integration_profile):
    rng = random.Random(42)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "users.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    rows = []
    for i in range(1, CHATTER_USERS + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        rows.append([f"sbx.chatter{i:02d}@{DOMAIN}", first, last, f"sbx.chatter{i:02d}@example.com", f"sbxc{i:02d}", chatter_profile])
    for i in range(1, INTEGRATION_USERS + 1):
        rows.append([f"sbx.integration{i:02d}@{DOMAIN}", "Integration", f"User {i:02d}", f"sbx.integration{i:02d}@example.com",
                     f"sbxint{i:02d}", integration_profile])
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Username", "FirstName", "LastName", "Email", "Alias", "ProfileId",
                    "TimeZoneSidKey", "LocaleSidKey", "EmailEncodingKey", "LanguageLocaleKey"])
        for r in rows:
            w.writerow(r + ["Asia/Kuwait", "en_US", "UTF-8", "en_US"])
    print(f"{len(rows)} users written to {os.path.normpath(out)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
