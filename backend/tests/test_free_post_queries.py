"""Run actual query expressions against SQLite without production configuration."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, create_engine, select, func, case
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    nickname = Column(String)
    avatar_url = Column(String)
    phone = Column(String)


class Club(Base):
    __tablename__ = 'clubs'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    latitude = Column(Integer)
    longitude = Column(Integer)


class MatchPost(Base):
    __tablename__ = 'match_posts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    club_id = Column(Integer, nullable=True)
    created_at = Column(DateTime)


class MatchRegistration(Base):
    __tablename__ = 'match_registrations'
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer)
    status = Column(String)


def source_query(filename, function):
    file = Path(__file__).parents[1] / 'app/api/v1' / filename
    node = next(n for n in ast.parse(file.read_text(encoding='utf-8')).body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == function)
    if function == 'get_post':
        assignment = next(n for n in node.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'result' for t in n.targets))
        expression = assignment.value.value.args[0]
    else:
        assignment = next(n for n in node.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'query' for t in n.targets))
        expression = assignment.value
    namespace = dict(select=select, func=func, MatchPost=MatchPost, User=User,
                     Club=Club, MatchRegistration=MatchRegistration,
                     current_user=SimpleNamespace(id=1), post_id=2,
                     approved_count=func.sum(case((MatchRegistration.status == 'approved', 1), else_=0)),
                     pending_count=func.sum(case((MatchRegistration.status == 'pending', 1), else_=0)))
    query = eval(compile(ast.Expression(expression), str(file), 'eval'), namespace)
    return query.group_by(MatchPost.id)


class FreePostQueriesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add_all([User(id=1, nickname='Player'), Club(id=1, name='Court'),
                              MatchPost(id=1, user_id=1, club_id=1, created_at=datetime(2026, 1, 1)),
                              MatchPost(id=2, user_id=1, club_id=None, created_at=datetime(2026, 1, 2))])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_public_list_includes_free_post(self):
        rows = self.session.execute(source_query('posts.py', 'list_posts')).all()
        self.assertEqual({row[0].id for row in rows}, {1, 2})

    def test_my_posts_include_free_post(self):
        rows = self.session.execute(source_query('users.py', 'my_posts')).all()
        self.assertEqual({row[0].id for row in rows}, {1, 2})

    def test_free_post_detail_is_not_lost_by_join(self):
        row = self.session.execute(source_query('posts.py', 'get_post')).one()
        self.assertEqual(row[0].id, 2)
        self.assertIsNone(row[0].club_id)


if __name__ == '__main__':
    unittest.main()
