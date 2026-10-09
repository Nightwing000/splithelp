-- ============================================================
-- Users
-- ============================================================
CREATE TABLE Users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

-- ============================================================
-- Groups
-- ============================================================
CREATE TABLE Groups (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (created_by)
        REFERENCES Users(id)
        ON DELETE RESTRICT
);

-- ============================================================
-- GroupMembers
-- ============================================================
CREATE TABLE GroupMembers (
    group_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (group_id, user_id),

    FOREIGN KEY (group_id)
        REFERENCES Groups(id)
        ON DELETE CASCADE,

    FOREIGN KEY (user_id)
        REFERENCES Users(id)
        ON DELETE RESTRICT
);

-- ============================================================
-- Expenses
-- ============================================================
CREATE TABLE Expenses (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL,
    description VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (group_id)
        REFERENCES Groups(id)
        ON DELETE CASCADE
);

-- ============================================================
-- ExpensePayments
-- ============================================================
CREATE TABLE ExpensePayments (
    id BIGSERIAL PRIMARY KEY,
    expense_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,

    UNIQUE (expense_id, user_id),

    FOREIGN KEY (expense_id)
        REFERENCES Expenses(id)
        ON DELETE CASCADE,

    FOREIGN KEY (user_id)
        REFERENCES Users(id)
        ON DELETE RESTRICT,

    CHECK (amount > 0)
);

-- ============================================================
-- ExpenseSplits
-- ============================================================
CREATE TABLE ExpenseSplits (
    id BIGSERIAL PRIMARY KEY,
    expense_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    split_type VARCHAR(20) NOT NULL,
    amount_owed NUMERIC(12, 2) NOT NULL,

    UNIQUE (expense_id, user_id),

    FOREIGN KEY (expense_id)
        REFERENCES Expenses(id)
        ON DELETE CASCADE,

    FOREIGN KEY (user_id)
        REFERENCES Users(id)
        ON DELETE RESTRICT,

    CHECK (split_type IN ('equal', 'exact', 'shares')),
    CHECK (amount_owed >= 0)
);

-- ============================================================
-- Balance-invariant trigger function
-- Fires after any write to ExpensePayments or ExpenseSplits;
-- deferred to transaction commit so multi-statement edits
-- (e.g. delete + re-insert within one transaction) aren't
-- rejected on an intermediate, temporarily-unbalanced state.
-- ============================================================
CREATE OR REPLACE FUNCTION check_expense_balance()
RETURNS TRIGGER AS $$
DECLARE
    total_paid   NUMERIC;
    total_owed   NUMERIC;
    target_id    BIGINT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_id := OLD.expense_id;
    ELSE
        target_id := NEW.expense_id;
    END IF;

    SELECT COALESCE(SUM(amount), 0) INTO total_paid
    FROM ExpensePayments WHERE expense_id = target_id;

    SELECT COALESCE(SUM(amount_owed), 0) INTO total_owed
    FROM ExpenseSplits WHERE expense_id = target_id;

    IF total_paid <> total_owed THEN
        RAISE EXCEPTION 'Expense % unbalanced: paid=% owed=%', target_id, total_paid, total_owed;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER check_expense_payments_balance
AFTER INSERT OR UPDATE OR DELETE
ON ExpensePayments
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION check_expense_balance();

CREATE CONSTRAINT TRIGGER check_expense_splits_balance
AFTER INSERT OR UPDATE OR DELETE
ON ExpenseSplits
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION check_expense_balance();
