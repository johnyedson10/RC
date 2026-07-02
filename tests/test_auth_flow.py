from __future__ import annotations

import html
import json
import re
from urllib.parse import urlparse


def get_flash_messages(response):
    body = response.get_data(as_text=True)
    match = re.search(r'<script id="flash-data" type="application/json">(.*?)</script>', body, re.S)
    assert match, "flash-data script not found in response"
    return json.loads(html.unescape(match.group(1)))


def create_user(app_api, name="Maria Silva", email="maria@example.com", password="Senha123!"):
    with app_api.app.app_context():
        user = app_api.User(name=name, email=email, role="publicador")
        user.set_password(password)
        app_api.db.session.add(user)
        app_api.db.session.commit()
        return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


def test_index_shows_forgot_password_message(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Esqueceu a senha? Use o e-mail cadastrado para receber o link de acesso." in response.get_data(as_text=True)
    assert "Criar conta" in response.get_data(as_text=True)


def test_register_page_is_separate_from_login_page(client):
    response = client.get("/register")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Cadastro" in body
    assert "Voltar ao login" in body


def test_registration_validates_required_fields_and_duplicates(client):
    response = client.post(
        "/register",
        data={"name": "", "email": "a@example.com", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Preencha o nome para criar a conta." in get_flash_messages(response)

    response = client.post(
        "/register",
        data={"name": "Maria", "email": "a@example.com", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Digite primeiro nome e sobrenome para continuar." in get_flash_messages(response)

    response = client.post(
        "/register",
        data={"name": "Maria Silva", "email": "", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Preencha o e-mail para criar a conta." in get_flash_messages(response)

    response = client.post(
        "/register",
        data={"name": "Maria Silva", "email": "maria@example.com", "password": ""},
        follow_redirects=True,
    )
    assert "Preencha a senha para criar a conta." in get_flash_messages(response)

    response = client.post(
        "/register",
        data={"name": "Maria Silva", "email": "maria@example.com", "password": "12345"},
        follow_redirects=True,
    )
    assert "A senha deve ter no mínimo 6 dígitos." in get_flash_messages(response)

    response = client.post(
        "/register",
        data={"name": "Maria Silva", "email": "maria@example.com", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Conta criada com sucesso." in get_flash_messages(response)

    response = client.post(
        "/register",
        data={"name": "maria silva", "email": "outra@example.com", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Já existe uma conta com esse nome." in get_flash_messages(response)

    response = client.post(
        "/register",
        data={"name": "Outra Pessoa", "email": "maria@example.com", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Já existe uma conta com esse e-mail." in get_flash_messages(response)


def test_login_accepts_correct_credentials_and_rejects_invalid_password(client, app_api):
    create_user(app_api)

    response = client.post(
        "/login",
        data={"name": "", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Preencha o nome para entrar." in get_flash_messages(response)

    response = client.post(
        "/login",
        data={"name": "Maria Silva", "password": ""},
        follow_redirects=True,
    )
    assert "Preencha a senha para entrar." in get_flash_messages(response)

    response = client.post(
        "/login",
        data={"name": "Maria Silva", "password": "12345"},
        follow_redirects=True,
    )
    assert "A senha deve ter no mínimo 6 dígitos." in get_flash_messages(response)

    response = client.post(
        "/login",
        data={"name": "Maria Silva", "password": "Senha123!"},
        follow_redirects=True,
    )
    assert "Login realizado." in get_flash_messages(response)

    whoami = client.get("/whoami")
    assert whoami.get_json() == {"logged_in": True, "user": {"id": 1, "name": "Maria Silva", "role": "publicador"}}

    response = client.post(
        "/login",
        data={"name": "Maria Silva", "password": "senha-errada"},
        follow_redirects=True,
    )
    assert "Conta não encontrada ou senha incorreta." in get_flash_messages(response)


def test_forgot_password_generates_reset_link_for_registered_email(client, app_api, monkeypatch):
    user = create_user(app_api)
    captured = {}

    def fake_send_reset_email(target_user, reset_url):
        captured["user"] = target_user
        captured["reset_url"] = reset_url

    monkeypatch.setattr(app_api, "send_reset_email", fake_send_reset_email)

    response = client.post(
        "/forgot-password",
        data={"email": user["email"]},
        follow_redirects=True,
    )
    assert "Enviamos um link de redefinição para o seu e-mail." in get_flash_messages(response)
    assert captured["user"].email == user["email"]
    assert "/reset-password/" in captured["reset_url"]

    token = urlparse(captured["reset_url"]).path.rsplit("/reset-password/", 1)[-1]
    response = client.get(f"/reset-password/{token}")
    assert response.status_code == 200
    assert "Definir nova senha" in response.get_data(as_text=True)


def test_forgot_password_shows_smtp_auth_error(client, app_api, monkeypatch):
    user = create_user(app_api)

    def fake_send_reset_email(*_args, **_kwargs):
        raise app_api.SMTPAuthenticationError(535, b"Authentication failed")

    monkeypatch.setattr(app_api, "send_reset_email", fake_send_reset_email)

    response = client.post(
        "/forgot-password",
        data={"email": user["email"]},
        follow_redirects=True,
    )
    assert "Falha de autenticação no SMTP. Verifique o e-mail e a senha de app." in get_flash_messages(response)


def test_forgot_password_validates_email_field_and_missing_account(client):
    response = client.post(
        "/forgot-password",
        data={"email": ""},
        follow_redirects=True,
    )
    assert "Preencha o e-mail para receber o link de redefinição." in get_flash_messages(response)

    response = client.post(
        "/forgot-password",
        data={"email": "email-invalido"},
        follow_redirects=True,
    )
    assert "Digite um e-mail válido para continuar." in get_flash_messages(response)

    response = client.post(
        "/forgot-password",
        data={"email": "naoexiste@example.com"},
        follow_redirects=True,
    )
    assert "Não encontramos nenhuma conta com esse e-mail." in get_flash_messages(response)


def test_reset_password_updates_login_password(client, app_api, monkeypatch):
    user = create_user(app_api, password="Senha123!")

    monkeypatch.setattr(app_api, "send_reset_email", lambda *_args, **_kwargs: None)
    response = client.post("/forgot-password", data={"email": user["email"]}, follow_redirects=True)
    assert "Enviamos um link de redefinição para o seu e-mail." in get_flash_messages(response)

    token = app_api.make_reset_token(user["id"])
    response = client.post(
        f"/reset-password/{token}",
        data={"password": "NovaSenha123!"},
        follow_redirects=True,
    )
    assert "Senha atualizada com sucesso." in get_flash_messages(response)

    response = client.post(
        "/login",
        data={"name": "Maria Silva", "password": "NovaSenha123!"},
        follow_redirects=True,
    )
    assert "Login realizado." in response.get_data(as_text=True)


def test_reset_password_rejects_invalid_token(client):
    response = client.get("/reset-password/token-invalido", follow_redirects=True)
    assert "Link de redefinição inválido." in get_flash_messages(response)
