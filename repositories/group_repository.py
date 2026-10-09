from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from repositories.user_repository import User


class GroupNotFoundError(Exception):
    pass


class MembershipNotFoundError(Exception):
    pass


@dataclass
class Group:
    id: int
    name: str
    created_by: int
    created_at: datetime


class GroupRepository:
    def __init__(self, pool):
        self.pool = pool

    def create(self, name: str, created_by_user_id: int) -> Group:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO Groups (name, created_by) VALUES (%s, %s) "
                    "RETURNING id, name, created_by, created_at",
                    (name, created_by_user_id),
                )
                row = cur.fetchone()
                group = Group(
                    id=row[0],
                    name=row[1],
                    created_by=row[2],
                    created_at=row[3],
                )

                cur.execute(
                    "INSERT INTO GroupMembers (group_id, user_id) VALUES (%s, %s)",
                    (group.id, created_by_user_id),
                )

                return group

    def get_by_id(self, group_id: int) -> Group | None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, created_by, created_at FROM Groups WHERE id = %s",
                    (group_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return Group(
                    id=row[0],
                    name=row[1],
                    created_by=row[2],
                    created_at=row[3],
                )

    def add_member(self, group_id: int, user_id: int) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO GroupMembers (group_id, user_id) VALUES (%s, %s)",
                    (group_id, user_id),
                )

    def remove_member(self, group_id: int, user_id: int) -> None:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM GroupMembers WHERE group_id = %s AND user_id = %s",
                    (group_id, user_id),
                )
                if cur.rowcount == 0:
                    raise MembershipNotFoundError(
                        f"User {user_id} is not a member of group {group_id}"
                    )

    def list_members(self, group_id: int) -> list[User]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.id, u.name, u.email, u.created_at, u.deleted_at
                    FROM Users u
                    JOIN GroupMembers gm ON gm.user_id = u.id
                    WHERE gm.group_id = %s AND u.deleted_at IS NULL
                    """,
                    (group_id,),
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

    def list_groups_for_user(self, user_id: int) -> list[Group]:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT g.id, g.name, g.created_by, g.created_at
                    FROM Groups g
                    JOIN GroupMembers gm ON gm.group_id = g.id
                    WHERE gm.user_id = %s
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                return [
                    Group(
                        id=row[0],
                        name=row[1],
                        created_by=row[2],
                        created_at=row[3],
                    )
                    for row in rows
                ]
