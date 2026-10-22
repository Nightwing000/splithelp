# Database role setup

Add a local read-only password to `.env`:

```env
POSTGRES_READONLY_PASSWORD=your-local-password
```

The existing Docker administrator defaults are used unless overridden:

```env
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_ADMIN_USER=splitter_user
POSTGRES_ADMIN_PASSWORD=devpassword
```

With PostgreSQL running:

```powershell
python scripts/setup_read_only_role.py
python scripts/setup_read_only_role.py --verify
```

The password is loaded at runtime and is never printed. The script is
idempotent: rerunning it updates the role password and reapplies privileges.
