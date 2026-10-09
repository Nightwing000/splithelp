from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class UserNotFoundError(Exception):
    pass


@dataclass
class User:
    id: int
    name: str
    email: str
    created_at: datetime
    deleted_at: datetime | None


class UserRepository:
    def __init__(self, pool):
        self.pool = pool

    def create(self, name: str, email: str) -> User:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO Users (name, email) VALUES (%s, %s) "
                    "RETURNING id, name, email, created_at, deleted_at",
                    (name, email),
                )
                row = cur.fetchone()
                return User(
                    id=row[0],
                    name=row[1],
                    email=row[2],
                    created_at=row[3],
                    deleted_at=row[4],
                )

    def get_by_id(self, user_id: int) -> User | None:
        # TODO: SELECT ... WHERE id = %s
        # TODO: return None if no row found
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, email, created_at, deleted_at FROM Users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return User(
                    id=row[0],
                    name=row[1],
                    email=row[2],
                    created_at=row[3],
                    deleted_at=row[4],
                )

    def get_by_email(self, email: str) -> User | None:
        # TODO: SELECT ... WHERE email = %s
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, email, created_at, deleted_at FROM Users WHERE email = %s",
                    (email,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return User(
                    id=row[0],
                    name=row[1],
                    email=row[2],
                    created_at=row[3],
                    deleted_at=row[4],
                )

    def soft_delete(self, user_id: int) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE Users SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (user_id,),
                )
                if cur.rowcount == 0:
                    raise UserNotFoundError(f"No user with id {user_id}")

    def list_active(self) -> list[User]:
        # TODO: SELECT ... WHERE deleted_at IS NULL
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, email, created_at, deleted_at FROM Users WHERE deleted_at IS NULL"
                )
                rows = cur.fetchall()
                return [
                    User(
                        id=row[0],
                        name=row[1],
                        email=row[2],
                        created_at=row[3],
                        deleted_at=row[4],
                    )
                    for row in rows
                ]
