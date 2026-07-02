from datetime import datetime
import re
from os import getenv
from pathlib import Path
from collections import defaultdict
import smtplib
import unicodedata
from email.message import EmailMessage
from smtplib import SMTPAuthenticationError, SMTPConnectError, SMTPException, SMTPNotSupportedError, SMTPServerDisconnected

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["SECRET_KEY"] = getenv("SECRET_KEY", "change-this-secret-key")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_REFRESH_EACH_REQUEST"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
database_url = getenv("DATABASE_URL")
env_name = getenv("FLASK_ENV", getenv("ENV", "development")).lower()
is_production = env_name == "production"
if not database_url:
    if is_production:
        raise RuntimeError("DATABASE_URL is required in production")
    database_url = f"sqlite:///{BASE_DIR / 'relatorios.db'}"
if database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url.removeprefix("postgres://")
elif database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
}

db = SQLAlchemy(app)
reset_serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=True, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="publicador")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    person_key = db.Column(db.String(160), nullable=False, default="")
    author_name = db.Column(db.String(120), nullable=False, default="")
    author_role = db.Column(db.String(20), nullable=False, default="publicador")
    month = db.Column(db.String(20), nullable=False)
    participated = db.Column(db.Boolean, default=False)
    bible_studies = db.Column(db.Integer, default=0)
    hours = db.Column(db.Float, default=0)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("reports", lazy=True))


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if not user:
        session.pop("user_id", None)
    return user


def normalize_name(value):
    text = " ".join(value.strip().split()).lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def display_name(value):
    parts = value.strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}"
    return parts[0] if parts else ""


def person_key(value):
    return normalize_name(display_name(value))


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value):
    return bool(value) and bool(EMAIL_PATTERN.match(value))


def make_reset_token(user_id):
    return reset_serializer.dumps({"user_id": user_id}, salt="password-reset")


def read_reset_token(token, max_age=3600):
    data = reset_serializer.loads(token, salt="password-reset", max_age=max_age)
    return data.get("user_id")


def send_reset_email(user, reset_url):
    smtp_host = getenv("MAIL_HOST", getenv("SMTP_HOST", "")).strip()
    smtp_port = int(getenv("MAIL_PORT", getenv("SMTP_PORT", "587")))
    smtp_user = getenv("MAIL_USERNAME", getenv("SMTP_USER", "")).strip()
    smtp_password = getenv("MAIL_PASSWORD", getenv("SMTP_PASSWORD", "")).strip()
    mail_from = getenv("MAIL_FROM", smtp_user).strip()
    use_tls = getenv("MAIL_USE_TLS", getenv("SMTP_USE_TLS", "true")).lower() == "true"

    if not smtp_host or not smtp_user or not smtp_password or not mail_from:
        raise RuntimeError("Configuração de e-mail incompleta.")

    message = EmailMessage()
    message["Subject"] = "Redefinição de senha"
    message["From"] = mail_from
    message["To"] = user.email
    message.set_content(
        f"Olá, {user.name}.\n\n"
        f"Recebemos uma solicitação para redefinir sua senha.\n"
        f"Acesse o link abaixo para criar uma nova senha:\n\n{reset_url}\n\n"
        f"Se você não pediu isso, ignore esta mensagem."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)


def month_order(month_name):
    months = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    try:
        return months.index(month_name)
    except ValueError:
        return len(months)


def previous_month_name(month_name):
    months = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    try:
        return months[(months.index(month_name) - 1) % len(months)]
    except ValueError:
        return month_name


def is_report_delayed(report):
    if not report or not report.created_at:
        return False
    created_order = report.created_at.month - 1
    report_order = month_order(report.month)
    return created_order > report_order


def init_db():
    try:
        db.create_all()
        inspector = inspect(db.engine)
        report_columns = {column["name"] for column in inspector.get_columns("report")}
        user_columns = {column["name"] for column in inspector.get_columns("user")}

        migration_needed = False
        if "person_key" not in report_columns:
            db.session.execute(text("ALTER TABLE report ADD COLUMN person_key VARCHAR(160) NOT NULL DEFAULT ''"))
            migration_needed = True
        if "author_name" not in report_columns:
            db.session.execute(text("ALTER TABLE report ADD COLUMN author_name VARCHAR(120) NOT NULL DEFAULT ''"))
            migration_needed = True
        if "author_role" not in report_columns:
            db.session.execute(text("ALTER TABLE report ADD COLUMN author_role VARCHAR(20) NOT NULL DEFAULT 'publicador'"))
            migration_needed = True
        if "email" not in user_columns:
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN email VARCHAR(120)"))
            migration_needed = True

        if migration_needed:
            db.session.commit()
            inspector = inspect(db.engine)
            report_columns = {column["name"] for column in inspector.get_columns("report")}
            user_columns = {column["name"] for column in inspector.get_columns("user")}

        if "person_key" in report_columns and "author_name" in report_columns and "author_role" in report_columns:
            orphan_reports = Report.query.filter((Report.author_name == "") | (Report.author_role == "") | (Report.person_key == "")).all()
            if orphan_reports:
                active_users = User.query.all()
                active_by_key = {person_key(item.name): item for item in active_users}
                for report in orphan_reports:
                    source_user = report.user
                    if not source_user and report.author_name:
                        source_user = active_by_key.get(person_key(report.author_name))
                    if source_user:
                        report.author_name = source_user.name
                        report.author_role = source_user.role
                    if not report.person_key:
                        source_name = report.author_name or (source_user.name if source_user else "")
                        if source_name:
                            report.person_key = person_key(source_name)
                db.session.commit()
        manager = User.query.filter_by(role="manager").first()
        if manager and manager.name == "Responsável":
            manager.name = "Secretário da Congregação"
            db.session.commit()
    except Exception:
        db.session.rollback()


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.before_request
def normalize_localhost():
    if is_production:
        return None

    host = request.host.split(":", 1)[0]
    if host == "127.0.0.1":
        target = request.url.replace("//127.0.0.1", "//localhost", 1)
        return redirect(target, code=302)


@app.route("/")
def index():
    user = current_user()
    months = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    current_month_index = datetime.now().month - 1
    previous_month_index = (current_month_index - 1) % 12
    selected_month = request.args.get("month", months[previous_month_index])
    report_loaded = request.args.get("submitted") == "1"
    report = None
    inbox_groups = []
    users_list = []
    can_create_manager = User.query.filter_by(role="manager").first() is None

    if user:
        stable_key = person_key(user.name)
        if report_loaded:
            report = (
                Report.query.filter(
                    (Report.user_id == user.id) | (Report.person_key == stable_key) | (Report.person_key == normalize_name(user.name)),
                    Report.month == selected_month,
                )
                .order_by(Report.created_at.desc())
                .first()
            )
            if report:
                report.is_delayed = is_report_delayed(report)
        if user.role == "manager":
            users_list = User.query.order_by(User.role.asc(), User.name.asc()).all()
            reports = Report.query.order_by(Report.created_at.desc()).all()
            grouped = defaultdict(list)
            active_person_keys = {person_key(item.name) for item in User.query.all()}
            for item in reports:
                label = item.author_name or (item.user.name if item.user else "Conta excluída")
                item.is_active = (item.person_key or normalize_name(label)) in active_person_keys
                item.is_delayed = is_report_delayed(item)
                item.display_month = previous_month_name(item.month)
                grouped[item.person_key or normalize_name(label)].append(item)
            inbox_groups = [
                {
                    "user": items[0].author_name or (items[0].user.name if items[0].user else "Conta excluída"),
                    "reports": sorted(items, key=lambda r: (month_order(r.month), r.created_at or datetime.min)),
                }
                for _, items in sorted(
                    grouped.items(),
                    key=lambda pair: (pair[1][0].author_name or pair[0]).lower(),
                )
            ]

    return render_template(
        "index.html",
        user=user,
        months=months,
        selected_month=selected_month,
        selected_work_month=previous_month_name(selected_month),
        report=report,
        inbox_groups=inbox_groups,
        users_list=users_list,
        active_person_keys=active_person_keys if user and user.role == "manager" else set(),
        can_create_manager=can_create_manager,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    can_create_manager = User.query.filter_by(role="manager").first() is None

    if request.method == "GET":
        return render_template(
            "register.html",
            user=current_user(),
            can_create_manager=can_create_manager,
        )

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "publicador")

    if not name:
        flash("Preencha o nome para criar a conta.")
        return redirect(url_for("register"))
    if not email:
        flash("Preencha o e-mail para criar a conta.")
        return redirect(url_for("register"))
    if not is_valid_email(email):
        flash("Digite um e-mail válido para criar a conta.")
        return redirect(url_for("register"))
    if not password:
        flash("Preencha a senha para criar a conta.")
        return redirect(url_for("register"))
    if len(password) < 6:
        flash("A senha deve ter no mínimo 6 dígitos.")
        return redirect(url_for("register"))

    normalized_name = normalize_name(name)
    name_parts = name.split()
    if len(name_parts) < 2:
        flash("Digite primeiro nome e sobrenome para continuar.")
        return redirect(url_for("register"))

    name = display_name(name)

    if any(normalize_name(user.name) == normalized_name for user in User.query.all()):
        flash("Já existe uma conta com esse nome.")
        return redirect(url_for("register"))
    if User.query.filter_by(email=email).first():
        flash("Já existe uma conta com esse e-mail.")
        return redirect(url_for("register"))

    if role == "manager" and User.query.filter_by(role="manager").first():
        flash("Já existe uma conta de Secretário da Congregação. Não é possível criar outra enquanto esta estiver ativa.")
        return redirect(url_for("register"))

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    session.permanent = False
    session["user_id"] = user.id
    session.modified = True
    flash("Conta criada com sucesso.")
    return redirect(url_for("index"))


@app.route("/login", methods=["POST"])
def login():
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")

    if not name:
        flash("Preencha o nome para entrar.")
        return redirect(url_for("index"))
    if not password:
        flash("Preencha a senha para entrar.")
        return redirect(url_for("index"))
    if len(password) < 6:
        flash("A senha deve ter no mínimo 6 dígitos.")
        return redirect(url_for("index"))

    normalized_name = normalize_name(name)
    user = next((item for item in User.query.all() if normalize_name(item.name) == normalized_name), None)

    if not user or not user.check_password(password):
        flash("Conta não encontrada ou senha incorreta.")
        return redirect(url_for("index"))

    session.permanent = False
    session["user_id"] = user.id
    session.modified = True
    flash("Login realizado.")
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("Preencha o e-mail para receber o link de redefinição.")
        return redirect(url_for("index"))
    if not is_valid_email(email):
        flash("Digite um e-mail válido para continuar.")
        return redirect(url_for("index"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Não encontramos nenhuma conta com esse e-mail.")
        return redirect(url_for("index"))

    token = make_reset_token(user.id)
    reset_url = url_for("reset_password", token=token, _external=True)
    try:
        send_reset_email(user, reset_url)
        flash("Enviamos um link de redefinição para o seu e-mail.")
    except SMTPAuthenticationError as exc:
        print(f"SMTP authentication error: {exc!r}")
        flash("Falha de autenticação no SMTP. Verifique o e-mail e a senha de app.")
    except SMTPNotSupportedError as exc:
        print(f"SMTP TLS/feature not supported: {exc!r}")
        flash("O servidor SMTP não aceitou o modo TLS configurado.")
    except SMTPConnectError as exc:
        print(f"SMTP connection error: {exc!r}")
        flash("Não foi possível conectar ao servidor SMTP. Verifique o host e a porta.")
    except SMTPServerDisconnected as exc:
        print(f"SMTP disconnected: {exc!r}")
        flash("O servidor SMTP encerrou a conexão. Verifique a configuração do provedor.")
    except SMTPException as exc:
        print(f"SMTP error: {exc!r}")
        flash("Não foi possível enviar o e-mail de redefinição. Verifique a configuração do SMTP.")
    except Exception as exc:
        print(f"Unexpected email error: {exc!r}")
        flash("Não foi possível enviar o e-mail de redefinição. Verifique a configuração do SMTP.")
    return redirect(url_for("index"))


@app.route("/admin-reset-password", methods=["POST"])
def admin_reset_password():
    user = current_user()
    if not user or user.role != "manager":
        flash("Faça login como Secretário da Congregação para redefinir senha.")
        return redirect(url_for("index"))

    target_user_id = request.form.get("user_id", type=int)
    new_password = request.form.get("password", "").strip()
    if not target_user_id or not new_password:
        flash("Selecione o usuário e digite a nova senha.")
        return redirect(url_for("index"))

    target_user = db.session.get(User, target_user_id)
    if not target_user:
        flash("Usuário não encontrado.")
        return redirect(url_for("index"))

    if target_user.role == "manager" and target_user.id != user.id:
        flash("Não é possível redefinir a senha do Secretário da Congregação por este formulário.")
        return redirect(url_for("index"))

    target_user.set_password(new_password)
    db.session.commit()
    flash(f"Senha redefinida para {target_user.name}.")
    return redirect(url_for("index"))


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        user_id = read_reset_token(token)
    except SignatureExpired:
        flash("O link de redefinição expirou. Solicite um novo.")
        return redirect(url_for("index"))
    except BadSignature:
        flash("Link de redefinição inválido.")
        return redirect(url_for("index"))

    user = db.session.get(User, user_id)
    if not user:
        flash("Usuário não encontrado para essa redefinição.")
        return redirect(url_for("index"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if not password:
            flash("Digite uma nova senha.")
            return redirect(url_for("reset_password", token=token))
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash("Senha atualizada com sucesso.")
        return redirect(url_for("index"))

    return render_template("reset_password.html", token=token, user=user)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Saiu da conta.")
    return redirect(url_for("index"))


@app.route("/delete-account", methods=["POST"])
def delete_account():
    session_user_id = session.get("user_id")
    form_user_id = request.form.get("user_id", type=int)
    user_id = session_user_id or form_user_id

    if not user_id:
        flash("Faça login novamente como Secretário da Congregação para excluir a conta.")
        return redirect(url_for("index"))

    user = db.session.get(User, user_id)
    if not user:
        session.pop("user_id", None)
        flash("Sua sessão expirou. Faça login novamente como Secretário da Congregação.")
        return redirect(url_for("index"))

    if session_user_id and form_user_id and session_user_id != form_user_id:
        flash("A conta logada não confere com a conta solicitada para exclusão.")
        return redirect(url_for("index"))

    user_name = user.name
    db.session.query(Report).filter_by(user_id=user_id).update(
        {"author_name": user_name, "user_id": None},
        synchronize_session=False,
    )
    db.session.delete(user)
    db.session.commit()
    session.pop("user_id", None)
    flash(f"Sua conta de {user_name} foi excluída.")
    return redirect(url_for("index"))


@app.route("/whoami")
def whoami():
    user = current_user()
    if not user:
        return {"logged_in": False, "user": None}
    return {"logged_in": True, "user": {"id": user.id, "name": user.name, "role": user.role}}


@app.route("/save-report", methods=["POST"])
def save_report():
    session_user_id = session.get("user_id")
    form_user_id = request.form.get("user_id", type=int)
    user_id = session_user_id or form_user_id

    if not user_id:
        flash("Faça login para salvar o relatório.")
        return redirect(url_for("index"))

    user = db.session.get(User, user_id)
    if not user:
        session.pop("user_id", None)
        flash("Sua sessão expirou. Faça login novamente para salvar o relatório.")
        return redirect(url_for("index"))

    if session_user_id and form_user_id and session_user_id != form_user_id:
        flash("A conta logada não confere com o relatório enviado.")
        return redirect(url_for("index"))

    session["user_id"] = user.id
    session.permanent = False
    session.modified = True

    month = request.form.get("month", "").strip()
    participated = request.form.get("participated") == "on"
    bible_studies_raw = request.form.get("bible_studies", "").strip()
    bible_studies = int(bible_studies_raw) if bible_studies_raw else 0
    hours_raw = request.form.get("hours", "").strip()
    hours = float(hours_raw) if hours_raw else 0
    notes = request.form.get("notes", "").strip()

    report = Report.query.filter_by(user_id=user.id, month=month).first()
    if not report:
        report = Report.query.filter_by(person_key=person_key(user.name), month=month).first()
    if not report:
        report = Report.query.filter_by(person_key=normalize_name(user.name), month=month).first()
    if not report:
        report = Report.query.filter_by(author_name=user.name, month=month).first()
    if report:
        flash("Já existe um relatório salvo para este mês. Só é permitido enviar um relatório por mês.")
        return redirect(url_for("index", month=month))

    report = Report(user_id=user.id, month=month)
    report.person_key = person_key(user.name)
    report.author_name = user.name
    report.author_role = user.role
    db.session.add(report)

    report.participated = participated
    report.bible_studies = bible_studies
    report.hours = hours
    report.notes = notes
    report.created_at = datetime.utcnow()
    db.session.commit()

    flash("Relatório salvo com sucesso.")
    return redirect(url_for("index", month=month, submitted=1))


@app.route("/manifest.webmanifest")
def manifest():
    return app.send_static_file("manifest.webmanifest")


@app.route("/sw.js")
def service_worker():
    response = app.send_static_file("sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.cli.command("init-db")
def init_db_command():
    """Initialize the database for a fresh deployment."""
    with app.app_context():
        init_db()
    print("Database initialized.")


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=(env_name != "production" and getenv("FLASK_DEBUG") == "1"))
