from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.entities import User, UserMovieInteraction


def _reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _register(client: TestClient, email: str, name: str = 'Tester'):
    response = client.post('/api/auth/register', json={'name': name, 'email': email, 'password': 'goodpassword123'})
    assert response.status_code == 201, response.text
    return response.json()['user']['csrf_token']


def test_auth_register_login_logout_and_me():
    _reset()
    with TestClient(app) as client:
        csrf = _register(client, 'one@example.com')
        me = client.get('/api/auth/me')
        assert me.status_code == 200
        assert me.json()['user']['email'] == 'one@example.com'
        logout = client.post('/api/auth/logout', headers={'X-CSRF-Token': csrf})
        assert logout.status_code == 200
        assert client.get('/api/auth/me').status_code == 401
        login = client.post('/api/auth/login', json={'email': 'one@example.com', 'password': 'goodpassword123'})
        assert login.status_code == 200
        assert client.get('/api/auth/me').status_code == 200


def test_duplicate_email_is_rejected():
    _reset()
    with TestClient(app) as client:
        _register(client, 'same@example.com')
        response = client.post('/api/auth/register', json={'name': 'Other', 'email': 'same@example.com', 'password': 'goodpassword123'})
        assert response.status_code == 409


def test_user_imports_are_isolated():
    _reset()
    ratings_a = b'Date,Name,Year,Rating\n2026-01-02,Arrival,2016,5\n'
    ratings_b = b'Date,Name,Year,Rating\n2026-01-02,Shrek,2001,4\n'
    with TestClient(app) as a, TestClient(app) as b:
        csrf_a = _register(a, 'a@example.com', 'A')
        csrf_b = _register(b, 'b@example.com', 'B')
        ra = a.post('/api/import', files=[('files', ('ratings.csv', ratings_a, 'text/csv'))], headers={'X-CSRF-Token': csrf_a})
        rb = b.post('/api/import', files=[('files', ('ratings.csv', ratings_b, 'text/csv'))], headers={'X-CSRF-Token': csrf_b})
        assert ra.status_code == 200, ra.text
        assert rb.status_code == 200, rb.text
        assert a.get('/api/stats').json()['total_watched'] == 1
        assert b.get('/api/stats').json()['total_watched'] == 1
        with SessionLocal() as db:
            users = {u.email: u.id for u in db.scalars(select(User)).all()}
            titles_a = {x.movie.title for x in db.scalars(select(UserMovieInteraction).where(UserMovieInteraction.user_id == users['a@example.com'])).all()}
            titles_b = {x.movie.title for x in db.scalars(select(UserMovieInteraction).where(UserMovieInteraction.user_id == users['b@example.com'])).all()}
            assert titles_a == {'Arrival'}
            assert titles_b == {'Shrek'}


def test_mutations_require_csrf():
    _reset()
    with TestClient(app) as client:
        _register(client, 'csrf@example.com')
        response = client.put('/api/settings', json={'weights': {}})
        assert response.status_code == 403


def test_replace_import_replaces_only_current_users_private_movie_data():
    _reset()
    first = b'Date,Name,Year,Rating\n2026-01-02,Arrival,2016,5\n'
    second = b'Date,Name,Year,Rating\n2026-02-02,Shrek,2001,4\n'
    with TestClient(app) as client:
        csrf = _register(client, 'replace@example.com')
        a = client.post('/api/import', files=[('files', ('ratings.csv', first, 'text/csv'))], headers={'X-CSRF-Token': csrf})
        assert a.status_code == 200
        b = client.post(
            '/api/import',
            data={'mode': 'replace'},
            files=[('files', ('ratings.csv', second, 'text/csv'))],
            headers={'X-CSRF-Token': csrf},
        )
        assert b.status_code == 200, b.text
        assert b.json()['mode'] == 'replace'
        with SessionLocal() as db:
            user_id = db.scalar(select(User.id).where(User.email == 'replace@example.com'))
            titles = {x.movie.title for x in db.scalars(select(UserMovieInteraction).where(UserMovieInteraction.user_id == user_id)).all()}
            assert titles == {'Shrek'}


def test_friend_compare_is_temporary_and_returns_confidence():
    _reset()
    yours = b'Date,Name,Year,Rating\n2026-01-02,Arrival,2016,5\n2026-01-03,Her,2013,4\n'
    friend = b'Date,Name,Year,Rating\n2026-01-02,Arrival,2016,4.5\n2026-01-03,Her,2013,2\n'
    with TestClient(app) as client:
        csrf = _register(client, 'compare@example.com')
        imported = client.post('/api/import', files=[('files', ('ratings.csv', yours, 'text/csv'))], headers={'X-CSRF-Token': csrf})
        assert imported.status_code == 200
        compared = client.post('/api/compare-users', files=[('files', ('ratings.csv', friend, 'text/csv'))], headers={'X-CSRF-Token': csrf})
        assert compared.status_code == 200, compared.text
        payload = compared.json()
        assert payload['shared'] == 2
        assert payload['confidence'] == 'Low'
        assert 0 <= payload['compatibility'] <= 100
        # Only the signed-in user's imported rows exist; friend data was not persisted.
        with SessionLocal() as db:
            assert len(db.scalars(select(UserMovieInteraction)).all()) == 2
