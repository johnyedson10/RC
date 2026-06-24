from datetime import datetime
from os import getenv
from pathlib import Path
from collections import defaultdict
import unicodedata

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
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


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
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


def month_order(month_name):
    months = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    try:
        return months.index(month_name)
    except ValueError:
        return len(months)


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
        if "person_key" not in report_columns:
            db.session.execute(text("ALTER TABLE report ADD COLUMN person_key VARCHAR(160) NOT NULL DEFAULT ''"))
            db.session.commit()
        if "author_name" not in report_columns:
            db.session.execute(text("ALTER TABLE report ADD COLUMN author_name VARCHAR(120) NOT NULL DEFAULT ''"))
            db.session.commit()
        if "author_role" not in report_columns:
            db.session.execute(text("ALTER TABLE report ADD COLUMN author_role VARCHAR(20) NOT NULL DEFAULT 'publicador'"))
            db.session.commit()
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
    selected_month = request.args.get("month", months[datetime.now().month - 1])
    report = None
    inbox_groups = []
    can_create_manager = User.query.filter_by(role="manager").first() is None

    if user:
        stable_key = person_key(user.name)
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
            reports = Report.query.order_by(Report.created_at.desc()).all()
            grouped = defaultdict(list)
            active_person_keys = {person_key(item.name) for item in User.query.all()}
            for item in reports:
                label = item.author_name or (item.user.name if item.user else "Conta excluída")
                item.is_active = (item.person_key or normalize_name(label)) in active_person_keys
                item.is_delayed = is_report_delayed(item)
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
        report=report,
        inbox_groups=inbox_groups,
        active_person_keys=active_person_keys if user and user.role == "manager" else set(),
        can_create_manager=can_create_manager,
    )


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "publicador")

    if not name or not password:
        flash("Preencha nome e senha.")
        return redirect(url_for("index"))

    normalized_name = normalize_name(name)
    name_parts = name.split()
    if len(name_parts) < 2:
        flash("Digite primeiro nome e sobrenome para continuar.")
        return redirect(url_for("index"))

    name = display_name(name)

    if any(normalize_name(user.name) == normalized_name for user in User.query.all()):
        flash("Já existe uma conta com esse nome.")
        return redirect(url_for("index"))

    if role == "manager" and User.query.filter_by(role="manager").first():
        flash("Já existe uma conta de Secretário da Congregação. Não é possível criar outra enquanto esta estiver ativa.")
        return redirect(url_for("index"))

    user = User(name=name, role=role)
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
    return redirect(url_for("index", month=month))


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
