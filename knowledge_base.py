KNOWLEDGE_ITEMS = [
    {
        "id": "users",
        "kind": "schema",
        "content": (
            "Users stores application user records. "
            "Important columns: id (primary key), name, email, "
            "created_at, and deleted_at. "
            "Users are soft-deleted by setting deleted_at to a timestamp; "
            "active users have deleted_at IS NULL. "
            "A soft-deleted user still exists and may have historical "
            "expenses, payments, and group memberships. "
            "Join related tables using Users.id and their user_id columns."
        ),
        "keywords": [
            "user", "users", "name", "email", "active",
            "deleted", "member", "person", "account",
        ],
    },
    {
        "id": "expense_payments",
        "kind": "schema",
        "content": (
            "ExpensePayments records how much a user paid toward an expense. "
            "Important columns: id (primary key), expense_id, user_id, "
            "and amount. "
            "Join ExpensePayments.expense_id to Expenses.id and "
            "ExpensePayments.user_id to Users.id. "
            "Each expense can have multiple payers, but UNIQUE "
            "(expense_id, user_id) permits at most one payment row per "
            "user per expense. "
            "amount must be greater than zero. "
            "Use SUM(amount) to calculate how much a user paid. "
            "Payment rows contribute positively to a user's net balance."
        ),
        "keywords": [
            "payment", "payments", "paid", "payer", "spent",
            "contribution", "amount", "total paid", "covered",
        ],
    },
    {
        "id": "groups",
        "kind": "schema",
        "content": (
            "Groups represents a collection of users who share expenses. "
            "Important columns: id (primary key), name, created_by, "
            "and created_at. "
            "Groups.created_by references the user who created the group. "
            "Join Groups.id to GroupMembers.group_id to find group members "
            "and to Expenses.group_id to find the group's expenses."
        ),
        "keywords": [
            "group", "groups", "created", "creator",
            "owner", "sharing", "community",
        ],
    },
    {
        "id": "group_members",
        "kind": "schema",
        "content": (
            "GroupMembers represents group membership between users and "
            "groups. "
            "Important columns: group_id, user_id, and joined_at. "
            "The composite primary key (group_id, user_id) prevents a user "
            "from being added to the same group more than once. "
            "Join GroupMembers.group_id to Groups.id and "
            "GroupMembers.user_id to Users.id. "
            "Use this table to determine which users belong to a group."
        ),
        "keywords": [
            "member", "members", "membership", "belongs",
            "join", "joined", "participant",
        ],
    },
    {
        "id": "expenses",
        "kind": "schema",
        "content": (
            "Expenses records expenses that belong to a group. "
            "Important columns: id (primary key), group_id, description, "
            "and created_at. "
            "Join Expenses.group_id to Groups.id. "
            "Join ExpensePayments.expense_id and "
            "ExpenseSplits.expense_id to Expenses.id to find who paid "
            "and who owes money for an expense."
        ),
        "keywords": [
            "expense", "expenses", "cost", "purchase",
            "description", "group", "spending",
        ],
    },
    {
        "id": "expense_splits",
        "kind": "schema",
        "content": (
            "ExpenseSplits records how much each user owes for an expense. "
            "Important columns: id (primary key), expense_id, user_id, "
            "split_type, and amount_owed. "
            "Join ExpenseSplits.expense_id to Expenses.id and "
            "ExpenseSplits.user_id to Users.id. "
            "split_type is restricted to equal, exact, or shares. "
            "amount_owed always stores the resolved monetary amount owed, "
            "regardless of split_type, and must not be negative. "
            "Each expense can have at most one split row per user. "
            "Split rows contribute negatively to a user's net balance."
        ),
        "keywords": [
            "split", "splits", "owes", "owed", "debt",
            "equal", "exact", "shares", "amount owed",
        ],
    },
]
