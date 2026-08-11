"""Site Wiki "How To" section: workflow-level help content, separate track
from setting_help.SETTING_HELP.

HOWTO_CATEGORIES is a plain data list (no Flask/route dependencies), one
entry per top-level dropdown section. Category names and grouping now
mirror GLT's own how-to page (https://www.golfleaguetracker.com/glthome/help/how-to/)
directly, per @user's request (2026-08-11) -- this is a structural/naming
match only, not a reversal of the content-model decision below. "League
Setup" is kept first (per @user), ahead of GLT's own page order, since
it's the most-used section for a new admin.

Two category shapes, both valid as top-level entries:
- Flat: {'slug', 'icon', 'name', 'articles': [...]} -- renders as one
  dropdown containing articles directly, same as before.
- Parent-with-subcategories (currently only "League Setup", matching
  GLT's own "League Setup - X" naming convention there): {'slug', 'icon',
  'name', 'subcategories': [{'slug', 'name', 'articles': [...]}, ...]} --
  renders as a dropdown containing nested sub-dropdowns.

An `articles` list (flat or within a subcategory) holds {'slug', 'title',
'body' (list of paragraph strings, may contain inline HTML, rendered with
|safe, same convention as the hand-written "Default Tees" section in
wiki/index.html), optional 'steps' (list of strings, rendered as an
ordered list)}.

Content model (per Work Packages backlog decision, 2026-08-11): original
BGLT-specific how-tos, written fresh from BGLT's actual screens/routes.
GLT's how-to articles/categories are used as a structural and topic
checklist during research (see the Feature Parity doc) -- category names
and grouping are deliberately matched to GLT's own page where a real BGLT
equivalent exists; article prose itself is never summarized or adapted
from GLT's copy.

Hard boundary: this module documents workflows, not individual League
Settings. Never fork or duplicate SETTING_HELP copy into an entry here.
Link to the relevant setting's wiki anchor (`/wiki#setting-N.NN`) instead
if it's genuinely relevant.

Voice: first-person as @user (the person who built BGLT), matching
SETTING_HELP's convention. See setting_help.py's module docstring for
the full voice guidance.

Categories/subcategories with no content yet keep an empty `articles`
list and render the wiki's existing placeholder text, same convention
WIKI_CATEGORIES already uses in wiki.py for settings categories with
nothing mapped yet. A few GLT categories with no real BGLT equivalent
(Purchasing Golf League Tracker, Premium E-mail Add-on, System
Requirements, Tracking Only Player Handicaps, Setup is Incomplete, the
ads/payment-problems troubleshooting items) are deliberately omitted
rather than stubbed -- they're GLT monetization/business-model specific
or generic boilerplate, not a BGLT gap. "Transferring from Other
Systems" and "Entering Scores and Points" are also omitted as separate
categories since their real content already lives under "Importing
Players, Teams, Schedules & Scores" (League Setup -> The Players) and
under Points/Subs respectively -- BGLT's own content doesn't split along
that exact boundary, and forcing an artificial split wouldn't add
anything true.
"""

HOWTO_CATEGORIES = [
    {
        'slug': 'howto-league-setup',
        'icon': '🗂️',
        'name': 'League Setup',
        'subcategories': [
            {
                'slug': 'howto-league-setup-players',
                'name': 'The Players',
                'articles': [
                    {
                        'slug': 'adding-players-teams',
                        'title': 'Adding Players & Teams',
                        'body': [
                            (
                                "A roster starts with players, not teams. Add each one from "
                                "<strong>Players → Add Player</strong>, then pair two players into a team "
                                "from <strong>Teams → Add Team</strong> for whichever season they're playing "
                                "in. A team can also carry a nickname; if it's left blank, BGLT falls back to "
                                "showing both players' last names wherever a team label is needed."
                            ),
                            (
                                "A player who leaves the league doesn't need to be deleted. "
                                "<strong>Deactivate</strong> (on the player's profile) keeps their entire "
                                "scoring/handicap history intact while dropping them off the active roster "
                                "and out of the pool of players available to add to a new team. "
                                "<strong>Reactivate</strong> reverses it any time."
                            ),
                            (
                                "Team size is fixed at two players today; there's no path yet, not even a "
                                "manual workaround, to a three- or four-player team. If a league ever needs "
                                "that (a scramble format, for instance), that's a real gap to flag rather than "
                                "something to work around in the roster screens."
                            ),
                        ],
                    },
                    {
                        'slug': 'divisions',
                        'title': 'Divisions',
                        'body': [
                            (
                                "Divisions aren't a separate setup screen. They're a free-text "
                                "<strong>Division</strong> field right on each team (Add/Edit Team). Give two "
                                "teams the same division name and they're grouped; BGLT suggests names "
                                "you've already used so it's easy to stay consistent instead of a typo "
                                "quietly creating a third division by accident."
                            ),
                            (
                                "I deliberately kept divisions, playoffs, and skins flights as separate, "
                                "purpose-built features instead of one shared \"grouping\" mechanism "
                                "driving all three. A single overloaded setting is easy to configure once "
                                "and then forget is silently controlling several other things."
                            ),
                        ],
                    },
                    {
                        'slug': 'playoffs',
                        'title': 'Playoffs',
                        'body': [
                            (
                                "Two settings drive the playoff bracket: <strong>Playoff Teams</strong> "
                                "(defaults to 4) decides how many top-standings teams qualify, and "
                                "<strong>Finals Duration</strong> (defaults to 2 weeks) decides how many "
                                "weeks the bracket runs. See "
                                "<a href=\"/wiki#setting-4.01\">Playoff Teams</a> and "
                                "<a href=\"/wiki#setting-4.02\">Finals Duration</a>."
                            ),
                            (
                                "Generating the bracket pulls straight from the season's current standings "
                                "at that moment, seeding the top N teams, so it's worth generating it after "
                                "the regular season is actually finished, not mid-season as a preview, since "
                                "there's no separate re-seed step short of resetting and regenerating."
                            ),
                        ],
                    },
                    {
                        'slug': 'importing-data',
                        'title': 'Importing Players, Teams, Schedules & Scores',
                        'body': [
                            (
                                "Moving a league here from another system, or just starting from a spreadsheet "
                                "instead of hand-entering a roster, goes through "
                                "<a href=\"/admin/migrate/\">Admin → Import Players</a> (the same tool handles "
                                "all four data types, not just players). It walks through Players, Teams, "
                                "Schedule, and Scores one at a time, in that order. Each later type expects the "
                                "earlier ones to already exist, so importing schedule before players won't find "
                                "anyone to schedule."
                            ),
                            (
                                "Both .csv and .xlsx files work. Each of the four types has its own downloadable "
                                "template on the upload page (real column headers plus one filled-in example "
                                "row), worth starting from rather than guessing what BGLT expects."
                            ),
                            (
                                "After uploading, a column-mapping step shows up before anything is actually "
                                "written: headers get auto-matched to BGLT's fields where the names line up, but "
                                "any column can be remapped by hand, individual rows can be excluded, and a "
                                "whole column can be ignored, all before committing, so it's safe to upload "
                                "first and clean up the mapping second."
                            ),
                            (
                                "A league that already has its roster in BGLT doesn't need to start at Players. "
                                "Schedule or Scores can be imported on their own as long as the players/teams "
                                "they reference already exist."
                            ),
                        ],
                    },
                ],
            },
            {
                'slug': 'howto-league-setup-course',
                'name': 'The Course',
                'articles': [
                    {
                        'slug': 'adding-a-course',
                        'title': 'Adding a Course',
                        'body': [
                            (
                                "From <strong>Courses → Add Course</strong>, search the built-in Golf Course "
                                "database first. It pulls in the course, its tees, and full hole-by-hole "
                                "par/yardage/handicap data in one shot, which is far less typing than entering "
                                "it by hand. That search is rate-limited (a usage meter on the page turns red "
                                "as you approach the monthly cap), so it's worth searching precisely rather "
                                "than browsing broadly."
                            ),
                            (
                                "If a course isn't in that database, add it manually, then add each tee "
                                "color one at a time and fill in the per-hole par/handicap data for it: more "
                                "setup work, but nothing the automated search can do that manual entry can't "
                                "eventually match."
                            ),
                        ],
                    },
                    {
                        'slug': '27-hole-courses',
                        'title': '27-Hole & Multi-Combo Courses',
                        'body': [
                            (
                                "BGLT doesn't have a dedicated \"27-hole course\" flag. Instead, enter each "
                                "9-hole set as its own tee/hole configuration, then add one course entry per "
                                "18-hole combination your league actually plays (e.g. a facility with A/B/C "
                                "nines becomes three course entries: A/B, B/C, and A/C)."
                            ),
                            (
                                "It's an admin data-entry pattern, not a missing feature. BGLT's course "
                                "model already supports arbitrary tee/hole configurations including "
                                "independent 9-hole sets, so nothing needs to change to schedule any of the "
                                "combinations once they're entered."
                            ),
                        ],
                    },
                    {
                        'slug': 'assigning-tees',
                        'title': 'Assigning Tees',
                        'body': [
                            (
                                "Every course has its own default tee (set from the course's detail page), "
                                "and every player can have a personal default tee on top of that. See "
                                "<a href=\"/wiki#default-tees\">Default Tees &amp; Tee Selection Order</a> for "
                                "how the two combine and where a one-week print-scorecards change fits in."
                            ),
                            (
                                "There's no course-by-course bulk grid or an assign-by-tee-name-across-courses "
                                "shortcut today. The Default Tees mass-edit page covers setting everyone's "
                                "tee for one course at a time, which is fine for a league that plays mostly one "
                                "home course, more repetitive for one that rotates across several."
                            ),
                        ],
                    },
                ],
            },
            {
                'slug': 'howto-league-setup-tee-times',
                'name': 'Tee Times',
                'articles': [],
            },
            {
                'slug': 'howto-league-setup-schedule',
                'name': 'The Schedule',
                'articles': [
                    {
                        'slug': 'creating-editing-a-schedule',
                        'title': 'Creating & Editing a Schedule',
                        'body': [
                            (
                                "<strong>Schedule → Generate</strong> builds a full round-robin from that "
                                "season's teams in one pass. After it exists, individual weeks can still be "
                                "added, removed, or bulk-edited, and any single matchup can be corrected "
                                "on its own. Generating isn't a one-shot, all-or-nothing action."
                            ),
                            (
                                "Regenerating from scratch clears the existing schedule first, so it's meant "
                                "for before a season starts, not as a way to patch one wrong matchup: use "
                                "the single-matchup edit or bulk-edit tools for that instead."
                            ),
                        ],
                    },
                    {
                        'slug': 'rain-outs',
                        'title': 'Rain-Outs',
                        'body': [
                            (
                                "A rained-out week gets flagged, then optionally rescheduled. That's two "
                                "separate steps, not one combined action:"
                            ),
                        ],
                        'steps': [
                            (
                                "<strong>Mark it.</strong> From that week's schedule row, mark it as a rain "
                                "out. This is blocked once any matchup that week already has a completed "
                                "score, so it can't be used to quietly undo real results."
                            ),
                            (
                                "<strong>Reschedule it (optional).</strong> From Rain-Outs, either move it "
                                "onto an existing week or insert a brand-new week at any date you pick. "
                                "Matchups carry over unchanged either way, only the date moves."
                            ),
                            (
                                "<strong>Or leave it unrescheduled</strong> if the season's just shrinking by "
                                "one round instead of replaying it."
                            ),
                        ],
                    },
                    {
                        'slug': 'season-segments',
                        'title': 'Season Segments',
                        'body': [
                            (
                                "<strong>Segment Start Week</strong> and <strong>Segment End Week</strong> "
                                "(<a href=\"/wiki#setting-7.01\">7.01</a> / "
                                "<a href=\"/wiki#setting-7.02\">7.02</a>) carve out a stretch of the season "
                                "(a \"first half\" or \"second half,\" for example) that standings and reports "
                                "can be filtered down to, without needing a whole separate season for it."
                            ),
                        ],
                    },
                ],
            },
            {
                'slug': 'howto-league-setup-scorecards',
                'name': 'The Scorecards',
                'articles': [],
            },
        ],
    },
    {
        'slug': 'howto-general-info',
        'icon': '🔑',
        'name': 'General Information',
        'articles': [
            {
                'slug': 'logins',
                'title': 'Two Ways to Sign In',
                'body': [
                    (
                        "BGLT gives a league two different ways in."
                    ),
                    (
                        "<strong>Shared League ID &amp; Password:</strong> Everyone uses the same "
                        "League ID and the same password, except admins, who have their own unique "
                        "password. This is fast and easy to hand out to a whole roster without asking "
                        "anyone to create an account. Because it's fast and easy, this is the default "
                        "way a league gets set up."
                    ),
                    (
                        "<strong>Individual Account:</strong> Email &amp; password, tied to one "
                        "specific person. Anyone can create their own individual account and link it "
                        "to their league(s). If you're active in more than one league, an individual "
                        "account lets you move between them without logging in and out over and over."
                    ),
                    (
                        "To link your individual account to a league, hit the “Add League” button "
                        "from the “My Leagues” page. Log into your league using the shared League ID "
                        "and password, and you're linked. Switch which league is active anytime from "
                        "My Leagues, and remove one from your account there too, without affecting the "
                        "league itself or the shared League ID and password."
                    ),
                    (
                        "Both ways to sign in work side by side. Some people can keep using the shared "
                        "league password while others use their individual account."
                    ),
                    (
                        "Individual accounts can hold league admin roles as well. The League Admin can "
                        "promote any league member's individual account to an admin role from "
                        "<a href=\"/users/\">Admin → Manage Users</a>."
                    ),
                    (
                        "If the <strong>shared admin password</strong> is forgotten, use “Forgot "
                        "Password” on the login page's League tab: enter the League ID and the admin "
                        "email on file, and a reset link goes out automatically. The <strong>shared "
                        "member password</strong> has no self-serve reset; contact your league admin "
                        "for it."
                    ),
                    (
                        "<strong>Individual accounts</strong> (either role, including an admin's own "
                        "individual account) have their own separate “Forgot Password?” link on the "
                        "login page's Individual Account tab: enter the account's email and a reset "
                        "link goes out the same way. Another League Admin can also reset an individual "
                        "account from <a href=\"/users/\">Manage Users</a> if that's faster, or reach "
                        "out directly if yours is the only admin account."
                    ),
                ],
            },
            {
                'slug': 'transferring-access',
                'title': 'Transferring League Access',
                'body': [
                    (
                        "Because individual accounts carry a role on top of the shared league password "
                        "rather than replacing it, handing admin access to someone else doesn't mean "
                        "changing a password the whole league would need re-told. From "
                        "<a href=\"/users/\">Admin → Manage Users</a>, promote any existing "
                        "individual account to League Admin, or demote one back to Member, with the "
                        "Set Role action. No password changes involved either way."
                    ),
                    (
                        "If the person taking over admin duties doesn't have an individual account yet, "
                        "have them register one first (see “Two Ways to Sign In” above) using the "
                        "league's current admin or member password, then promote that new account from "
                        "Manage Users."
                    ),
                    (
                        "The league's shared League ID + admin/member passwords stay in place no matter "
                        "who holds individual admin roles. Rotate those separately, from League Settings, "
                        "if a departing admin's access to the shared login itself needs cutting off too. "
                        "Promoting/demoting an individual account's role doesn't touch the shared "
                        "passwords at all."
                    ),
                ],
            },
            {
                'slug': 'season-checklist',
                'title': 'Before Your First Season: A Setup Checklist',
                'body': [
                    (
                        "A handful of decisions are much cheaper to make once, before week 1, than to "
                        "change mid-season after real rounds have already been scored against the old "
                        "settings:"
                    ),
                ],
                'steps': [
                    (
                        "<strong>Handicap settings</strong>: rounds-to-average, handicap percent, and "
                        "the max index cap all feed the handicap calculation from the very first round. "
                        "Changing any of them after scores exist means running a full Handicap Rebuild "
                        "to make history consistent with the new numbers. See "
                        "<a href=\"/wiki#handicaps\">Handicaps</a>."
                    ),
                    (
                        "<strong>Absence &amp; sub policy</strong>: decide upfront whether an absent "
                        "player's ghost score can win the overall point against their opponent, and how "
                        "subs get requested vs. admin-assigned. See "
                        "<a href=\"/wiki#setting-1.08\">Absence Overall Point Policy</a>."
                    ),
                    (
                        "<strong>Rain-out plan</strong>: know how a rained-out week gets rescheduled "
                        "before the first one actually happens, not while it's raining. See "
                        "<a href=\"/wiki#howto-league-setup-schedule\">League Setup → The Schedule</a>."
                    ),
                    (
                        "<strong>Tiebreakers &amp; scoring format</strong>: pick the scoring format and "
                        "point values before anyone's played a hole under them; changing formats "
                        "mid-season mixes two different points systems in the same standings."
                    ),
                    (
                        "<strong>Skins/contest money</strong>: if any real stakes are riding on skins or "
                        "contests, set the pot/payout rules up before week 1, not after the first pot's "
                        "already been played for. See "
                        "<a href=\"/wiki#skins-contests\">Skins &amp; Contests</a>."
                    ),
                    (
                        "<strong>Tees</strong>: set each course's default tee and, if it matters to your "
                        "league, each player's personal default tee, so scorecards aren't defaulting to "
                        "a guess on the first week. See "
                        "<a href=\"/wiki#default-tees\">Default Tees &amp; Tee Selection Order</a>."
                    ),
                ],
            },
        ],
    },
    {
        'slug': 'howto-league-formats',
        'icon': '🏆',
        'name': 'League Formats and Ideas',
        'articles': [],
    },
    {
        'slug': 'howto-email-text',
        'icon': '📢',
        'name': 'E-mail and Text Messaging',
        'articles': [
            {
                'slug': 'setting-up-league-email',
                'title': 'Setting Up League Email',
                'body': [
                    (
                        "Member-facing email (announcements, a round being posted, a sub getting "
                        "assigned) goes out through your own league's SMTP settings, configured once "
                        "from Admin → Email Settings: host, port, sender address/name, and whether each "
                        "of those three trigger types actually sends an email or stays silent. There's "
                        "no shared platform sender for these: a league that never sets this up simply "
                        "won't send member emails; players/admins would still see the in-app "
                        "Announcements or notification, just no email copy."
                    ),
                    (
                        "A Test send is built into that same settings page: after saving, send a test "
                        "straight to the address on file before trusting the real thing to any player's "
                        "inbox."
                    ),
                    (
                        "Platform-level emails (password resets, League ID lookups) are separate from "
                        "all of this. Those send from BGLT's own sender regardless of whether a league has "
                        "configured its own SMTP at all."
                    ),
                    (
                        "A one-off Blast (subject + free-text body, sent to every player with an email on "
                        "file) also lives on the Email Settings page, for anything that doesn't fit the "
                        "Announcements or Weekly Recap flows below."
                    ),
                ],
            },
            {
                'slug': 'announcements-weekly-recap',
                'title': 'Announcements & Weekly Recap',
                'body': [
                    (
                        "Announcements post from Admin → Announcements: shown in-app, and emailed too if "
                        "Email Settings has that trigger turned on. They can be toggled active/inactive "
                        "without deleting them, so an old one can come down without losing its text if "
                        "it's needed again."
                    ),
                    (
                        "The Weekly Recap is a heavier, separate tool: a full digest (results, standings, "
                        "low gross/net, handicaps, upcoming schedule) built from real season data, with a "
                        "live preview and an Email vs. plain-text Copy mode, so it can go out however a "
                        "league actually communicates (email blast, group text, whatever's normal for "
                        "that group), not just email."
                    ),
                    (
                        "Two real gaps worth knowing about: BGLT doesn't send text messages directly; the "
                        "Copy-as-text mode is built for pasting into a group text yourself, not automated "
                        "SMS. And there's no delivery log for emails sent (bounces, opens): a Test send "
                        "confirms the setup can send at all, not what happened to any specific real email "
                        "afterward."
                    ),
                ],
            },
        ],
    },
    {
        'slug': 'howto-reporting',
        'icon': '📊',
        'name': 'Reporting',
        'articles': [
            {
                'slug': 'exporting-printing',
                'title': 'Exporting & Printing',
                'body': [
                    (
                        "Standings, scores, the roster, and the schedule can each be exported straight to "
                        "CSV from the season Reports page. Useful for anything that needs to leave BGLT, "
                        "like a league newsletter or handing a spreadsheet to a new admin."
                    ),
                    (
                        "For anything meant to be read on-screen or printed as-is, BGLT doesn't have a "
                        "separate print/PDF button. The browser's own Print command works directly "
                        "against the page as rendered, same as any other web page."
                    ),
                    (
                        "Printing Scorecards is the one report built specifically for a physical hand-out: "
                        "a season's scorecards laid out for printing (header, group rows, side/team "
                        "labels, points columns) rather than the on-screen scoring view, reachable from "
                        "the Admin Quick Options row."
                    ),
                ],
            },
            {
                'slug': 'stats-vs-weekly-reports',
                'title': 'Stats & Records vs. Weekly Reports',
                'body': [
                    (
                        "Two places can sound like they cover the same ground. The weekly Reports page is "
                        "season/week-scoped: standings, a specific week's scorecard, a full season "
                        "summary, and the CSV exports above. Stats &amp; Records is the standing library "
                        "(season stats, hole-by-hole averages, a scoring leaderboard, head-to-head player "
                        "comparison, and participation), browsable any time, without picking a week first."
                    ),
                    (
                        "One thing BGLT doesn't have: a way to save a particular filter or report view and "
                        "pin it for later. Stats &amp; Records' categories are fixed; if there's a specific "
                        "cut you find yourself rebuilding every week, that's worth flagging rather than "
                        "assuming it's saved somewhere already."
                    ),
                ],
            },
        ],
    },
    {
        'slug': 'howto-handicaps',
        'icon': '🧮',
        'name': 'Handicaps',
        'articles': [
            {
                'slug': 'how-calculated',
                'title': 'How Your Handicap Gets Calculated',
                'body': [
                    (
                        "BGLT's handicap is par-based, not the USGA slope/rating system. That's by "
                        "design, to keep it simple for a casual weeknight league. It's built entirely "
                        "from your own recent rounds, nothing else."
                    ),
                    (
                        "Each round produces a differential (your gross score vs. par, adjusted by "
                        "<a href=\"/wiki#setting-2.07\">Max Score Per Hole</a> if that's set). Your index "
                        "is the average of your most recent rounds: how many rounds are in that window "
                        "and how many of your worst scores get dropped before averaging are both "
                        "league-level settings. See "
                        "<a href=\"/wiki#setting-2.02\">Rounds to Average</a> and "
                        "<a href=\"/wiki#setting-2.03\">High Scores to Drop</a>."
                    ),
                    (
                        "That raw index isn't what you actually play off of. It gets reduced by "
                        "<a href=\"/wiki#setting-2.05\">Handicap Percent</a> (typically 90%) and capped "
                        "by <a href=\"/wiki#setting-2.06\">Max Handicap Index</a> to produce your Playing "
                        "Handicap, which is the number that actually gives you strokes on the course."
                    ),
                    (
                        "One setting worth knowing about upfront: "
                        "<a href=\"/wiki#setting-2.09\">Carry Scores Across Seasons</a> decides whether "
                        "rounds from a prior season still count toward your averaging window once a new "
                        "season starts, or whether everyone effectively starts fresh."
                    ),
                ],
            },
            {
                'slug': 'new-players',
                'title': 'New & Returning Players: The Pre-Eligibility Period',
                'body': [
                    (
                        "A player needs a minimum number of real rounds "
                        "(<a href=\"/wiki#setting-2.04\">Min Rounds Required</a>) before they have a real, "
                        "averaged handicap index. Before that, they're not left at scratch. Each "
                        "pre-eligibility round gets its own one-off temporary handicap, computed fresh "
                        "from that single round's own score. It's never averaged with other "
                        "pre-eligibility rounds and never carried into the next one."
                    ),
                    (
                        "There are actually two temp-handicap percentages, not one: "
                        "<a href=\"/wiki#setting-2.10\">one for a regular member's own rounds</a> and "
                        "<a href=\"/wiki#setting-2.11\">a separate one for rounds flagged as a "
                        "substitute</a>. That sub flag is per-round, not a permanent label on a player, "
                        "so if a full member fills in as someone else's sub for a single week, that one "
                        "round uses the sub percentage even though every other round of theirs uses the "
                        "member one."
                    ),
                    (
                        "Provisional rounds are marked with a small asterisk wherever a handicap shows up "
                        "(standings, schedule, player profile, dashboard), so it's clear the number isn't "
                        "final yet. Once a player crosses the minimum-rounds threshold, their real average "
                        "takes over automatically on their very next round; there's no manual switch to "
                        "flip."
                    ),
                ],
            },
            {
                'slug': 'fixing-a-handicap',
                'title': 'Fixing a Wrong Handicap',
                'body': [
                    (
                        "Three different tools touch handicaps and points, and they're not "
                        "interchangeable; using the wrong one either does too little or redoes more "
                        "than necessary:"
                    ),
                ],
                'steps': [
                    (
                        "<strong>Recalc Handicaps</strong> (season page, “↺ Recalc Handicaps”): "
                        "recomputes every player's current index for one season from their latest rounds. "
                        "Doesn't touch match results or points at all."
                    ),
                    (
                        "<strong>Recalc Points</strong> (Admin → Season panel, “🔁 Recalc Points”): "
                        "recomputes hole and overall points for every completed round in one season, using "
                        "each round's already-stored handicap. Reach for this after a scoring-rule change, "
                        "not a handicap change. It deliberately leaves handicaps alone."
                    ),
                    (
                        "<strong>Rebuild Handicap Timeline</strong> (Admin → More Tools → 🛠 Rebuild "
                        "Handicap Timeline), the full rebuild: every player's handicap, every round's net "
                        "score, and every match's points, walked in true chronological order across every "
                        "season, using whatever settings were actually in effect on each round's own date. "
                        "This is the one to reach for after changing a handicap setting (rounds-to-average, "
                        "percent, cap, etc.). It can preview the result first (same code path as the real "
                        "apply, just rolled back afterward) before you commit to it."
                    ),
                    (
                        "Two separate manual-override mechanisms also exist, and they don't conflict with "
                        "each other: the <strong>Handicap Matrix</strong> lets you hand-edit one specific "
                        "round's playing handicap, while the <strong>Handicap History</strong> page lets "
                        "you set an override that becomes every following round's starting point going "
                        "forward, with a required reason kept visible in that player's history permanently."
                    ),
                    (
                        "If a player's handicap needs to stop counting old rounds after an injury or long "
                        "absence, set an <strong>Oldest Date For Handicap</strong> on their player edit "
                        "page. Rounds before that date are excluded from their averaging window without "
                        "deleting any of their actual scoring history."
                    ),
                ],
            },
        ],
    },
    {
        'slug': 'howto-points',
        'icon': '🏌️',
        'name': 'Points',
        'articles': [
            {
                'slug': 'choosing-a-format',
                'title': 'Choosing a Scoring Format',
                'body': [
                    (
                        "A league runs one scoring format at a time, set on League Settings: Match Play, "
                        "Stableford, Best Ball, Team Totals, or Classical Stroke Play (see "
                        "<a href=\"/wiki#setting-1.03\">Scoring Format</a> for how each one is scored). "
                        "Switching formats mid-season is possible, but every round already played stays "
                        "scored under whatever format was active when it was entered. It mixes two point "
                        "systems in the same season's standings, so it's worth picking a format before "
                        "week 1 rather than partway through."
                    ),
                    (
                        "Each format has its own point values (per-hole win/tie, overall bonus) as separate "
                        "settings: Match Play's are at "
                        "<a href=\"/wiki#setting-1.05\">1.05-1.07</a>, Best Ball's at "
                        "<a href=\"/wiki#setting-1.09\">1.09-1.11</a>, Team Totals' at "
                        "<a href=\"/wiki#setting-1.12\">1.12-1.14</a>, and Classical Stroke Play's single "
                        "points-per-stroke setting at "
                        "<a href=\"/wiki#setting-1.15\">1.15</a>. Only the settings for the active format "
                        "actually do anything."
                    ),
                ],
            },
            {
                'slug': 'match-play-two-nets',
                'title': 'Why Match Play Shows Two Different Net Scores',
                'body': [
                    (
                        "If your league runs Match Play, you'll notice the Scoring Debug page shows two "
                        "different net numbers per hole. That's not a bug; it's two genuinely different "
                        "calculations answering two different questions."
                    ),
                    (
                        "<strong>Hole-by-hole win/loss</strong> is decided by comparing strokes the way "
                        "real singles match play does: only the higher-handicap player in the pairing "
                        "gets strokes, one per hole up to their handicap gap with the other player, given "
                        "on the hardest holes first. This result depends on who you're paired against. "
                        "The same round could come out differently against a different opponent."
                    ),
                    (
                        "The <strong>overall point</strong> for the round works differently on purpose. "
                        "It compares each player's own full net score (their own gross minus their own "
                        "full handicap, nothing to do with who they're paired against) the way stroke "
                        "play does. This is the number that also drives your personal stats, Standings, "
                        "and the Net column everywhere else in the app."
                    ),
                    (
                        "Because the two methods allocate strokes differently, they can occasionally "
                        "disagree on a single hole. Someone can be down on the hole-by-hole result but "
                        "still take the overall point, or vice versa. That's expected, not a scoring "
                        "error. Stableford leagues never see this, since every player scores against par "
                        "independently there with no opponent-dependent math involved."
                    ),
                ],
            },
            {
                'slug': 'overriding-points',
                'title': 'Overriding a Match’s Points',
                'body': [
                    (
                        "The scoring engine can't model every possible ruling: a rules infraction, a "
                        "bonus, a one-off admin decision. For those, an admin can manually override a "
                        "player's points for a specific matchup directly from the Scoring Debug page "
                        "(“Override Points →” next to any matchup)."
                    ),
                    (
                        "A reason is required for every override, and nothing gets silently lost: the "
                        "full history of every override ever set on a matchup (who, when, what it was "
                        "before, what it changed to) stays visible on that same page permanently, not "
                        "just the current value. An overridden value shows an “Overridden” badge anywhere "
                        "it appears."
                    ),
                    (
                        "Clearing an override is its own explicit action, not something that happens as a "
                        "side effect of re-saving scores. Clearing it re-runs the normal points "
                        "calculation for that round so the value actually reverts to what the engine would "
                        "compute on its own."
                    ),
                ],
            },
        ],
    },
    {
        'slug': 'howto-subs',
        'icon': '🔄',
        'name': 'Subs',
        'articles': [
            {
                'slug': 'managing-a-sub',
                'title': 'Handling a Sub or an Absence for a Matchup',
                'body': [
                    (
                        "From any matchup's Subs/Absences page, mark any scheduled player Absent, and "
                        "either assign an existing player as their SUB or type in a new name on the spot. "
                        "Typing a new name creates that person as a player automatically, no separate "
                        "roster step needed first."
                    ),
                    (
                        "Each absence can also be marked Excused, with an optional reason. Excused status "
                        "feeds directly into how that absence affects the overall point. See “What "
                        "Happens When a Player Is Marked Absent” below."
                    ),
                ],
            },
            {
                'slug': 'sub-requests',
                'title': 'Players Requesting a Sub',
                'body': [
                    (
                        "A player who knows they can't make an upcoming week can request a sub straight "
                        "from their own schedule, with an optional note, instead of texting the admin "
                        "directly. Their request shows up under My Sub Requests, where it can be cancelled "
                        "any time before it's filled if plans change."
                    ),
                    (
                        "Every open request across the whole league lands in one place for the admin "
                        "(Admin → 🔄 Sub Requests), sorted by the week it's for, ready to assign a "
                        "specific sub to from that same queue rather than hunting through individual "
                        "matchups."
                    ),
                ],
            },
            {
                'slug': 'ghost-scores',
                'title': 'What Happens When a Player Is Marked Absent (No Sub)',
                'body': [
                    (
                        "If a player is marked Absent with no sub assigned, BGLT still needs a score to "
                        "keep the matchup scoreable. It generates a “ghost” score for them automatically "
                        "(par on every hole, adjusted for their handicap), shown in italics wherever it "
                        "appears so it's never mistaken for a score they actually played."
                    ),
                    (
                        "Whether that ghost score can still win the overall point against their opponent "
                        "is a league policy choice, not automatic. See "
                        "<a href=\"/wiki#setting-1.08\">Absence Overall Point Policy</a>. Marking an "
                        "absence Excused only matters if that policy is set to key off excused status; "
                        "otherwise it's just a record-keeping note."
                    ),
                    (
                        "Ghost scores never count toward personal gross stats (average gross, best gross, "
                        "rounds played for gross purposes), regardless of what the points policy is set "
                        "to, since nothing was actually played. That exclusion is unconditional and "
                        "separate from the points question above."
                    ),
                ],
            },
        ],
    },
    {
        'slug': 'howto-contests',
        'icon': '💰',
        'name': 'Contests',
        'articles': [
            {
                'slug': 'setting-up-skins',
                'title': 'Setting Up Skins',
                'body': [
                    (
                        "Skins run per round, not per season. The Skins page (season overview) lists "
                        "every completed round in that season as its own entry: participant count, pot "
                        "size, and whether it's been calculated yet. Nothing calculates automatically; an "
                        "admin opens a round and hits Calculate once scores are in."
                    ),
                    (
                        "Each round pulls its buy-in amount and gross/net basis from the season's Skins "
                        "defaults (<a href=\"/wiki#setting-5.02\">Default Buy-In Amount</a>, "
                        "<a href=\"/wiki#setting-5.01\">Default Scoring</a>) unless overridden for that "
                        "specific round. If nobody wins a hole, its pot carries forward into the next "
                        "calculated round rather than disappearing."
                    ),
                    (
                        "Skins Flights split entrants into handicap-based groups (Low/High, or more) so "
                        "one low-handicapper doesn't sweep every hole. Flights use up to four threshold "
                        "cutoffs set on the season's Skins settings; once enabled, results, pots, and "
                        "carryovers are all tracked separately per flight, not pooled together."
                    ),
                    (
                        "Turning on <a href=\"/wiki#setting-5.03\">Allow Players to Self Opt-In</a> lets "
                        "members choose for themselves whether they're playing for skins that week, "
                        "instead of an admin building the participant list by hand every round."
                    ),
                ],
            },
            {
                'slug': 'custom-contests',
                'title': 'Setting Up Custom Contests',
                'body': [
                    (
                        "Beyond skins, Custom Contests cover the usual side games (Long Drive, Closest to "
                        "Pin, Low Gross, Low Net, Most Birdies, or a fully custom one), set up per season "
                        "from the Contests admin page, each tied to a specific week (or every week, if "
                        "Recurrence is set to run it week-by-week instead of once)."
                    ),
                    (
                        "Team Low Net is the one type BGLT calculates automatically from that week's "
                        "scorecards: Calculate (or Calculate All, for a recurring one) fills in results "
                        "with no hand-entry. Every other contest type needs its winner(s) entered "
                        "manually, since there's no way to know who hit the longest drive from scorecard "
                        "data alone."
                    ),
                    (
                        "Results stay editable after the fact, and the Contest Winners report pulls "
                        "everything together across a season (by contest, by week, low score, or skins "
                        "leader), so players aren't hunting through individual weeks to see who's won what."
                    ),
                ],
            },
        ],
    },
    {
        'slug': 'howto-trouble-shooting',
        'icon': '🔧',
        'name': 'Trouble Shooting',
        'articles': [],
    },
]
