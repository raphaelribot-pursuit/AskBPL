"""Retrieval verification test questions (Step 01 acceptance harness)."""

from __future__ import annotations

TEST_QUESTIONS: list[tuple[str, str]] = [
    # materials_selection
    ("What is the main purpose of the Materials Selection Policy?", "materials_selection"),
    ("Who has the final authority over selecting and retaining library materials?", "materials_selection"),
    ("What criteria are used when deciding whether to add an item to the collection?", "materials_selection"),
    (
        "How does the organization handle requests to reconsider or challenge a specific item in the collection?",
        "materials_selection",
    ),
    # unattended_children
    ("What is considered an unattended child under this policy?", "unattended_children"),
    ("Is the organization responsible for supervising children left alone in the building?", "unattended_children"),
    ("What should staff do if an unattended child is disruptive or unsafe?", "unattended_children"),
    ("What steps should staff take if a child is left alone at closing time?", "unattended_children"),
    # annual_leave
    ("Who is eligible to earn annual leave under the Annual Leave Policy?", "annual_leave"),
    ("How much annual leave does a non-union employee earn based on years of service?", "annual_leave"),
    ("When can a new hire start using their annual leave?", "annual_leave"),
    ("How much unused annual leave can be carried over to the next plan year?", "annual_leave"),
    # conflict_of_interest
    ("Who is considered a Covered Person under the Conflict of Interest Policy?", "conflict_of_interest"),
    ("What types of relationships or transactions might create a conflict of interest?", "conflict_of_interest"),
    ("What is a Covered Person required to do if they think a conflict exists?", "conflict_of_interest"),
    ("How are related-party transactions reviewed and approved?", "conflict_of_interest"),
    # fundraising
    ("Which department is responsible for managing fundraising activities?", "fundraising"),
    ("When does a fundraising initiative require Board approval?", "fundraising"),
    ("How are private donations and government grants processed and acknowledged?", "fundraising"),
    ("What administrative fees apply to restricted private grants?", "fundraising"),
    # volunteer_manual
    ("What is the role of the Office of Volunteer Resources?", "volunteer_manual"),
    ("Can employees serve as volunteers, and under what conditions?", "volunteer_manual"),
    ("Are volunteers allowed to replace paid staff positions?", "volunteer_manual"),
    (
        "What screening or background checks may be required for volunteers working with children?",
        "volunteer_manual",
    ),
]
