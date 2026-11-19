# SplitHelp

A group expense splitter you can talk to. Record shared expenses from a
Telegram chat, and ask questions about them in plain English:

```
/add 4000 Fireworks +ishan:1080 on:2026-11-08 at:Cracker_Bazaar
→ Ishan pays ₹4000; ₹1080 of sky shots is his alone, the other ₹2920 is
  split equally between the 5 members.
  Shares: Ishan ₹1664.00, rahul ₹584.00, krish ₹584.00, jaffer ₹584.00, sush ₹584.00

/balances
→ Ishan is owed ₹2336.00
  jaffer owes ₹584.00
  krish owes ₹584.00
  rahul owes ₹584.00
  sush owes ₹584.00

  Suggested payments:
  krish pays Ishan ₹584.00
  jaffer pays Ishan ₹584.00
  rahul pays Ishan ₹584.00
  sush pays Ishan ₹584.00

What was each person's share of the fireworks expense in the Diwali Crackers group?
→ For the fireworks expense in the Diwali Crackers group, Ishan's share is
  ₹1664.00, rahul's share is ₹584.00, krish's share is ₹584.00, jaffer's share
  is ₹584.00, and sush's share is ₹584.00.
```

Questions are answered by an LLM (Gemini) that writes SQL. The SQL is
validated, then run against PostgreSQL under a read-only role, and the answer
is checked against the database before it is shown.

## How it works

See [arch.md](arch.md) for the full diagram.

**Recording money is deterministic.** `/add` and `/settle` are parsed by
plain code ([bot_commands.py](bot_commands.py)), never by the LLM.

- Equal splits are allocated in whole cents, so 100.00 between three people is
  stored as 33.34 / 33.33 / 33.33 ([splitting.py](splitting.py)).
- `/add` options:

  | Option | Meaning |
  |---|---|
  | `@name` | Who shares the bill. Leave it out and the whole group shares it. |
  | `+name:amount` | A part charged to that person alone, e.g. something they're sponsoring. |
  | `on:YYYY-MM-DD` | The date the money was spent. |
  | `at:Shop_Name` | Where it was spent (`_` stands for a space). |

  Every split row stores the resolved amount, so mixed bills still satisfy the
  balance rule.
- All amounts are in one currency (₹). Supporting several would need
  exchange rates.
- A settlement is stored as an expense the payer paid and the recipient owes,
  which moves both balances without a separate table.
- PostgreSQL enforces that every expense balances (total paid = total split),
  using a deferred constraint trigger ([init/01_schema.sql](init/01_schema.sql)).

**Answering questions is read-only and checked at every step.**

1. **Retrieval** ([retrieval.py](retrieval.py), [knowledge_base.py](knowledge_base.py)):
   schema descriptions, business rules (such as "a negative balance means the
   user owes money"), and trusted question→SQL examples are selected by
   keyword scoring and put into the prompt. This is a lightweight form of RAG
   with no embeddings.
2. **Generation** ([nl_to_sql.py](nl_to_sql.py)): Gemini writes one SQL query.
   It falls back to a second model on rate limits, overload (503/504) and
   timeouts.
3. **Validation** ([sql_validation.py](sql_validation.py)): the SQL is parsed
   into an AST with sqlglot and must be:
   - a single `SELECT`,
   - using only allowlisted tables, columns and functions.

   Anything else is rejected before it reaches the database.
4. **Execution:** the query runs as `splitter_readonly`, a role with `SELECT`
   permission only and a 5-second `statement_timeout`. This is the backstop if
   validation ever misses something.
5. **Answering** ([response_formatting.py](response_formatting.py)):
   - Empty and single-value results are formatted in code, without the LLM.
   - Balances are converted to "owes X" / "is owed X" in code, so the LLM never
     has to interpret a sign.
   - Every number in the LLM's answer must appear in the query results. If one
     doesn't, the plain results are shown instead.

Who is asking is known from an allowlist that maps Telegram user ids to app
users. People not on the list are refused, and questions like "How much do I
owe?" resolve "I" to the right person.

## Running it

Requirements: Python 3.9+ and Docker.

```bash
pip install -r requirements.txt
cp .env.example .env                       # then fill in the values
docker compose up -d                       # PostgreSQL with the schema
python scripts/apply_migrations.py         # schema changes for older databases
python scripts/setup_read_only_role.py     # create the read-only role
python scripts/setup_read_only_role.py --verify
python scripts/seed_demo.py                # optional demo group; prints its id
```

To start the Telegram bot:

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USERS` and `SPLITHELP_GROUP_ID` in `.env`.
3. Run `python bot.py`.

In a Telegram group chat, the bot only receives plain questions if privacy
mode is turned off in BotFather (`/setprivacy`). Commands always work.

## Tests

```bash
pytest
```

285 tests. The 12 tests that need the Docker database skip automatically when
it isn't running, so CI (GitHub Actions) runs the rest on every push. Tests
never call Gemini; a fake client stands in for it.

## Known limitations

- **One group per bot instance** (`SPLITHELP_GROUP_ID`).
- **Splits from chat are equal, plus sponsored parts.** Splits by share ratio
  ("2 shares for Alex") aren't supported in chat yet, though the schema allows
  them.
- **"We" can be read as "I":** the asker's name is added to every question, so
  "what did *we* spend" may be filtered to the asker's own payments.
- **Phrasing slips:** the LLM's wording can still slip, for example by
  mentioning a column name. The numbers are checked, but the prose isn't.
- **Spelled-out numbers** ("two people") are not covered by the number check.
- **Single machine:** it runs locally; there is no deployment setup.
