"""S2-B-8 performance: deleting a 200-member group writes 19,900 friendship rows in ONE statement, under 2 s.
Timing is asserted on PostgreSQL only (TEST_DATABASE_URL); on SQLite the row count and statement count still run."""
import time
import uuid

from sqlalchemy import event, func, select

from app.models import Friendship, GroupMember, User
from app.security import new_friend_code

from tests.test_auth import reg
from tests.test_friends_keep import _group, _h, _uid

from tests.conftest import PG_URL


def test_delete_200_member_group_is_one_statement_and_fast(client, db_session, engine):
    owner = reg(client, email="owner@example.com", name="Owner").json()
    gid = _group(client, owner, [])
    users = [User(email=f"u{i}@example.com", name=f"U{i}", is_registered=False, default_currency="USD",
                  time_zone="UTC", notification_prefs={}, friend_code=new_friend_code() + str(i))
             for i in range(199)]
    db_session.add_all(users)
    db_session.flush()
    db_session.add_all(GroupMember(group_id=uuid.UUID(gid), user_id=u.id, role="member", sort_index=i + 1,
                                   added_by=uuid.UUID(_uid(owner))) for i, u in enumerate(users))
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == uuid.UUID(gid))) == 200

    inserts = []

    def spy(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO FRIENDSHIPS"):
            inserts.append(statement)

    event.listen(engine, "before_cursor_execute", spy)
    try:
        t0 = time.perf_counter()
        r = client.delete(f"/groups/{gid}", headers=_h(owner))
        elapsed = time.perf_counter() - t0
    finally:
        event.remove(engine, "before_cursor_execute", spy)
    assert r.status_code == 204, r.text
    assert len(inserts) == 1
    assert db_session.scalar(select(func.count()).select_from(Friendship)) == 200 * 199 // 2
    if PG_URL:
        assert elapsed < 2.0, elapsed
