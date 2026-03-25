from __future__ import annotations

import os
import importlib
import smtplib
import threading
import string
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, case, func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

dotenv_spec = importlib.util.find_spec("dotenv")
if dotenv_spec:
    dotenv_module = importlib.import_module("dotenv")
    dotenv_module.load_dotenv(override=True)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")


def resolve_database_uri() -> str:
    """Resolve a URI do banco para produção/local com fallback seguro."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        # Render pode fornecer URL legada com postgres://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return database_url
    return f"sqlite:///{DB_PATH}"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = resolve_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)

MODALIDADES_VALIDAS = {"Volei", "Natacao", "Funcional"}


class Aula(db.Model):
    __tablename__ = "aulas"

    id = db.Column(db.Integer, primary_key=True)
    modalidade = db.Column(db.String(30), nullable=False)
    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.Time, nullable=False)
    vagas_totais = db.Column(db.Integer, nullable=False)
    plano_aula = db.Column(db.Text, nullable=False)
    equipamentos_necessarios = db.Column(db.Text, nullable=False)

    checkins = db.relationship("Checkin", back_populates="aula", cascade="all, delete-orphan")


class Aluno(db.Model):
    __tablename__ = "alunos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    aprovado = db.Column(db.Boolean, default=False, nullable=False)

    checkins = db.relationship("Checkin", back_populates="aluno", cascade="all, delete-orphan")


class Checkin(db.Model):
    __tablename__ = "checkins"
    __table_args__ = (UniqueConstraint("aluno_id", "aula_id", name="uq_checkin_aluno_aula"),)

    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    aula_id = db.Column(db.Integer, db.ForeignKey("aulas.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    compareceu = db.Column(db.Boolean, nullable=True)
    pontos_recebidos = db.Column(db.Integer, default=0, nullable=False)

    aluno = db.relationship("Aluno", back_populates="checkins")
    aula = db.relationship("Aula", back_populates="checkins")


class RequisicaoResetSenha(db.Model):
    __tablename__ = "requisicoes_reset_senha"

    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    email_solicitante = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default="pendente", nullable=False)  # pendente, aprovado, rejeitado
    criada_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    nova_senha = db.Column(db.String(255), nullable=True)

    aluno = db.relationship("Aluno")


def current_user() -> Aluno | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return Aluno.query.get(user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Faça login para continuar.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user.is_admin:
            flash("Acesso restrito ao painel administrativo.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "Não autenticado."}), 401
        return view(*args, **kwargs)

    return wrapped


def seed_admin_user() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@prosaude.local").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

    existing_admin = Aluno.query.filter_by(email=admin_email).first()
    if existing_admin:
        if not existing_admin.is_admin:
            existing_admin.is_admin = True
            db.session.commit()
        return

    admin = Aluno(
        nome="Instrutora",
        email=admin_email,
        senha_hash=generate_password_hash(admin_password),
        is_admin=True,
        aprovado=True,
    )
    db.session.add(admin)
    db.session.commit()


def migrate_database() -> None:
    """Adiciona colunas novas sem recriar o banco."""
    if db.engine.dialect.name != "sqlite":
        # PRAGMA é específico do SQLite; em Postgres o schema é criado por create_all.
        return

    with db.engine.connect() as conn:
        result = conn.execute(db.text("PRAGMA table_info(alunos)"))
        columns = [row[1] for row in result.fetchall()]
        if "aprovado" not in columns:
            conn.execute(db.text("ALTER TABLE alunos ADD COLUMN aprovado BOOLEAN NOT NULL DEFAULT 0"))
            conn.execute(db.text("UPDATE alunos SET aprovado = 1 WHERE is_admin = 1"))

        checkin_result = conn.execute(db.text("PRAGMA table_info(checkins)"))
        checkin_columns = [row[1] for row in checkin_result.fetchall()]
        if "compareceu" not in checkin_columns:
            conn.execute(db.text("ALTER TABLE checkins ADD COLUMN compareceu BOOLEAN"))
        if "pontos_recebidos" not in checkin_columns:
            conn.execute(db.text("ALTER TABLE checkins ADD COLUMN pontos_recebidos INTEGER NOT NULL DEFAULT 0"))

        conn.commit()


def montar_ranking_alunos() -> list[dict]:
    ranking_rows = (
        db.session.query(
            Aluno.id.label("aluno_id"),
            Aluno.nome.label("nome"),
            Aluno.email.label("email"),
            func.coalesce(func.sum(Checkin.pontos_recebidos), 0).label("pontos"),
            func.coalesce(func.sum(case((Checkin.compareceu.is_(True), 1), else_=0)), 0).label("presencas"),
            func.count(Checkin.id).label("checkins"),
        )
        .outerjoin(Checkin, Checkin.aluno_id == Aluno.id)
        .filter(Aluno.aprovado.is_(True), Aluno.is_admin.is_(False))
        .group_by(Aluno.id)
        .all()
    )

    ranking = [
        {
            "aluno_id": row.aluno_id,
            "nome": row.nome,
            "email": row.email,
            "pontos": int(row.pontos or 0),
            "presencas": int(row.presencas or 0),
            "checkins": int(row.checkins or 0),
        }
        for row in ranking_rows
    ]

    ranking.sort(key=lambda item: (-item["pontos"], -item["presencas"], item["nome"].lower()))

    for idx, item in enumerate(ranking, start=1):
        item["posicao"] = idx

    return ranking


def enviar_email_aprovacao(nome: str, email_destino: str) -> None:
    """Envia e-mail de boas-vindas ao aluno aprovado. Falha silenciosa se SMTP não configurado."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Cadastro aprovado - Pro Saúde"
    msg["From"] = smtp_from
    msg["To"] = email_destino

    corpo_texto = f"Olá {nome},\n\nSeu cadastro no Pro Saúde foi aprovado!\nAgora você já pode fazer login e confirmar presença nas aulas.\n\nBem-vindo(a)!\nEquipe Pro Saúde"
    corpo_html = f"""
    <html><body style="font-family:sans-serif;color:#1f2937;">
      <div style="max-width:480px;margin:auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="color:#f47821;">Cadastro Aprovado!</h2>
        <p>Olá, <strong>{nome}</strong>!</p>
        <p>Seu cadastro no <strong>Pro Saúde</strong> foi aprovado pelo administrador.</p>
        <p>Agora você já pode fazer login e confirmar presença nas aulas.</p>
        <br>
        <p style="color:#6b7280;font-size:13px;">Equipe Pro Saúde</p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    def _enviar():
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
                servidor.ehlo()
                servidor.starttls()
                servidor.login(smtp_user, smtp_password)
                servidor.sendmail(smtp_user, [email_destino], msg.as_string())
        except Exception:
            pass

    threading.Thread(target=_enviar, daemon=True).start()


def notificar_admin_novo_aluno(nome: str, email_aluno: str) -> None:
    """Notifica admin quando um novo aluno se cadastra."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)
    admin_email = os.getenv("ADMIN_EMAIL", "admin@prosaude.local").strip()

    if not smtp_host or not smtp_user or not smtp_password:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Novo aluno aguardando aprovação - {nome}"
    msg["From"] = smtp_from
    msg["To"] = admin_email

    corpo_texto = f"Um novo aluno se cadastrou:\n\nNome: {nome}\nEmail: {email_aluno}\n\nAcesse o painel admin para aprovar ou rejeitar."
    corpo_html = f"""
    <html><body style="font-family:sans-serif;color:#1f2937;">
      <div style="max-width:480px;margin:auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="color:#f47821;">Novo Aluno Cadastrado</h2>
        <p><strong>{nome}</strong> se cadastrou e aguarda ser aprovado.</p>
        <p><strong>Email:</strong> {email_aluno}</p>
        <p>Acesse o painel admin para aprovar ou rejeitar o cadastro.</p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    def _enviar():
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
                servidor.ehlo()
                servidor.starttls()
                servidor.login(smtp_user, smtp_password)
                servidor.sendmail(smtp_user, [admin_email], msg.as_string())
        except Exception:
            pass

    threading.Thread(target=_enviar, daemon=True).start()


def enviar_confirmacao_cadastro(nome: str, email_aluno: str) -> None:
    """Envia email de confirmação ao aluno quando ele se cadastra."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Cadastro recebido - Pro Saúde"
    msg["From"] = smtp_from
    msg["To"] = email_aluno

    corpo_texto = f"Olá {nome},\n\nSeu cadastro foi recebido com sucesso!\n\nAguarde a aprovação do nosso administrador para acessar o sistema.\nEm breve você receberá um email de confirmação.\n\nObrigado!\nEquipe Pro Saúde"
    corpo_html = f"""
    <html><body style="font-family:sans-serif;color:#1f2937;">
      <div style="max-width:480px;margin:auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="color:#f47821;">Cadastro Recebido!</h2>
        <p>Olá, <strong>{nome}</strong>!</p>
        <p>Seu cadastro foi recebido com sucesso na <strong>Pro Saúde</strong>.</p>
        <p>Nosso(a) administrador(a) analisará seu perfil em breve.</p>
        <p style="background:#f3f4f6;padding:12px;border-radius:6px;margin:16px 0;">Você receberá um email de confirmação assim que for aprovado(a).</p>
        <p style="color:#6b7280;font-size:13px;">Obrigado por se cadastrar!<br>Equipe Pro Saúde</p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    def _enviar():
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
                servidor.ehlo()
                servidor.starttls()
                servidor.login(smtp_user, smtp_password)
                servidor.sendmail(smtp_user, [email_aluno], msg.as_string())
        except Exception:
            pass

    threading.Thread(target=_enviar, daemon=True).start()


def notificar_reset_senha(nome: str, email_admin: str) -> None:
    """Notifica admin sobre solicitação de reset de senha."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)
    admin_email = os.getenv("ADMIN_EMAIL", "admin@prosaude.local").strip()

    if not smtp_host or not smtp_user or not smtp_password:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Solicitação de reset de senha - {nome}"
    msg["From"] = smtp_from
    msg["To"] = admin_email

    corpo_texto = f"Uma solicitação de reset de senha foi feita por {nome} ({email_admin}).\n\nAcesse o painel admin para aprovar e redefinir a senha."
    corpo_html = f"""
    <html><body style="font-family:sans-serif;color:#1f2937;">
      <div style="max-width:480px;margin:auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="color:#f47821;">Solicitação de Reset de Senha</h2>
        <p><strong>{nome}</strong> solicitou um reset de senha.</p>
        <p><strong>Email:</strong> {email_admin}</p>
        <p>Acesse o painel admin para aprovar ou rejeitar o pedido.</p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    def _enviar():
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
                servidor.ehlo()
                servidor.starttls()
                servidor.login(smtp_user, smtp_password)
                servidor.sendmail(smtp_user, [admin_email], msg.as_string())
        except Exception:
            pass

    threading.Thread(target=_enviar, daemon=True).start()


def enviar_nova_senha(nome: str, email_aluno: str, nova_senha: str) -> None:
    """Envia a nova senha para o aluno aprovado."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Sua senha foi redefinida - Pro Saúde"
    msg["From"] = smtp_from
    msg["To"] = email_aluno

    corpo_texto = f"Olá {nome},\n\nSua senha foi redefinida pelo administrador.\n\nNova senha: {nova_senha}\n\nA sua nova senha foi redefinida. Recomendamos mudar a senha ao fazer o primeiro login.\n\nEquipe Pro Saúde"
    corpo_html = f"""
    <html><body style="font-family:sans-serif;color:#1f2937;">
      <div style="max-width:480px;margin:auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="color:#f47821;">Senha Redefinida</h2>
        <p>Olá, <strong>{nome}</strong>!</p>
        <p>Sua senha foi redefinida pelo administrador.</p>
        <p style="background:#f3f4f6;padding:12px;border-radius:6px;font-weight:bold;">Nova senha: <code>{nova_senha}</code></p>
        <p style="color:#6b7280;font-size:13px;">Recomendamos mudar a senha no primeiro login.</p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    def _enviar():
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
                servidor.ehlo()
                servidor.starttls()
                servidor.login(smtp_user, smtp_password)
                servidor.sendmail(smtp_user, [email_aluno], msg.as_string())
        except Exception:
            pass

    threading.Thread(target=_enviar, daemon=True).start()


def enviar_confirmacao_checkin(nome: str, email_aluno: str, modalidade: str, data_aula: str, horario_aula: str) -> None:
    """Envia confirmação de check-in para o aluno."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Confirmação de presença - {modalidade}"
    msg["From"] = smtp_from
    msg["To"] = email_aluno

    corpo_texto = f"Olá {nome},\n\nVocê confirmou sua presença na aula.\n\nDetalhes da Aula:\nModalidade: {modalidade}\nData: {data_aula}\nHorário: {horario_aula}\n\nEquipe Pro Saúde"
    corpo_html = f"""
    <html><body style="font-family:sans-serif;color:#1f2937;">
      <div style="max-width:480px;margin:auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
        <h2 style="color:#f47821;">Presenca Confirmada!</h2>
        <p>Ola, <strong>{nome}</strong>!</p>
        <p>Sua presenca foi confirmada na aula.</p>
        <div style="background:#f3f4f6;padding:16px;border-radius:8px;margin:16px 0;">
          <p style="margin:0 0 8px 0;"><strong>Modalidade:</strong> {modalidade}</p>
          <p style="margin:0 0 8px 0;"><strong>Data:</strong> {data_aula}</p>
          <p style="margin:0;"><strong>Horário:</strong> {horario_aula}</p>
        </div>
        <p style="color:#6b7280;font-size:13px;">Nos vemos em breve!</p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    def _enviar():
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
                servidor.ehlo()
                servidor.starttls()
                servidor.login(smtp_user, smtp_password)
                servidor.sendmail(smtp_user, [email_aluno], msg.as_string())
        except Exception:
            pass

    threading.Thread(target=_enviar, daemon=True).start()



def bootstrap_database() -> None:
    db.create_all()
    migrate_database()
    seed_admin_user()


with app.app_context():
    bootstrap_database()


@app.route("/splash-assets/<path:filename>")
def splash_asset(filename: str):
    return send_from_directory(os.path.join(BASE_DIR, "img"), filename)


@app.route("/", methods=["GET"])
def index():
    user = current_user()
    return render_template("index.html", user=user)


@app.route("/ranking", methods=["GET"])
@login_required
def ranking():
    user = current_user()
    ranking_lista = montar_ranking_alunos()
    podio = ranking_lista[:3]
    restante = ranking_lista[3:]
    minha_posicao = next((item for item in ranking_lista if item["aluno_id"] == user.id), None)

    return render_template(
        "ranking.html",
        user=user,
        podio=podio,
        restante=restante,
        ranking=ranking_lista,
        minha_posicao=minha_posicao,
    )


@app.route("/register", methods=["POST"])
def register():
    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")

    if not nome or not email or not senha:
        flash("Preencha nome, email e senha para se cadastrar.", "error")
        return redirect(url_for("index"))

    if Aluno.query.filter_by(email=email).first():
        flash("Este email já está cadastrado.", "error")
        return redirect(url_for("index"))

    aluno = Aluno(nome=nome, email=email, senha_hash=generate_password_hash(senha), aprovado=False)
    db.session.add(aluno)
    db.session.commit()

    # Enviar email de confirmação ao aluno
    enviar_confirmacao_cadastro(nome, email)
    
    # Notificar admin sobre novo cadastro
    notificar_admin_novo_aluno(nome, email)

    flash("Cadastro realizado! Aguarde a aprovação do administrador para acessar o sistema.", "success")
    return redirect(url_for("index"))


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")

    user = Aluno.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.senha_hash, senha):
        flash("Email ou senha inválidos.", "error")
        return redirect(url_for("index"))

    if not user.aprovado:
        flash("Seu cadastro ainda está aguardando aprovação do administrador.", "error")
        return redirect(url_for("index"))

    session["user_id"] = user.id
    flash("Login realizado com sucesso.", "success")
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu da sua conta.", "success")
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = request.form.get("email", "").strip().lower()

    user = Aluno.query.filter_by(email=email).first()
    if not user:
        flash("Email não encontrado no sistema.", "error")
        return redirect(url_for("index"))

    # Verificar se já existe uma requisição pendente
    req_existente = RequisicaoResetSenha.query.filter_by(
        aluno_id=user.id,
        status="pendente"
    ).first()

    if req_existente:
        flash("Você já tem uma solicitação de reset pendente. Aguarde a aprovação do administrador.", "warning")
        return redirect(url_for("index"))

    # Criar nova requisição
    requisicao = RequisicaoResetSenha(aluno_id=user.id, email_solicitante=email)
    db.session.add(requisicao)
    db.session.commit()

    # Notificar admin
    notificar_reset_senha(user.nome, email)

    flash("Solicitação enviada! O administrador analisará seu pedido em breve.", "success")
    return redirect(url_for("index"))


@app.route("/api/aulas", methods=["GET"])
@api_login_required
def api_aulas():
    user = current_user()

    aulas = (
        db.session.query(
            Aula,
            func.count(Checkin.id).label("confirmados"),
        )
        .outerjoin(Checkin, Checkin.aula_id == Aula.id)
        .group_by(Aula.id)
        .order_by(Aula.data.asc(), Aula.horario.asc())
        .all()
    )

    checkins_usuario = {c.aula_id for c in Checkin.query.filter_by(aluno_id=user.id).all()}

    payload = []
    for aula, confirmados in aulas:
        payload.append(
            {
                "id": aula.id,
                "modalidade": aula.modalidade,
                "data": aula.data.strftime("%d/%m/%Y"),
                "horario": aula.horario.strftime("%H:%M"),
                "vagas_totais": aula.vagas_totais,
                "vagas_disponiveis": max(aula.vagas_totais - int(confirmados), 0),
                "confirmados": int(confirmados),
                "checked_in": aula.id in checkins_usuario,
            }
        )

    return jsonify(payload)


@app.route("/api/checkin/<int:aula_id>", methods=["POST"])
@api_login_required
def api_checkin(aula_id: int):
    user = current_user()

    aula = Aula.query.get_or_404(aula_id)

    if aula.data < date.today():
        return jsonify({"error": "Check-in não permitido para aulas passadas."}), 400

    if Checkin.query.filter_by(aluno_id=user.id, aula_id=aula.id).first():
        return jsonify({"message": "Você já confirmou presença nesta aula."}), 200

    total_confirmados = Checkin.query.filter_by(aula_id=aula.id).count()
    if total_confirmados >= aula.vagas_totais:
        return jsonify({"error": "Não há vagas disponíveis para esta aula."}), 409

    checkin = Checkin(aluno_id=user.id, aula_id=aula.id)
    db.session.add(checkin)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Você já confirmou presença nesta aula."}), 200

    # Enviar email de confirmação de check-in
    enviar_confirmacao_checkin(
        user.nome,
        user.email,
        aula.modalidade,
        aula.data.strftime("%d/%m/%Y"),
        aula.horario.strftime("%H:%M")
    )

    return jsonify({"message": "Check-in confirmado com sucesso."}), 201


@app.route("/api/checkin/<int:aula_id>", methods=["DELETE"])
@api_login_required
def api_cancelar_checkin(aula_id: int):
    user = current_user()

    aula = Aula.query.get_or_404(aula_id)

    if aula.data < date.today():
        return jsonify({"error": "Não é possível cancelar check-in de aulas passadas."}), 400

    checkin = Checkin.query.filter_by(aluno_id=user.id, aula_id=aula.id).first()
    if not checkin:
        return jsonify({"error": "Você não tem check-in nesta aula."}), 404

    db.session.delete(checkin)
    db.session.commit()

    return jsonify({"message": "Presença cancelada com sucesso."}), 200


@app.route("/api/minha-aula", methods=["GET"])
@api_login_required
def api_minha_aula():
    user = current_user()

    hoje = date.today()
    aula = (
        db.session.query(Aula)
        .join(Checkin, Checkin.aula_id == Aula.id)
        .filter(Checkin.aluno_id == user.id, Aula.data == hoje)
        .order_by(Aula.horario.asc())
        .first()
    )

    if not aula:
        return jsonify({"has_class": False})

    return jsonify(
        {
            "has_class": True,
            "modalidade": aula.modalidade,
            "data": aula.data.strftime("%d/%m/%Y"),
            "horario": aula.horario.strftime("%H:%M"),
            "plano_aula": aula.plano_aula,
            "equipamentos_necessarios": aula.equipamentos_necessarios,
        }
    )


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    guard = current_user()

    if request.method == "POST":
        modalidade = request.form.get("modalidade", "").strip()
        data_raw = request.form.get("data", "")
        horario_raw = request.form.get("horario", "")
        vagas_totais = request.form.get("vagas_totais", "0")
        plano_aula = request.form.get("plano_aula", "").strip()
        equipamentos_necessarios = request.form.get("equipamentos_necessarios", "").strip()

        try:
            parsed_data = datetime.strptime(data_raw, "%Y-%m-%d").date()
            parsed_horario = datetime.strptime(horario_raw, "%H:%M").time()
            parsed_vagas = int(vagas_totais)
            if parsed_vagas <= 0:
                raise ValueError
        except ValueError:
            flash("Preencha data, horário e vagas com valores válidos.", "error")
            return redirect(url_for("admin"))

        if parsed_data < date.today():
            flash("Não é permitido cadastrar aula em data passada.", "error")
            return redirect(url_for("admin"))

        if modalidade not in MODALIDADES_VALIDAS:
            flash("Modalidade inválida.", "error")
            return redirect(url_for("admin"))

        if not plano_aula or not equipamentos_necessarios:
            flash("Plano de aula e equipamentos são obrigatórios.", "error")
            return redirect(url_for("admin"))

        aula_existente = Aula.query.filter_by(
            modalidade=modalidade,
            data=parsed_data,
            horario=parsed_horario,
        ).first()
        if aula_existente:
            flash("Já existe uma aula dessa modalidade nesse dia e horário.", "error")
            return redirect(url_for("admin"))

        aula = Aula(
            modalidade=modalidade,
            data=parsed_data,
            horario=parsed_horario,
            vagas_totais=parsed_vagas,
            plano_aula=plano_aula,
            equipamentos_necessarios=equipamentos_necessarios,
        )
        db.session.add(aula)
        db.session.commit()
        flash("Aula cadastrada com sucesso.", "success")
        return redirect(url_for("admin"))

    aulas = (
        db.session.query(Aula)
        .order_by(Aula.data.desc(), Aula.horario.desc())
        .all()
    )

    resumo = []
    for aula in aulas:
        confirmados = (
            db.session.query(Checkin, Aluno.nome, Aluno.email)
            .join(Aluno, Checkin.aluno_id == Aluno.id)
            .filter(Checkin.aula_id == aula.id)
            .order_by(Aluno.nome.asc())
            .all()
        )
        resumo.append(
            {
                "aula": aula,
                "confirmados": [
                    {
                        "checkin_id": checkin.id,
                        "nome": nome,
                        "email": email,
                        "compareceu": checkin.compareceu,
                        "pontos_recebidos": checkin.pontos_recebidos,
                    }
                    for checkin, nome, email in confirmados
                ],
            }
        )

    pendentes = Aluno.query.filter_by(aprovado=False, is_admin=False).order_by(Aluno.id.asc()).all()
    resets_pendentes = RequisicaoResetSenha.query.filter_by(status="pendente").all()
    alunos_aprovados = Aluno.query.filter_by(aprovado=True, is_admin=False).order_by(Aluno.nome.asc()).all()

    stats = {
        "total_alunos": len(alunos_aprovados),
        "total_aulas": Aula.query.count(),
        "total_checkins": Checkin.query.count(),
        "total_pendentes": len(pendentes),
        "total_resets": len(resets_pendentes),
    }

    return render_template("admin.html", user=guard, resumo=resumo, stats=stats, pendentes=pendentes, resets_pendentes=resets_pendentes, alunos_aprovados=alunos_aprovados)


@app.route("/admin/aluno/<int:aluno_id>/aprovar", methods=["POST"])
@admin_required
def admin_aprovar_aluno(aluno_id: int):
    aluno = Aluno.query.get_or_404(aluno_id)
    aluno.aprovado = True
    db.session.commit()
    enviar_email_aprovacao(aluno.nome, aluno.email)
    flash(f"Aluno {aluno.nome} aprovado com sucesso.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/aluno/<int:aluno_id>/rejeitar", methods=["POST"])
@admin_required
def admin_rejeitar_aluno(aluno_id: int):
    aluno = Aluno.query.get_or_404(aluno_id)
    db.session.delete(aluno)
    db.session.commit()
    flash(f"Cadastro de {aluno.nome} rejeitado e removido.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/aluno/<int:aluno_id>/excluir", methods=["POST"])
@admin_required
def admin_excluir_aluno(aluno_id: int):
    aluno = Aluno.query.get_or_404(aluno_id)
    if aluno.is_admin:
        flash("Você não pode excluir um administrador.", "error")
        return redirect(url_for("admin"))
    nome_aluno = aluno.nome
    db.session.delete(aluno)
    db.session.commit()
    flash(f"Aluno {nome_aluno} foi excluído do sistema.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/reset-senha/<int:requisicao_id>/aprovar", methods=["POST"])
@admin_required
def admin_aprovar_reset(requisicao_id: int):
    requisicao = RequisicaoResetSenha.query.get_or_404(requisicao_id)
    aluno = requisicao.aluno

    # Gerar nova senha aleatória (8 caracteres)
    nova_senha = "".join(random.choices(string.ascii_letters + string.digits, k=8))

    # Atualizar senha do aluno
    aluno.senha_hash = generate_password_hash(nova_senha)
    requisicao.status = "aprovado"
    requisicao.nova_senha = nova_senha
    db.session.commit()

    # Enviar nova senha para o aluno
    enviar_nova_senha(aluno.nome, aluno.email, nova_senha)

    flash(f"Reset de senha para {aluno.nome} foi aprovado. Nova senha enviada por email.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/reset-senha/<int:requisicao_id>/rejeitar", methods=["POST"])
@admin_required
def admin_rejeitar_reset(requisicao_id: int):
    requisicao = RequisicaoResetSenha.query.get_or_404(requisicao_id)
    aluno = requisicao.aluno
    requisicao.status = "rejeitado"
    db.session.commit()
    flash(f"Solicitação de reset de {aluno.nome} foi rejeitada.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/aula/<int:aula_id>/delete", methods=["POST"])
@admin_required
def admin_delete_aula(aula_id: int):
    aula = Aula.query.get_or_404(aula_id)
    db.session.delete(aula)
    db.session.commit()
    flash("Aula removida com sucesso.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/checkin/<int:checkin_id>/presenca", methods=["POST"])
@admin_required
def admin_marcar_presenca(checkin_id: int):
    checkin = Checkin.query.get_or_404(checkin_id)
    status = request.form.get("status", "").strip().lower()

    if status == "compareceu":
        checkin.compareceu = True
        checkin.pontos_recebidos = 10
        flash("Presença confirmada. 10 pontos aplicados ao aluno.", "success")
    elif status == "faltou":
        checkin.compareceu = False
        checkin.pontos_recebidos = 0
        flash("Falta registrada. Pontuação do check-in ficou em 0.", "success")
    else:
        flash("Status de presença inválido.", "error")
        return redirect(url_for("admin"))

    db.session.commit()
    return redirect(url_for("admin"))


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
