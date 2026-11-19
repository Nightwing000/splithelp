from typing import Literal, TypedDict


class KnowledgeItem(TypedDict):
    id: str
    kind: Literal["schema", "rule", "example"]
    content: str
    keywords: list[str]


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
            "owner", "sharing", "community", "member",
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
            "join", "joined", "participant", "group",
        ],
    },
    {
        "id": "expenses",
        "kind": "schema",
        "content": (
            "Expenses records expenses that belong to a group. "
            "Important columns: id (primary key), group_id, description, "
            "spent_on (DATE the money was spent), merchant (shop or place, "
            "may be NULL), and created_at (when the row was recorded). "
            "Join Expenses.group_id to Groups.id. "
            "Join ExpensePayments.expense_id and "
            "ExpenseSplits.expense_id to Expenses.id to find who paid "
            "and who owes money for an expense."
        ),
        "keywords": [
            "expense", "expenses", "cost", "purchase",
            "description", "group", "spending", "payment", "paid",
            "date", "when", "merchant", "shop", "store", "spent", "bought",
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
            "equal", "exact", "shares", "amount owed", "group",
        ],
    },
]


BUSINESS_RULES = [
    {
        "id": "net_balance_calculation",
        "kind": "rule",
        "content": (
            "A user's net balance within a group is calculated as "
            "the sum of their ExpensePayments.amount across the group's "
            "expenses minus the sum of their ExpenseSplits.amount_owed "
            "across those same expenses. "
            "Net balance = total paid - total owed. "
            "Calculate payments and splits separately before combining "
            "their totals to avoid multiplying rows in joins."
        ),
        "keywords": [
            "balance", "net balance", "calculate balance",
            "total paid", "total owed", "net position",
            "owes", "owing", "group",
        ],
    },
    {
        "id": "positive_balance",
        "kind": "rule",
        "content": (
            "A positive net balance means the user is owed money overall "
            "and should receive money. It does not mean the user owes money."
        ),
        "keywords": [
            "creditor", "receive", "receives", "owed money",
            "positive balance", "who gets paid",
        ],
    },
    {
        "id": "negative_balance",
        "kind": "rule",
        "content": (
            "A negative net balance means the user owes money overall "
            "and must pay money to settle their balance. "
            "The amount owed is the absolute value of the negative balance."
        ),
        "keywords": [
            "debtor", "owes", "owing", "pay", "negative balance",
            "who owes money", "amount owed",
        ],
    },
    {
        "id": "expense_dates_and_merchants",
        "kind": "rule",
        "content": (
            "Use Expenses.spent_on for when money was spent (dates, months, "
            "'in November', 'last week'); created_at is only when the row was "
            "recorded. Use Expenses.merchant for where it was spent ('at "
            "Cracker Bazaar'), matching case-insensitively with ILIKE. "
            "Find a specific expense by matching words in Expenses.description "
            "with ILIKE, e.g. description ILIKE '%fireworks%'. All amounts "
            "are in one currency, Indian rupees."
        ),
        "keywords": [
            "date", "when", "month", "november", "week", "spent", "merchant",
            "shop", "store", "bought", "at", "rupees", "description",
        ],
    },
    {
        "id": "group_scoped_balances",
        "kind": "rule",
        "content": (
            "Balances and settlements are calculated per group, not "
            "across the entire application. Include only expenses belonging "
            "to the requested group by joining Expenses.group_id to the "
            "requested group. Do not combine expenses from unrelated groups."
        ),
        "keywords": [
            "group balance", "group debts", "settlement",
            "group_id", "group expenses", "who owes whom", "owes",
        ],
    },
    {
        "id": "expense_balance_invariant",
        "kind": "rule",
        "content": (
            "For every existing expense, the sum of ExpensePayments.amount "
            "must equal the sum of ExpenseSplits.amount_owed. "
            "The database enforces this invariant using deferred constraint "
            "triggers, which validate the final transaction state. "
            "Do not interpret payment totals and split totals as unrelated "
            "amounts when modifying an expense."
        ),
        "keywords": [
            "balanced expense", "total paid", "total owed",
            "payment total", "split total", "expense invariant",
            "modify expense",
        ],
    },
    {
        "id": "active_users",
        "kind": "rule",
        "content": (
            "A user is active when Users.deleted_at IS NULL. "
            "When a question explicitly asks for active users, filter using "
            "this condition. Soft-deleted users remain in the database "
            "and may need to be included when querying historical expenses "
            "or financial records."
        ),
        "keywords": [
            "active users", "active members", "deleted users",
            "soft delete", "current members",
        ],
    },
    {
        "id": "payments_and_splits_are_distinct",
        "kind": "rule",
        "content": (
            "ExpensePayments and ExpenseSplits represent different concepts. "
            "ExpensePayments records how much each user actually paid. "
            "ExpenseSplits records how much each user owes for an expense. "
            "Do not combine them into a single signed-ledger interpretation "
            "or treat a payment as equivalent to an amount owed. "
            "Compute their totals separately, then calculate net balance "
            "as total paid minus total owed."
        ),
        "keywords": [
            "payments versus splits", "amount paid", "amount owed",
            "expense payments", "expense splits", "signed ledger",
            "payer", "split",
        ],
    },
]
SQL_EXAMPLES = [
    {
        "id": "list_active_users",
        "kind": "example",
        "content": (
            "Question: List all active users.\n"
            "SQL:\n"
            "SELECT id, name, email "
            "FROM Users "
            "WHERE deleted_at IS NULL "
            "ORDER BY name;"
        ),
        "keywords": [
            "users", "active", "people", "accounts",
        ],
    },
    {
        "id": "list_group_members",
        "kind": "example",
        "content": (
            "Question: List the members of a group.\n"
            "SQL:\n"
            "SELECT u.id, u.name, u.email "
            "FROM Users u "
            "JOIN GroupMembers gm ON gm.user_id = u.id "
            "WHERE gm.group_id = 1 AND u.deleted_at IS NULL "
            "ORDER BY u.name;"
        ),
        "keywords": [
            "members", "member", "belongs", "participants", "group",
        ],
    },
    {
        "id": "list_group_expenses",
        "kind": "example",
        "content": (
            "Question: List the expenses in a group.\n"
            "SQL:\n"
            "SELECT id, description, created_at "
            "FROM Expenses "
            "WHERE group_id = 1 "
            "ORDER BY created_at DESC;"
        ),
        "keywords": [
            "expenses", "expense", "spending", "purchases", "group",
        ],
    },
    {
        "id": "group_payment_totals",
        "kind": "example",
        "content": (
            "Question: How much did each user pay in a group?\n"
            "SQL:\n"
            "SELECT u.id, u.name, SUM(ep.amount) AS total_paid "
            "FROM ExpensePayments ep "
            "JOIN Expenses e ON e.id = ep.expense_id "
            "JOIN Users u ON u.id = ep.user_id "
            "WHERE e.group_id = 1 "
            "GROUP BY u.id, u.name "
            "ORDER BY total_paid DESC;"
        ),
        "keywords": [
            "paid", "payment", "payments", "total", "payer", "group",
        ],
    },
    {
        "id": "expense_shares",
        "kind": "example",
        "content": (
            "Question: What was each person's share of the dinner expense "
            "in the Goa Trip group?\n"
            "SQL:\n"
            "SELECT u.name, e.description, es.amount_owed AS share "
            "FROM ExpenseSplits es "
            "JOIN Expenses e ON e.id = es.expense_id "
            "JOIN Groups g ON g.id = e.group_id "
            "JOIN Users u ON u.id = es.user_id "
            "WHERE g.name = 'Goa Trip' AND e.description ILIKE '%dinner%' "
            "ORDER BY share DESC;"
        ),
        "keywords": [
            "share", "shares", "each", "person", "split", "expense",
            "portion", "part",
        ],
    },
    {
        "id": "group_net_balances",
        "kind": "example",
        "content": (
            "Question: Show each user's net balance in a group.\n"
            "SQL:\n"
            "WITH payment_totals AS ("
            "SELECT ep.user_id, SUM(ep.amount) AS total_paid "
            "FROM ExpensePayments ep "
            "JOIN Expenses e ON e.id = ep.expense_id "
            "WHERE e.group_id = 1 "
            "GROUP BY ep.user_id"
            "), split_totals AS ("
            "SELECT es.user_id, SUM(es.amount_owed) AS total_owed "
            "FROM ExpenseSplits es "
            "JOIN Expenses e ON e.id = es.expense_id "
            "WHERE e.group_id = 1 "
            "GROUP BY es.user_id"
            ") "
            "SELECT u.id, u.name, "
            "COALESCE(pt.total_paid, 0) - COALESCE(st.total_owed, 0) "
            "AS net_balance "
            "FROM Users u "
            "LEFT JOIN payment_totals pt ON pt.user_id = u.id "
            "LEFT JOIN split_totals st ON st.user_id = u.id "
            "JOIN GroupMembers gm ON gm.user_id = u.id "
            "WHERE gm.group_id = 1 "
            "ORDER BY net_balance DESC;"
        ),
        "keywords": [
            "balance", "balances", "owes", "owed", "owe",
            "payment", "payments", "split", "splits",
            "settlement", "group", "net", "paid", "total",
        ],
    },
]


ALL_KNOWLEDGE: list[KnowledgeItem] = (
    KNOWLEDGE_ITEMS + BUSINESS_RULES + SQL_EXAMPLES
)
