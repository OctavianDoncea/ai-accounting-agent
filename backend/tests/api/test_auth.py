import pytest
from app.config import settings
from app.services.auth_service import authenticate_user, create_access_token, create_user, decode_access_token, hash_password, verify_password, AuthError

@pytest.fixture
def auth_enabled():
    settings.jwt_secret = 'test-signing-secret'
    yield 'test-signing-secret'
    settings.jwt_secret = ''

class TestPasswordHashing:
    def test_hash_is_not_the_plaintext(self):
        h = hash_password('mypasssword123')
        assert h != 'mypasssword123'

    def test_correct_password_verifies(self):
        h = hash_password('mypasssword123')
        assert verify_password('mypasssword123', h) is True

    def test_wrong_password_fails(self):
        h = hash_password('mypasssword123')
        assert verify_password('wrongpassword', h) is False

    def test_same_password_hashes_differently_each_time(self):
        h1 = hash_password('mypasssword123')
        h2 = hash_password('mypasssword123')
        assert h1 != h2
        assert verify_password('mypasssword123', h1)
        assert verify_password('mypasssword123', h2)


class TestCreateUser:
    def test_creates_a_user(self, db):
        user = create_user(db, 'person@example.com', 'password123')
        assert user.email == 'person@example.com'
        assert user.password_hash != 'password123'

    def test_email_is_lowercased_and_stripped(self, db):
        user = create_user(db, ' Person@Example.com ', 'password123')
        assert user.email == 'person@example.com'

    def test_duplicate_email_rejected(self, db):
        create_user(db, 'person@example.com', 'password123')
        with pytest.raises(AuthError, match='already exists'):
            create_user(db, 'person@example.com', 'different456')

    def test_duplicate_email_case_insensitive(self, db):
        create_user(db, 'person@example.com', 'password123')
        with pytest.raises(AuthError):
            create_user(db, 'PERSON@EXAMPLE.COM', 'different456')


class TestAuthenticateUser:
    def test_correct_credentials(self, db):
        create_user(db, 'person@example.com', 'password123')
        user = authenticate_user(db, 'person@example.com', 'password123')
        assert user.email == 'person@example.com'

    def test_wrong_password(self, db):
        create_user(db, 'person@example.com', 'password123')
        with pytest.raises(AuthError, match='Incorrect'):
            authenticate_user(db, 'person@example.com', 'wrongpassword')

    def test_nonexistent_email(self, db):
        with pytest.raises(AuthError, match='Incorrect'):
            authenticate_user(db, 'nonexistent@example.com', 'whatever123')

    def test_same_error_for_wrong_password_and_missing_user(self, db):
        create_user(db, 'person@example.com', 'password123')
        try:
            authenticate_user(db, 'person@example.com', 'wrongpassword')
            assert False
        except AuthError as e1:
            msg1 = str(e1)
        try:
            authenticate_user(db, 'nonexistent@example.com', 'whatever123')
            assert False
        except AuthError as e2:
            msg2 = str(e2)
        assert msg1 == msg2


class TestTokens:
    def test_creates_and_decode_round_trip(self, db, auth_enabled):
        user = create_user(db, 'person@example.com', 'password123')
        token = create_access_token(user)
        payload = decode_access_token(token)
        assert payload['email'] == 'person@example.com'
        assert payload['sub'] == str(user.id)

    def test_tampered_token_fails_to_decode(self, db, auth_enabled):
        user = create_user(db, 'person@example.com', 'password123')
        token = create_access_token(user)
        tampered = token[:-4] + 'xxxx'
        import jwt as pyjwt
        with pytest.raises(pyjwt.PyJWTError):
            decode_access_token(tampered)

    def test_token_signed_with_different_secret_is_rejected(self, db, auth_enabled):
        user = create_user(db, 'person@example.com', 'password123')
        token = create_access_token(user)
        settings.jwt_secret = 'different-secret'
        import jwt as pyjwt
        with pytest.raises(pyjwt.PyJWTError):
            decode_access_token(token)


class TestSignupAPI:
    def test_signup_returns_token(self, client, auth_enabled):
        r = client.post('/auth/signup', json={'email': 'new@example.com', 'password': 'password123'})
        assert r.status_code == 201
        body = r.json()
        assert body['email'] == 'new@example.com'
        assert body['token_type'] == 'bearer'
        assert len(body['access_token']) > 20

    def test_deuplicate_signup_rejected(self, client, auth_enabled):
        client.post('/auth/signup', json={'email': 'dup@example.com', 'password': 'password123'})
        r = client.post('/auth/signup', json={'email': 'dup@example.com', 'password': 'different456'})
        assert r.status_code == 409

    def test_short_password_rejected(self, client, auth_enabled):
        r = client.post('/auth/signup', json={'email': 'short@example.com', 'password': 'abc'})
        assert r.status_code == 422

    def test_invalid_email_rejected(self, client, auth_enabled):
        r = client.post('/auth/signup', json={'email': 'invalid-email', 'password': 'password123'})
        assert r.status_code == 422

    def test_signup_works_even_when_auth_disabled(self, client):
        assert settings.jwt_secret == ''
        r = client.post('/auth/signup', json={'email': 'predisabled@example.com', 'password': 'password123'})
        assert r.status_code == 201


class TestLoginAPI:
    def test_login_with_correct_password(self, client, auth_enabled):
        client.post('/auth/signup', json={'email': 'person@example.com', 'password': 'password123'})
        r = client.post('/auth/login', json={'email': 'person@example.com', 'password': 'password123'})
        assert r.status_code == 200
        assert r.json()['email'] == 'person@example.com'

    def test_login_with_wrong_password(self, client, auth_enabled):
        client.post('/auth/signup', json={'email': 'person@example.com', 'password': 'password123'})
        r = client.post('/auth/login', json={'email': 'person@example.com', 'password': 'wrongpassword'})
        assert r.status_code == 401

    def test_login_nonexistent_account(self, client, auth_enabled):
        r = client.post('/auth/login', json={'email': 'nonexistent@example.com', 'password': 'whatever123'})
        assert r.status_code == 401


class TestMeAPI:
    def test_me_with_valid_tokens(self, client, auth_enabled):
        signup = client.post('/auth/signup', json={'email': 'person@example.com', 'password': 'password123'})
        token = signup.json()['access_token']
        r = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
        assert r.status_code == 200
        assert r.json()['email'] == 'person@example.com'

    def test_me_without_token(self, client, auth_enabled):
        r = client.get('/auth/me')
        assert r.status_code == 401

    def test_me_when_auth_disabled(self, client):
        assert settings.jwt_secret == ''
        r = client.get('/auth/me')
        assert r.status_code == 400


class TestAuthGate:
    def test_disabled_by_default_allows_everything(self, client):
        assert settings.jwt_secret == ''
        r = client.get('/chart-of-accounts')
        assert r.status_code == 200

    def test_enabled_blocks_without_token(self, client, auth_enabled):
        r = client.get('/chart-of-accounts')
        assert r.status_code == 401

    def test_enabled_allows_with_valid_token(self, client, auth_enabled):
        signup = client.post('/auth/signup', json={'email': 'gated@example.com', 'password': 'password123'})
        token = signup.json()['access_token']
        r = client.get('/chart-of-accounts', headers={'Authorization': f'Bearer {token}'})
        assert r.status_code == 200

    def test_health_open_regardless(self, client, auth_enabled):
        r = client.get('/health')
        assert r.status_code == 200

    def test_health_reports_auth_enabled_flag(self, client, auth_enabled):
        assert client.get('/health').json()['auth_enabled'] is True

    def test_health_reports_auth_disabled_flag(self, client):
        assert settings.jwt_secret == ''
        assert client.get('/health').json()['auth_enabled'] is False

    def test_post_endpoints_gated_too(self, client, auth_enabled):
        r = client.post('/invoices/upload', files={'file': ('x.pdf', b'data', 'application/pdf')})
        assert r.status_code == 401

    def test_signup_and_login_stay_open_even_when_gate_is_on(self, client, auth_enabled):
        r = client.post('/auth/signup', json={'email': 'boot@example.com', 'password': 'password123'})
        assert r.status_code == 201
        r = client.post('/auth/login', json={'email': 'boot@example.com', 'password': 'password123'})
        assert r.status_code == 200