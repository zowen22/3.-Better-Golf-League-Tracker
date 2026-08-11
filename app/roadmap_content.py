"""Public Roadmap page content: plain data, no Flask dependency.

ROADMAP_LANES is a plain list of {'slug', 'label', 'items'} dicts, ordered
most-active-first (In Progress, then Planned / Under Consideration, then
Recently Shipped last as a trust signal, not the headline). Each item is
{'title', 'body'}: one or two plain-English sentences, written for a
league admin or player, not a developer. No internal file/route names,
credentials, infra details, or engineering jargon belong here; that's
what Work Packages / Technical Reference are for.

This is a curated, hand-maintained list (same pattern as setting_help.py
and howto_help.py), not sourced automatically from Work Packages: most
WP entries are written for Claude/@user, not for end users, and mix in
things (sandbox quirks, migration file names, admin-only edge cases) that
have no business on a public page. Update this file by hand when the
backlog changes enough to be worth telling users about.

Voice: first-person as @user (the person who built BGLT), same
convention as setting_help.py/howto_help.py.
"""

ROADMAP_LANES = [
    {
        'slug': 'in-progress',
        'label': 'In Progress',
        'items': [
            {
                'title': 'How-To Guides',
                'body': (
                    "The Site Wiki has always explained what each setting does. It's getting a "
                    "second section of plain how-to guides for actually running a league week to "
                    "week (logins & admin access, importing a roster, season setup, and more). The "
                    "first section is live now; the rest are being written the same way."
                ),
            },
            {
                'title': 'iOS App',
                'body': (
                    "A companion iOS app is built and in testing (TestFlight), not yet available "
                    "to the public. It mirrors the web app's scoring and push notifications for "
                    "score updates and announcements."
                ),
            },
        ],
    },
    {
        'slug': 'planned',
        'label': 'Planned / Under Consideration',
        'items': [
            {
                'title': 'One Account, Multiple Leagues',
                'body': (
                    "Right now an individual account is tied to one league. If you help run (or "
                    "play in) more than one league, you need a separate account for each today. "
                    "Letting one account hold roles across several leagues is on the list."
                ),
            },
            {
                'title': 'League Self-Signup',
                'body': (
                    "Starting a brand-new league currently goes through me directly. A self-serve "
                    "signup flow (pick a plan, create your league, invite your admins) would let "
                    "a new league get going without waiting on a manual setup."
                ),
            },
            {
                'title': 'In-App Support Inbox',
                'body': (
                    "A way to report a bug or ask a question straight from the app, instead of "
                    "email, with a real place for it to land and get tracked."
                ),
            },
            {
                'title': 'Teams Larger Than Two Players',
                'body': (
                    "Team formats are currently built around two-player teams. Support for "
                    "larger teams (e.g. scramble-format leagues) isn't scheduled yet, but it's a "
                    "known gap I'd take on if a league needs it."
                ),
            },
        ],
    },
    {
        'slug': 'shipped',
        'label': 'Recently Shipped',
        'items': [
            {
                'title': 'Manual Points Override',
                'body': (
                    "Admins can now correct a match's points directly, with a required reason and "
                    "a full history of every change, for the rare case a result needs a manual fix."
                ),
            },
            {
                'title': 'Faster Roster & Score Imports',
                'body': (
                    "Bringing a league in from a spreadsheet now supports .xlsx files directly, "
                    "plus a column-mapping step so nothing has to be reformatted by hand first."
                ),
            },
            {
                'title': 'In-App Site Wiki',
                'body': (
                    "Every League Setting now has a plain-language explanation, all in one "
                    "searchable page. It's the same text shown in each setting's own tooltip."
                ),
            },
        ],
    },
]
