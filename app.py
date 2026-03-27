


from __future__ import annotations
import json
import os
import random
import smtplib
import string
import threading
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from dotenv import load_dotenv
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
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

# ── Constantes ────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads", "fotos")
os.makedirs(UPLOADS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MODALIDADES_VALIDAS = {"funcional", "natacao", "natação", "volei", "vôlei"}

# ── App Flask ─────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Render usa postgres:// mas SQLAlchemy 2.x exige postgresql://
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace(
        "postgres://", "postgresql://", 1
    )

db = SQLAlchemy(app)


# ── Models ────────────────────────────────────────────────────────────
class Aluno(db.Model):
    __tablename__ = "alunos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    aprovado = db.Column(db.Boolean, nullable=False, default=False)
    foto_path = db.Column(db.String(255))


class Aula(db.Model):
    __tablename__ = "aulas"
    id = db.Column(db.Integer, primary_key=True)
    modalidade = db.Column(db.String(30), nullable=False)
    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.Time, nullable=False)
    vagas_totais = db.Column(db.Integer, nullable=False)
    plano_aula = db.Column(db.Text, nullable=False)
    equipamentos_necessarios = db.Column(db.Text, nullable=False)


class Checkin(db.Model):
    __tablename__ = "checkins"
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    aula_id = db.Column(db.Integer, db.ForeignKey("aulas.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    compareceu = db.Column(db.Boolean)
    pontos_recebidos = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("aluno_id", "aula_id"),)


class RankingEvento(db.Model):
    __tablename__ = "ranking_eventos"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    modalidade = db.Column(db.String(30), nullable=False)
    pontos_ganhos = db.Column(db.Integer, nullable=False, default=0)
    data_hora = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    origem = db.Column(db.String(30), nullable=False, default="gym")
    request_id = db.Column(db.String(80))
    detalhes = db.Column(db.Text)


class Desafio(db.Model):
    __tablename__ = "desafios"
    id = db.Column(db.Integer, primary_key=True)
    criador_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    oponente_id = db.Column(db.Integer, db.ForeignKey("alunos.id"))
    titulo = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    meta = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="aberto")
    resultado_criador = db.Column(db.String(120))
    resultado_oponente = db.Column(db.String(120))
    vencedor_id = db.Column(db.Integer, db.ForeignKey("alunos.id"))
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    criador = db.relationship("Aluno", foreign_keys=[criador_id])
    oponente = db.relationship("Aluno", foreign_keys=[oponente_id])
    vencedor = db.relationship("Aluno", foreign_keys=[vencedor_id])


class RequisicaoResetSenha(db.Model):
    __tablename__ = "requisicoes_reset_senha"
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    email_solicitante = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pendente")
    nova_senha = db.Column(db.String(120))
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    aluno = db.relationship("Aluno")


class Seguidor(db.Model):
    __tablename__ = "seguidores"
    id = db.Column(db.Integer, primary_key=True)
    seguidor_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    seguido_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    midia_path = db.Column(db.String(255), nullable=False)
    legenda = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    aluno = db.relationship("Aluno", backref="posts")
    curtidas = db.relationship("Curtida", backref="post", lazy="select")


class Curtida(db.Model):
    __tablename__ = "curtidas"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    aluno_id = db.Column(db.Integer, db.ForeignKey("alunos.id"), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


# ── Context Processor ─────────────────────────────────────────────────
@app.context_processor
def inject_models():
    return dict(Post=Post)


POST_UPLOADS_DIR = os.path.join(BASE_DIR, "static", "uploads", "posts")
os.makedirs(POST_UPLOADS_DIR, exist_ok=True)

ALLOWED_POST_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "webm"}


# ── Helpers ───────────────────────────────────────────────────────────
def current_user() -> Aluno | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return Aluno.query.get(user_id)


def redirect_back(default_endpoint: str = "index"):
    next_url = (request.form.get("next") or request.args.get("next") or request.referrer or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for(default_endpoint))


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
        if "foto_path" not in columns:
            conn.execute(db.text("ALTER TABLE alunos ADD COLUMN foto_path VARCHAR(255)"))

        checkin_result = conn.execute(db.text("PRAGMA table_info(checkins)"))
        checkin_columns = [row[1] for row in checkin_result.fetchall()]
        if "compareceu" not in checkin_columns:
            conn.execute(db.text("ALTER TABLE checkins ADD COLUMN compareceu BOOLEAN"))
        if "pontos_recebidos" not in checkin_columns:
            conn.execute(db.text("ALTER TABLE checkins ADD COLUMN pontos_recebidos INTEGER NOT NULL DEFAULT 0"))

        ranking_result = conn.execute(db.text("PRAGMA table_info(ranking_eventos)"))
        ranking_columns = [row[1] for row in ranking_result.fetchall()]
        if "request_id" not in ranking_columns:
            conn.execute(db.text("ALTER TABLE ranking_eventos ADD COLUMN request_id VARCHAR(80)"))

        conn.execute(
            db.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_ranking_evento_user_request "
                "ON ranking_eventos(user_id, request_id) "
                "WHERE request_id IS NOT NULL"
            )
        )

        conn.commit()


def montar_ranking_alunos() -> list[dict]:
    ranking_rows = (
        db.session.query(
            Aluno.id.label("aluno_id"),
            Aluno.nome.label("nome"),
            Aluno.email.label("email"),
            Aluno.foto_path.label("foto_path"),
            func.coalesce(func.sum(Checkin.pontos_recebidos), 0).label("pontos"),
            func.coalesce(func.sum(case((Checkin.compareceu.is_(True), 1), else_=0)), 0).label("presencas"),
            func.count(Checkin.id).label("checkins"),
        )
        .outerjoin(Checkin, Checkin.aluno_id == Aluno.id)
        .filter(Aluno.aprovado.is_(True), Aluno.is_admin.is_(False))
        .group_by(Aluno.id)
        .all()
    )

    pontos_extras_rows = (
        db.session.query(
            RankingEvento.user_id.label("aluno_id"),
            func.coalesce(func.sum(RankingEvento.pontos_ganhos), 0).label("pontos_extras"),
        )
        .group_by(RankingEvento.user_id)
        .all()
    )
    pontos_extras_map = {row.aluno_id: int(row.pontos_extras or 0) for row in pontos_extras_rows}

    ranking = [
        {
            "aluno_id": row.aluno_id,
            "nome": row.nome,
            "email": row.email,
            "foto_path": row.foto_path,
            "pontos": int(row.pontos or 0) + pontos_extras_map.get(row.aluno_id, 0),
            "presencas": int(row.presencas or 0),
            "checkins": int(row.checkins or 0),
        }
        for row in ranking_rows
    ]

    ranking.sort(key=lambda item: (-item["pontos"], -item["presencas"], item["nome"].lower()))

    for idx, item in enumerate(ranking, start=1):
        item["posicao"] = idx

    return ranking


def limpar_aulas_passadas() -> None:
    """Deleta automaticamente as aulas que já passaram (data < hoje)."""
    try:
        hoje = date.today()
        aulas_passadas = Aula.query.filter(Aula.data < hoje).all()
        
        for aula in aulas_passadas:
            # Deletar check-ins associados (cascade vai fazer isso, mas deixamos explícito)
            Checkin.query.filter_by(aula_id=aula.id).delete()
            # Deletar a aula
            db.session.delete(aula)
        
        if aulas_passadas:
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass


def allowed_file(filename: str) -> bool:
    """Verifica se a extensão do arquivo é permitida."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def salvar_foto_aluno(file, aluno_id: int) -> str | None:
    """
    Salva a foto do aluno e retorna o caminho relativo.
    Retorna None se houver erro.
    """
    if not file or file.filename == "":
        return None

    if not allowed_file(file.filename):
        return None

    try:
        # Gerar nome único para arquivo
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = secure_filename(f"aluno_{aluno_id}_{datetime.now().timestamp()}.{ext}")
        filepath = os.path.join(UPLOADS_DIR, filename)
        
        # Salvar arquivo
        file.save(filepath)
        
        # Retornar caminho relativo
        return f"uploads/fotos/{filename}"
    except Exception:
        return None


def deletar_foto_aluno(foto_path: str) -> bool:
    """Deleta a foto anterior do aluno se existir."""
    if not foto_path:
        return True
    
    try:
        full_path = os.path.join(BASE_DIR, foto_path)
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception:
        pass
    
    return True


def normalizar_modalidade(modalidade: str) -> str:
    valor = (modalidade or "").strip().lower()
    mapa = {
        "volei": "volei",
        "vôlei": "volei",
        "natacao": "natacao",
        "natação": "natacao",
        "funcional": "funcional",
    }
    return mapa.get(valor, "")


def processar_pontos_ranking(registros: list[dict], origem: str = "gym") -> dict:
    """Serviço central para contabilizar pontos extras no ranking global."""
    eventos: list[RankingEvento] = []
    total_pontos = 0
    duplicados = 0

    for item in registros:
        user_id = int(item.get("user_id", 0))
        modalidade = normalizar_modalidade(item.get("modalidade", ""))
        pontos = int(item.get("pontos_ganhos", 0))
        data_hora_raw = str(item.get("data_hora", "")).strip()
        detalhes_raw = item.get("detalhes")
        request_id = str(item.get("request_id", "")).strip() or None

        if not user_id or not modalidade or pontos <= 0:
            continue

        aluno = Aluno.query.filter_by(id=user_id, aprovado=True, is_admin=False).first()
        if not aluno:
            continue

        if request_id:
            duplicado = RankingEvento.query.filter_by(user_id=user_id, request_id=request_id).first()
            if duplicado:
                duplicados += 1
                continue

        try:
            data_hora = datetime.fromisoformat(data_hora_raw.replace("Z", "+00:00")) if data_hora_raw else datetime.utcnow()
        except ValueError:
            data_hora = datetime.utcnow()

        evento = RankingEvento(
            user_id=user_id,
            modalidade=modalidade,
            pontos_ganhos=pontos,
            data_hora=data_hora,
            origem=origem,
            request_id=request_id,
            detalhes=json.dumps(detalhes_raw, ensure_ascii=True) if detalhes_raw is not None else None,
        )
        eventos.append(evento)
        total_pontos += pontos

    if not eventos:
        if duplicados:
            return {"ok": False, "duplicate": True, "error": "Pontuação já processada para esta ação."}
        return {"ok": False, "error": "Nenhum registro de pontuação válido para processar."}

    db.session.add_all(eventos)
    db.session.commit()

    return {
        "ok": True,
        "registros": len(eventos),
        "total_pontos": total_pontos,
    }


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
    # Só rodar migrate_database se as tabelas já existirem
    try:
        migrate_database()
    except Exception:
        pass
    seed_admin_user()


with app.app_context():
    bootstrap_database()


@app.route("/splash-assets/<path:filename>")
def splash_asset(filename: str):
    return send_from_directory(os.path.join(BASE_DIR, "img"), filename)


@app.route("/", methods=["GET"])
def index():
    limpar_aulas_passadas()
    user = current_user()
    return render_template("index.html", user=user)


@app.route("/feed", methods=["GET"])
@login_required
def feed():
    user = current_user()
    posts = Post.query.order_by(Post.criado_em.desc()).limit(40).all()

    story_users = (
        Aluno.query.filter(Aluno.aprovado.is_(True), Aluno.is_admin.is_(False))
        .order_by(Aluno.nome.asc())
        .limit(12)
        .all()
    )

    return render_template(
        "feed.html",
        user=user,
        posts=posts,
        story_users=story_users,
    )


@app.route("/postar", methods=["POST"])
@login_required
def postar():
    user = current_user()
    if "midia" not in request.files:
        flash("Nenhum arquivo foi enviado.", "error")
        return redirect_back("feed")

    file = request.files["midia"]
    if file.filename == "":
        flash("Nenhum arquivo foi selecionado.", "error")
        return redirect_back("feed")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_POST_EXTENSIONS:
        flash("Tipo de arquivo não permitido.", "error")
        return redirect_back("feed")

    tipo = "video" if ext in {"mp4", "mov", "webm"} else "foto"
    filename = secure_filename(f"post_{user.id}_{datetime.now().timestamp()}.{ext}")
    filepath = os.path.join(POST_UPLOADS_DIR, filename)
    file.save(filepath)

    midia_path = f"uploads/posts/{filename}"
    legenda = request.form.get("legenda", "").strip()[:200]

    post = Post(aluno_id=user.id, tipo=tipo, midia_path=midia_path, legenda=legenda or None)
    db.session.add(post)
    db.session.commit()

    flash("Post publicado!", "success")
    return redirect_back("feed")


@app.route("/curtir/<int:post_id>", methods=["POST"])
@login_required
def curtir_post(post_id: int):
    user = current_user()
    post = Post.query.get_or_404(post_id)

    curtida_existente = Curtida.query.filter_by(post_id=post.id, aluno_id=user.id).first()
    if curtida_existente:
        db.session.delete(curtida_existente)
        db.session.commit()
    else:
        curtida = Curtida(post_id=post.id, aluno_id=user.id)
        db.session.add(curtida)
        db.session.commit()

    return redirect_back("feed")


@app.route("/perfil/<int:aluno_id>", methods=["GET"])
@login_required
def perfil_publico(aluno_id: int):
    user = current_user()
    aluno = Aluno.query.get_or_404(aluno_id)

    seguidores_count = Seguidor.query.filter_by(seguido_id=aluno.id).count()
    seguindo_count = Seguidor.query.filter_by(seguidor_id=aluno.id).count()
    seguindo = Seguidor.query.filter_by(seguidor_id=user.id, seguido_id=aluno.id).first() is not None

    total_checkins = Checkin.query.filter_by(aluno_id=aluno.id).count()
    total_presencas = Checkin.query.filter_by(aluno_id=aluno.id, compareceu=True).count()

    pontos_checkins = db.session.query(func.coalesce(func.sum(Checkin.pontos_recebidos), 0)).filter_by(aluno_id=aluno.id).scalar()
    pontos_extras = db.session.query(func.coalesce(func.sum(RankingEvento.pontos_ganhos), 0)).filter_by(user_id=aluno.id).scalar()
    total_pontos = int(pontos_checkins or 0) + int(pontos_extras or 0)

    posts = Post.query.filter_by(aluno_id=aluno.id).order_by(Post.criado_em.desc()).all()

    return render_template(
        "perfil_publico.html",
        user=user,
        aluno=aluno,
        seguidores_count=seguidores_count,
        seguindo_count=seguindo_count,
        seguindo=seguindo,
        total_checkins=total_checkins,
        total_presencas=total_presencas,
        total_pontos=total_pontos,
        posts=posts,
    )


@app.route("/seguir/<int:aluno_id>", methods=["POST"])
@login_required
def seguir_aluno(aluno_id: int):
    user = current_user()
    if user.id == aluno_id:
        flash("Você não pode seguir a si mesmo.", "error")
        return redirect(url_for("perfil_publico", aluno_id=aluno_id))

    aluno = Aluno.query.get_or_404(aluno_id)
    existente = Seguidor.query.filter_by(seguidor_id=user.id, seguido_id=aluno.id).first()
    if existente:
        db.session.delete(existente)
        db.session.commit()
        flash(f"Você deixou de seguir {aluno.nome}.", "success")
    else:
        seguir = Seguidor(seguidor_id=user.id, seguido_id=aluno.id)
        db.session.add(seguir)
        db.session.commit()
        flash(f"Você agora segue {aluno.nome}!", "success")

    return redirect(url_for("perfil_publico", aluno_id=aluno_id))


@app.route("/ranking", methods=["GET"])
@login_required
def ranking():
    limpar_aulas_passadas()
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


@app.route("/uploads/fotos/<filename>")
def servir_foto(filename: str):
    """Serve as fotos dos alunos."""
    try:
        return send_from_directory(UPLOADS_DIR, filename)
    except Exception:
        flash("Foto não encontrada.", "error")
        return redirect(url_for("index"))


@app.route("/perfil", methods=["GET"])
@login_required
def perfil():
    """Exibe o perfil do aluno com opção para editar foto."""
    user = current_user()
    return render_template("perfil.html", user=user)


@app.route("/perfil/foto", methods=["POST"])
@login_required
def upload_foto():
    """Realiza o upload da foto do aluno."""
    user = current_user()
    
    if "foto" not in request.files:
        return jsonify({"error": "Nenhum arquivo foi enviado."}), 400
    
    file = request.files["foto"]
    
    if file.filename == "":
        return jsonify({"error": "Nenhum arquivo foi selecionado."}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "Tipo de arquivo não permitido. Use JPG, PNG ou WEBP."}), 400
    
    if len(file.read()) > MAX_FILE_SIZE:
        file.seek(0)
        return jsonify({"error": "Arquivo muito grande. Máximo de 5 MB."}), 400
    
    file.seek(0)
    
    # Deletar foto anterior se existir
    if user.foto_path:
        deletar_foto_aluno(user.foto_path)
    
    # Salvar nova foto
    foto_path = salvar_foto_aluno(file, user.id)
    if not foto_path:
        return jsonify({"error": "Erro ao salvar a foto."}), 500
    
    # Atualizar banco de dados
    user.foto_path = foto_path
    db.session.commit()
    
    return jsonify({"message": "Foto salva com sucesso!", "foto_path": foto_path}), 200


# ── RATS: Desafios entre alunos ──────────────────────────────────────

@app.route("/rats", methods=["GET"])
@login_required
def rats():
    user = current_user()
    return render_template("rats.html", user=user)


@app.route("/api/rats/desafios", methods=["GET"])
@api_login_required
def api_rats_listar():
    user = current_user()
    desafios = (
        Desafio.query
        .filter(
            db.or_(
                Desafio.criador_id == user.id,
                Desafio.oponente_id == user.id,
                Desafio.status == "aberto",
            )
        )
        .order_by(Desafio.criado_em.desc())
        .all()
    )
    resultado = []
    for d in desafios:
        resultado.append({
            "id": d.id,
            "titulo": d.titulo,
            "descricao": d.descricao,
            "tipo": d.tipo,
            "meta": d.meta,
            "status": d.status,
            "criador": {"id": d.criador.id, "nome": d.criador.nome},
            "oponente": {"id": d.oponente.id, "nome": d.oponente.nome} if d.oponente else None,
            "resultado_criador": d.resultado_criador,
            "resultado_oponente": d.resultado_oponente,
            "vencedor": {"id": d.vencedor.id, "nome": d.vencedor.nome} if d.vencedor else None,
            "criado_em": d.criado_em.strftime("%d/%m/%Y %H:%M"),
            "is_mine": d.criador_id == user.id,
        })
    return jsonify(resultado)


@app.route("/api/rats/desafios", methods=["POST"])
@api_login_required
def api_rats_criar():
    user = current_user()
    data = request.get_json(silent=True) or {}
    titulo = str(data.get("titulo", "")).strip()
    descricao = str(data.get("descricao", "")).strip()
    tipo = str(data.get("tipo", "")).strip()
    meta = str(data.get("meta", "")).strip()

    if not titulo or not descricao or not tipo or not meta:
        return jsonify({"error": "Preencha todos os campos."}), 400
    if tipo not in ("tempo", "repeticoes", "distancia", "livre"):
        return jsonify({"error": "Tipo inválido."}), 400

    desafio = Desafio(criador_id=user.id, titulo=titulo, descricao=descricao, tipo=tipo, meta=meta)
    db.session.add(desafio)
    db.session.commit()
    return jsonify({"message": "Desafio criado!", "id": desafio.id}), 201


@app.route("/api/rats/desafios/<int:desafio_id>/aceitar", methods=["POST"])
@api_login_required
def api_rats_aceitar(desafio_id):
    user = current_user()
    d = Desafio.query.get_or_404(desafio_id)
    if d.status != "aberto":
        return jsonify({"error": "Este desafio não está mais aberto."}), 400
    if d.criador_id == user.id:
        return jsonify({"error": "Você não pode aceitar seu próprio desafio."}), 400
    d.oponente_id = user.id
    d.status = "aceito"
    db.session.commit()
    return jsonify({"message": f"Você aceitou o desafio: {d.titulo}!"})


@app.route("/api/rats/desafios/<int:desafio_id>/resultado", methods=["POST"])
@api_login_required
def api_rats_resultado(desafio_id):
    user = current_user()
    d = Desafio.query.get_or_404(desafio_id)
    if d.status != "aceito":
        return jsonify({"error": "O desafio precisa ser aceito antes de registrar resultado."}), 400
    if user.id not in (d.criador_id, d.oponente_id):
        return jsonify({"error": "Você não participa deste desafio."}), 403

    data = request.get_json(silent=True) or {}
    resultado = str(data.get("resultado", "")).strip()
    if not resultado:
        return jsonify({"error": "Informe seu resultado."}), 400

    if user.id == d.criador_id:
        d.resultado_criador = resultado
    else:
        d.resultado_oponente = resultado

    if d.resultado_criador and d.resultado_oponente:
        d.status = "concluido"

    db.session.commit()
    return jsonify({"message": "Resultado registrado!"})


@app.route("/api/rats/desafios/<int:desafio_id>/vencedor", methods=["POST"])
@api_login_required
def api_rats_vencedor(desafio_id):
    user = current_user()
    d = Desafio.query.get_or_404(desafio_id)
    if d.status != "concluido":
        return jsonify({"error": "O desafio ainda não foi concluído."}), 400
    if user.id not in (d.criador_id, d.oponente_id):
        return jsonify({"error": "Você não participa deste desafio."}), 403

    data = request.get_json(silent=True) or {}
    vencedor_id = data.get("vencedor_id")
    if vencedor_id not in (d.criador_id, d.oponente_id):
        return jsonify({"error": "Vencedor inválido."}), 400

    d.vencedor_id = vencedor_id
    db.session.commit()
    return jsonify({"message": "Vencedor definido!"})


@app.route("/api/rats/desafios/<int:desafio_id>/cancelar", methods=["POST"])
@api_login_required
def api_rats_cancelar(desafio_id):
    user = current_user()
    d = Desafio.query.get_or_404(desafio_id)
    if d.criador_id != user.id:
        return jsonify({"error": "Apenas o criador pode cancelar."}), 403
    if d.status == "concluido":
        return jsonify({"error": "Desafio já concluído."}), 400
    d.status = "cancelado"
    db.session.commit()
    return jsonify({"message": "Desafio cancelado."})


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
    limpar_aulas_passadas()
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
    limpar_aulas_passadas()
    user = current_user()

    hoje = date.today()
    aula = (
        db.session.query(Aula)
        .join(Checkin, Checkin.aula_id == Aula.id)
        .filter(Checkin.aluno_id == user.id, Aula.data >= hoje)
        .order_by(Aula.data.asc(), Aula.horario.asc())
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


@app.route("/api/gym/checkin-info", methods=["GET"])
@api_login_required
def api_gym_checkin_info():
    """Retorna a modalidade de check-in atual do usuário para a tela Gym."""
    user = current_user()
    hoje = date.today()
    aula = (
        db.session.query(Aula)
        .join(Checkin, Checkin.aula_id == Aula.id)
        .filter(Checkin.aluno_id == user.id, Aula.data >= hoje)
        .order_by(Aula.data.asc(), Aula.horario.asc())
        .first()
    )

    if not aula:
        return jsonify({"has_checkin": False, "userCheckinInfo": None})

    return jsonify(
        {
            "has_checkin": True,
            "userCheckinInfo": {
                "userId": user.id,
                "modalidade": normalizar_modalidade(aula.modalidade),
                "aulaId": aula.id,
                "dataHora": datetime.utcnow().isoformat(),
            },
        }
    )


@app.route("/api/gym/atletas", methods=["GET"])
@api_login_required
def api_gym_atletas():
    """Busca atletas para composição de duplas na modalidade de vôlei."""
    termo = request.args.get("q", "").strip().lower()

    query = Aluno.query.filter_by(aprovado=True, is_admin=False)
    if termo:
        like = f"%{termo}%"
        query = query.filter(or_(Aluno.nome.ilike(like), Aluno.email.ilike(like)))

    atletas = query.order_by(Aluno.nome.asc()).limit(30).all()
    return jsonify(
        [
            {"id": atleta.id, "nome": atleta.nome, "email": atleta.email}
            for atleta in atletas
        ]
    )


@app.route("/api/gym/process-points", methods=["POST"])
@api_login_required
def api_gym_process_points():
    """Endpoint de serviço para consolidar pontos da tela Gym no ranking global."""
    user = current_user()
    payload = request.get_json(silent=True) or {}
    modalidade = normalizar_modalidade(str(payload.get("modalidade", "")))
    data_hora = str(payload.get("dataHora", "")).strip() or datetime.utcnow().isoformat()
    request_id = str(payload.get("requestId", "")).strip()

    if modalidade not in {"volei", "natacao", "funcional"}:
        return jsonify({"error": "Modalidade inválida para processamento de pontos."}), 400
    if not request_id:
        return jsonify({"error": "requestId é obrigatório para evitar pontuação duplicada."}), 400

    try:
        if modalidade == "volei":
            score = payload.get("score") or {}
            pontos_a = int(score.get("timeA", 0))
            pontos_b = int(score.get("timeB", 0))
            time_a_ids = [int(v) for v in (payload.get("timeAIds") or [])]
            time_b_ids = [int(v) for v in (payload.get("timeBIds") or [])]

            if len(time_a_ids) != 2 or len(time_b_ids) != 2:
                return jsonify({"error": "Cada time deve ter exatamente 2 atletas."}), 400
            if pontos_a == pontos_b:
                return jsonify({"error": "Empate não é permitido. Informe placar final com vencedor."}), 400

            ids_unicos = set(time_a_ids + time_b_ids)
            if len(ids_unicos) != 4:
                return jsonify({"error": "Os atletas da partida devem ser únicos."}), 400
            if user.id not in ids_unicos:
                return jsonify({"error": "A partida precisa incluir o usuário logado."}), 403

            atletas_validos = Aluno.query.filter(Aluno.id.in_(ids_unicos), Aluno.aprovado.is_(True), Aluno.is_admin.is_(False)).count()
            if atletas_validos != 4:
                return jsonify({"error": "Um ou mais atletas informados não são válidos."}), 400

            vencedores = time_a_ids if pontos_a > pontos_b else time_b_ids
            perdedores = time_b_ids if pontos_a > pontos_b else time_a_ids

            registros = []
            for atleta_id in vencedores:
                registros.append(
                    {
                        "user_id": atleta_id,
                        "modalidade": modalidade,
                        "pontos_ganhos": 15,
                        "data_hora": data_hora,
                        "request_id": request_id,
                        "detalhes": payload,
                    }
                )
            for atleta_id in perdedores:
                registros.append(
                    {
                        "user_id": atleta_id,
                        "modalidade": modalidade,
                        "pontos_ganhos": 10,
                        "data_hora": data_hora,
                        "request_id": request_id,
                        "detalhes": payload,
                    }
                )

            resultado = processar_pontos_ranking(registros, origem="gym")
            if not resultado.get("ok"):
                if resultado.get("duplicate"):
                    return jsonify({"message": "Esta partida já foi processada anteriormente.", "duplicate": True}), 200
                return jsonify({"error": resultado.get("error", "Falha ao processar pontos.")}), 400

            return jsonify(
                {
                    "message": "Partida concluída e pontuação enviada ao ranking.",
                    "resultado": {
                        "vencedores": vencedores,
                        "perdedores": perdedores,
                        "pontosPorVencedor": 15,
                        "pontosPorPerdedor": 10,
                        "registros": resultado["registros"],
                        "totalPontosEnviados": resultado["total_pontos"],
                    },
                }
            )

        pontos_fixos = 20
        registros = [
            {
                "user_id": user.id,
                "modalidade": modalidade,
                "pontos_ganhos": pontos_fixos,
                "data_hora": data_hora,
                "request_id": request_id,
                "detalhes": payload,
            }
        ]
        resultado = processar_pontos_ranking(registros, origem="gym")
        if not resultado.get("ok"):
            if resultado.get("duplicate"):
                return jsonify({"message": "Esta ação já foi processada anteriormente.", "duplicate": True}), 200
            return jsonify({"error": resultado.get("error", "Falha ao processar pontos.")}), 400

        return jsonify(
            {
                "message": "Pontuação enviada ao ranking com sucesso.",
                "resultado": {
                    "userId": user.id,
                    "modalidade": modalidade,
                    "pontosGanhos": pontos_fixos,
                    "dataHora": data_hora,
                    "registros": resultado["registros"],
                    "totalPontosEnviados": resultado["total_pontos"],
                },
            }
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Dados inválidos para processamento de pontos."}), 400


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    limpar_aulas_passadas()
    guard = current_user()

    if request.method == "POST":
        modalidade_raw = request.form.get("modalidade", "")
        modalidade = normalizar_modalidade(modalidade_raw)
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
