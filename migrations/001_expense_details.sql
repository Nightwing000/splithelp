-- Adds expense date and merchant to databases created before they were part
-- of init/01_schema.sql. Idempotent: safe to run on new and old databases.
-- Existing rows get spent_on = their created_at date, not today.

ALTER TABLE Expenses ADD COLUMN IF NOT EXISTS spent_on DATE;
UPDATE Expenses SET spent_on = created_at::date WHERE spent_on IS NULL;
ALTER TABLE Expenses ALTER COLUMN spent_on SET DEFAULT CURRENT_DATE;
ALTER TABLE Expenses ALTER COLUMN spent_on SET NOT NULL;

ALTER TABLE Expenses ADD COLUMN IF NOT EXISTS merchant VARCHAR(255) NULL;
