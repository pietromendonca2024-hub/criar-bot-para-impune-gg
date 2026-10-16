
import os
import io
import json
import time
import sqlite3
import asyncio
import traceback
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ============================================================
# BOT FACÇÃO PRO — REBUILD DO ZERO
# Interface inspirada nos vídeos enviados:
# - /gerenciar abre um dashboard privado
# - cada sistema possui tela própria de configuração
# - Status / Logs / Cargos / URL / opções específicas
# - painéis públicos usam botões + modais
# ============================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID", "")
FAC_NAME = os.getenv("FAC_NAME", "IMPUNE")
DB_PATH = os.getenv("DB_PATH", "faccao.db")
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
AUTO_SYNC_COMMANDS = os.getenv("AUTO_SYNC_COMMANDS", "1").strip().lower() not in {"0", "false", "no"}

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não configurado.")

# -------- Discord --------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.voice_states = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------- Aparência --------
GOLD = 0xC89B3C
GREEN = 0x57F287
RED = 0xED4245
BLUE = 0x5865F2
GREY = 0x2B2D31
FOOTER = f"{FAC_NAME} • Facção Pro"

# -------- Sistemas --------
SYSTEMS = {
    # Página 1 — igual ao painel principal da referência
    "boas_vindas": {
        "label": "Boas Vindas", "emoji": "🏠",
        "description": "Configure a mensagem privada enviada para novos membros.",
        "public_title": "🏠 BOAS VINDAS", "public_description": "Sistema de boas-vindas da organização.",
        "has_public_panel": False,
    },
    "registro": {
        "label": "Registro", "emoji": "👤",
        "description": "Configure o sistema de registro de novos membros.",
        "public_title": "👤 CENTRAL DE REGISTRO",
        "public_description": "Realize seu registro utilizando o botão abaixo. Após o envio, aguarde a análise da liderança.",
        "has_public_panel": True,
    },
    "vendas": {
        "label": "Vendas", "emoji": "💰",
        "description": "Configure o sistema de vendas no servidor.",
        "public_title": "💰 CENTRAL DE VENDAS", "public_description": "Registre uma nova venda através do botão abaixo.",
        "has_public_panel": True,
    },
    "banco": {
        "label": "Banco", "emoji": "🏦",
        "description": "Configure o sistema de banco no servidor.",
        "public_title": "🏦 CENTRAL DO BANCO", "public_description": "Utilize os botões abaixo para movimentar ou consultar o banco.",
        "has_public_panel": True,
    },
    "farm": {
        "label": "Farm", "emoji": "🌊",
        "description": "Configure o sistema de farm.",
        "public_title": "📦 CENTRAL DE FARM", "public_description": "Envie seu farm para aprovação.",
        "has_public_panel": True,
    },
    "acoes": {
        "label": "Ações", "emoji": "🛩️",
        "description": "Configure o sistema de ações.",
        "public_title": "🎯 CENTRAL DE AÇÕES", "public_description": "Consulte e registre ações da organização.",
        "has_public_panel": True,
    },
    "hierarquia": {
        "label": "Hierarquia", "emoji": "🏰",
        "description": "Configure o sistema de Hierarquia.",
        "public_title": "🏰 HIERARQUIA", "public_description": "Consulte a hierarquia da organização.",
        "has_public_panel": True,
    },
    "ausencia": {
        "label": "Ausência", "emoji": "⌛",
        "description": "Configure o Sistema de Ausência.",
        "public_title": "⌛ CENTRAL DE AUSÊNCIAS", "public_description": "Solicite uma ausência e aguarde a análise da liderança.",
        "has_public_panel": True,
    },

    # Página 2 — restante das funções do Bot Facção Pro
    "lavagem": {
        "label": "Lavagem", "emoji": "💸",
        "description": "Configure o sistema de lavagem.",
        "public_title": "💸 CENTRAL DE LAVAGEM", "public_description": "Registre uma nova operação de lavagem.",
        "has_public_panel": True,
    },
    "encomendas": {
        "label": "Encomendas", "emoji": "📦",
        "description": "Configure o sistema de encomendas.",
        "public_title": "📦 CENTRAL DE ENCOMENDAS", "public_description": "Registre pedidos para aprovação da equipe responsável.",
        "has_public_panel": True,
    },
    "bau": {
        "label": "Baús / Estoque", "emoji": "🧰",
        "description": "Configure baú geral, baú de líder e estoque.",
        "public_title": "🧰 CENTRAL DE BAÚ", "public_description": "Registre entradas, retiradas e consulte o estoque.",
        "has_public_panel": True,
    },
    "advertencias": {
        "label": "Advertências", "emoji": "⚠️",
        "description": "Configure advertências e punições de membros.",
        "public_title": "⚠️ ADVERTÊNCIAS", "public_description": "Sistema interno de advertências.",
        "has_public_panel": False,
    },
    "ranking": {
        "label": "Ranking", "emoji": "🏆",
        "description": "Configure o ranking de membros e pontuação.",
        "public_title": "🏆 RANKING", "public_description": "Ranking geral da organização.",
        "has_public_panel": True,
    },
    "logs": {
        "label": "Logs", "emoji": "📑",
        "description": "Configure logs de entrada, saída, ban, voz, mensagens e cargos.",
        "public_title": "📑 LOGS", "public_description": "Sistema interno de logs.",
        "has_public_panel": False,
    },
    "seguranca": {
        "label": "Segurança", "emoji": "🛡️",
        "description": "Configure Anti-Spam e Anti-Raid.",
        "public_title": "🛡️ SEGURANÇA", "public_description": "Sistema interno de segurança.",
        "has_public_panel": False,
    },
    "backup": {
        "label": "Backup", "emoji": "💾",
        "description": "Configure backup automático e restauração.",
        "public_title": "💾 BACKUP", "public_description": "Sistema interno de backup.",
        "has_public_panel": False,
    },
    "personalizacao": {
        "label": "Personalização", "emoji": "🎨",
        "description": "Configure status, nome, perfil e apresentação do bot.",
        "public_title": "🎨 PERSONALIZAÇÃO", "public_description": "Sistema interno de personalização.",
        "has_public_panel": False,
    },
    "metas": {
        "label": "Metas Semanais", "emoji": "🎯",
        "description": "Metas automáticas de farm, vendas e participação em ações.",
        "public_title": "🎯 METAS DA SEMANA", "public_description": "Acompanhe seu progresso semanal.",
        "has_public_panel": True,
    },
    "promocoes": {
        "label": "Promoções", "emoji": "⬆️",
        "description": "Análise de membros para auxiliar promoções da liderança.",
        "public_title": "⬆️ ANÁLISE DE PROMOÇÕES", "public_description": "Sistema interno da liderança.",
        "has_public_panel": False,
    },
    "inicio": {
        "label": "Central de Início", "emoji": "👋",
        "description": "Painel Comece Aqui integrado aos sistemas da facção.",
        "public_title": "👋 COMECE AQUI", "public_description": "Tudo que um membro precisa para começar.",
        "has_public_panel": True,
    },

    "utilidades": {
        "label": "Utilidades", "emoji": "🧩",
        "description": "Configure embeds, anúncio privado, limpeza e central de ajuda.",
        "public_title": "🧩 UTILIDADES", "public_description": "Ferramentas administrativas.",
        "has_public_panel": False,
    },
}

# Compatibilidade com configurações/bancos de versões anteriores.
# Garante que o painel de Utilidades nunca gere KeyError mesmo após atualização.
SYSTEMS.setdefault("utilidades", {
    "label": "Utilidades", "emoji": "🧩",
    "description": "Configure embeds, anúncio privado, limpeza e central de ajuda.",
    "public_title": "🧩 UTILIDADES", "public_description": "Ferramentas administrativas.",
    "has_public_panel": False,
})

DASHBOARD_PAGES = {
    1: ["boas_vindas", "registro", "vendas", "banco", "farm", "acoes", "hierarquia", "ausencia"],
    2: ["lavagem", "encomendas", "bau", "advertencias", "ranking", "metas", "promocoes"],
    3: ["inicio", "logs", "seguranca", "backup", "personalizacao", "utilidades"],
}

DEFAULTS = {
    "enabled": False,
    "log_channel_id": None,
    "access_role_ids": [],
    "approver_role_ids": [],
    "embed_url": "",
    "approved_role_id": None,
    "visitor_enabled": False,
    "visitor_role_id": None,
    "name_pattern": "{id} | {nome}",
    "products": [],
    "farm_items": [],
    "stock_items": [],
    "partner_discount": 0,
    "laundry_rate": 25.0,
    "member_role_id": None,
    "public_channel_id": None,
    "welcome_channel_id": None,
    "welcome_message": "Bem-vindo(a), {membro}!",
    "welcome_channel_id": None,
    "theme_color": "#C89B3C",
    "message_image_url": "",
    "message_thumbnail_url": "",
    "message_footer_text": "",
    "hierarchy_role_ids": [],
    "leader_role_ids": [],
    "action_ping_role_id": None,
    "sale_points": 2,
    "register_points": 5,
    "farm_points_divisor": 100,
    "spam_count": 6,
    "spam_window": 5,
    "spam_timeout": 45,
    "raid_count": 10,
    "raid_window": 15,
    "anti_spam_enabled": True,
    "anti_raid_enabled": True,
    "auto_backup_enabled": True,
    "weekly_farm_goal": 500,
    "weekly_sales_goal": 2000000,
    "weekly_actions_goal": 3,
    "rules_channel_id": None,
    "hierarchy_channel_id": None,
}

# ============================================================
# BANCO DE DADOS
# ============================================================

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def init_db():
    conn = connect()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS system_config (
            guild_id INTEGER NOT NULL,
            system TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY(guild_id, system)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            identificacao TEXT NOT NULL,
            telefone TEXT,
            recrutador TEXT,
            status TEXT NOT NULL DEFAULT 'pendente',
            reviewer_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            produto TEXT NOT NULL,
            parceria INTEGER NOT NULL DEFAULT 0,
            quantidade INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS banco (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            valor REAL NOT NULL,
            descricao TEXT,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS lavagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            bruto REAL NOT NULL,
            taxa REAL NOT NULL,
            liquido REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS encomendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            responsavel_id INTEGER NOT NULL,
            descricao TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            destinatario TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            reviewer_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ausencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            periodo TEXT NOT NULL,
            motivo TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            reviewer_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS farms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            comprovante TEXT,
            status TEXT NOT NULL DEFAULT 'pendente',
            reviewer_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            guild_id INTEGER NOT NULL,
            bau TEXT NOT NULL,
            item TEXT NOT NULL,
            quantidade INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(guild_id, bau, item)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS estoque_mov (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            bau TEXT NOT NULL,
            tipo TEXT NOT NULL,
            item TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS advertencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            motivo TEXT NOT NULL,
            pontos INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pontos (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            pontos INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(guild_id, user_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS acoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            descricao TEXT,
            horario TEXT,
            status TEXT NOT NULL DEFAULT 'aberta',
            resultado TEXT,
            valor_ganho REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            closed_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS acoes_participantes (
            action_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY(action_id, user_id)
        )
    """)

    # Migrações seguras para builds anteriores
    def ensure_column(table, column, definition):
        cols = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    ensure_column("advertencias", "active", "INTEGER NOT NULL DEFAULT 1")
    ensure_column("advertencias", "removed_by", "INTEGER")
    ensure_column("advertencias", "removed_at", "TEXT")
    ensure_column("advertencias", "removal_reason", "TEXT")

    ensure_column("encomendas", "claimed_by", "INTEGER")
    ensure_column("encomendas", "claimed_at", "TEXT")
    ensure_column("encomendas", "completed_at", "TEXT")
    ensure_column("encomendas", "cancelled_at", "TEXT")

    conn.commit()
    conn.close()

def get_config(guild_id: int, system: str):
    data = dict(DEFAULTS)
    conn = connect()
    row = conn.execute(
        "SELECT data FROM system_config WHERE guild_id=? AND system=?",
        (guild_id, system)
    ).fetchone()
    conn.close()
    if row:
        try:
            saved = json.loads(row["data"])
            if isinstance(saved, dict):
                data.update(saved)
        except Exception:
            pass
    return data

def save_config(guild_id: int, system: str, data: dict):
    conn = connect()
    conn.execute(
        """INSERT INTO system_config(guild_id,system,data) VALUES(?,?,?)
           ON CONFLICT(guild_id,system) DO UPDATE SET data=excluded.data""",
        (guild_id, system, json.dumps(data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()

def update_config(guild_id: int, system: str, **changes):
    cfg = get_config(guild_id, system)
    cfg.update(changes)
    save_config(guild_id, system, cfg)
    return cfg

def add_points(guild_id: int, user_id: int, amount: int):
    conn = connect()
    conn.execute(
        """INSERT INTO pontos(guild_id,user_id,pontos) VALUES(?,?,?)
           ON CONFLICT(guild_id,user_id) DO UPDATE SET pontos=pontos+excluded.pontos""",
        (guild_id, user_id, amount)
    )
    conn.commit()
    conn.close()

# ============================================================
# HELPERS
# ============================================================

def parse_hex_color(value, fallback=GOLD):
    try:
        s = str(value or "").strip().replace("#", "")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) != 6:
            raise ValueError
        return int(s, 16)
    except Exception:
        return fallback


def get_theme(guild_id=None):
    if not guild_id:
        return {
            "color": GOLD,
            "image": "",
            "thumbnail": "",
            "footer": FOOTER,
        }

    try:
        cfg = get_config(guild_id, "personalizacao")
    except Exception:
        cfg = {}

    footer = str(cfg.get("message_footer_text") or "").strip() or FOOTER
    return {
        "color": parse_hex_color(cfg.get("theme_color"), GOLD),
        "image": str(cfg.get("message_image_url") or "").strip(),
        "thumbnail": str(cfg.get("message_thumbnail_url") or "").strip(),
        "footer": footer,
    }


def embed(
    title,
    description="",
    color=None,
    image_url="",
    guild_id=None,
    thumbnail_url="",
    use_theme_image=False,
    use_theme_thumbnail=True
):
    theme = get_theme(guild_id)
    resolved_color = theme["color"] if color is None else color
    e = discord.Embed(title=title, description=description, color=resolved_color)

    # Imagem grande não é mais aplicada em TODAS as mensagens.
    # Ela aparece apenas em painéis/embeds onde use_theme_image=True.
    explicit_image = str(image_url or "").strip()
    final_image = explicit_image or (theme["image"] if use_theme_image else "")

    explicit_thumbnail = str(thumbnail_url or "").strip()
    final_thumbnail = explicit_thumbnail or (theme["thumbnail"] if use_theme_thumbnail else "")

    if final_image:
        e.set_image(url=final_image)
    if final_thumbnail:
        e.set_thumbnail(url=final_thumbnail)

    e.set_footer(text=theme["footer"])
    return e

def role_mentions(guild, ids):
    values = []
    for rid in ids or []:
        role = guild.get_role(int(rid))
        if role:
            values.append(role.mention)
    return ", ".join(values) if values else "Nenhum cargo configurado."

def channel_mention(guild, cid):
    if not cid:
        return "Nenhum canal configurado."
    ch = guild.get_channel(int(cid))
    return ch.mention if ch else "Canal não encontrado."

def role_mention(guild, rid):
    if not rid:
        return "Nenhum cargo configurado."
    role = guild.get_role(int(rid))
    return role.mention if role else "Cargo não encontrado."

def is_admin(member: discord.Member):
    return member.guild_permissions.administrator

def has_access(member: discord.Member, system: str):
    if is_admin(member):
        return True
    cfg = get_config(member.guild.id, system)
    allowed = {int(x) for x in cfg.get("access_role_ids", [])}
    if not allowed:
        return False
    return any(r.id in allowed for r in member.roles)

def can_approve(member: discord.Member, system: str):
    if is_admin(member):
        return True
    cfg = get_config(member.guild.id, system)
    allowed = {int(x) for x in cfg.get("approver_role_ids", [])}
    if not allowed:
        return False
    return any(r.id in allowed for r in member.roles)

def enabled(guild_id: int, system: str):
    return bool(get_config(guild_id, system).get("enabled"))

async def log_event(guild, system, title, description, color=GOLD):
    cfg = get_config(guild.id, system)
    cid = cfg.get("log_channel_id")
    if not cid:
        return
    ch = guild.get_channel(int(cid))
    if isinstance(ch, discord.TextChannel):
        try:
            await ch.send(embed=embed(title, description, color, guild_id=guild.id))
        except Exception:
            pass

async def deny(interaction, text="❌ Você não possui permissão para utilizar esta função."):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)

def money(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_money(text):
    text = str(text).strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(".", "")
    return float(text)

def parse_int(text):
    return int(str(text).replace(".", "").replace(",", "").strip())

# ============================================================
# DASHBOARD V2 — COMPONENTS V2 (discord.py 2.6+)
# Reproduz o padrão visual da referência: texto à esquerda e
# botão de edição à direita em TODAS as opções.
# ============================================================

APPROVAL_SYSTEMS = {"registro", "encomendas", "ausencia", "farm"}


def dashboard_header(page: int):
    total_pages = len(DASHBOARD_PAGES)
    return (
        f"# DashBoard Bot Facção ({page}/{total_pages})\n"
        "Painel central de configurações do bot. Utilize os botões ao lado para acessar cada área."
    )


def system_config_lines(guild: discord.Guild, system: str):
    cfg = get_config(guild.id, system)
    status = "🟢 Ativado" if cfg.get("enabled") else "🔴 Desativado"
    lines = [
        f"**Status atual:** {status}",
        f"**Canal de logs:** {channel_mention(guild, cfg.get('log_channel_id'))}",
        f"**Cargos de acesso:** {role_mentions(guild, cfg.get('access_role_ids', []))}",
    ]
    if system in APPROVAL_SYSTEMS:
        lines.append(f"**Aprovadores:** {role_mentions(guild, cfg.get('approver_role_ids', []))}")
    if system == "registro":
        lines += [
            f"**Padrão de nome:** `{cfg.get('name_pattern', '{id} | {nome}')}`",
            f"**Cargo aprovado:** {role_mention(guild, cfg.get('approved_role_id'))}",
            f"**Visitante:** {'🟢 Ativado' if cfg.get('visitor_enabled') else '🔴 Desativado'}",
            f"**Cargo visitante:** {role_mention(guild, cfg.get('visitor_role_id'))}",
        ]
    if system == "vendas":
        lines += [
            f"**Produtos cadastrados:** {len(cfg.get('products', []))}",
            f"**Desconto parceria:** {cfg.get('partner_discount', 0)}%",
        ]
    if system == "lavagem":
        lines.append(f"**Taxa padrão:** {cfg.get('laundry_rate', 25)}%")
    if system == "farm":
        lines.append(f"**Itens configurados:** {len(cfg.get('farm_items', []))}")
    if system == "seguranca":
        lines += [
            f"**Anti-Spam:** {'🟢' if cfg.get('anti_spam_enabled', True) else '🔴'}",
            f"**Anti-Raid:** {'🟢' if cfg.get('anti_raid_enabled', True) else '🔴'}",
        ]
    if system == "backup":
        lines.append(f"**Backup automático:** {'🟢' if cfg.get('auto_backup_enabled', True) else '🔴'}")
    if system == "boas_vindas":
        lines.append(f"**Canal público:** {channel_mention(guild, cfg.get('welcome_channel_id'))}")
    if system == "hierarquia":
        lines.append(f"**Cargos na hierarquia:** {role_mentions(guild, cfg.get('hierarchy_role_ids', []))}")
    if system == "bau":
        lines.append(f"**Cargos de líder:** {role_mentions(guild, cfg.get('leader_role_ids', []))}")
    if system == "acoes":
        lines.append(f"**Cargo para ping:** {role_mention(guild, cfg.get('action_ping_role_id'))}")
    if system == "ranking":
        lines += [
            f"**Pontos por venda:** {cfg.get('sale_points', 2)}",
            f"**Pontos por registro aprovado:** {cfg.get('register_points', 5)}",
            f"**Divisor de pontos do farm:** {cfg.get('farm_points_divisor', 100)}",
        ]
    if system == "personalizacao":
        lines += [
            f"**Cor principal:** `{cfg.get('theme_color', '#C89B3C')}`",
            f"**Imagem das mensagens:** {'Configurada' if cfg.get('message_image_url') else 'Não configurada'}",
            f"**Miniatura:** {'Configurada' if cfg.get('message_thumbnail_url') else 'Não configurada'}",
            f"**Rodapé:** `{cfg.get('message_footer_text') or FOOTER}`",
        ]
    if system == "seguranca":
        lines += [
            f"**Spam:** {cfg.get('spam_count', 6)} msg / {cfg.get('spam_window', 5)}s",
            f"**Timeout:** {cfg.get('spam_timeout', 45)}s",
            f"**Raid:** {cfg.get('raid_count', 10)} entradas / {cfg.get('raid_window', 15)}s",
        ]
    if cfg.get("embed_url"):
        lines.append(f"**URL da embed:** {cfg['embed_url']}")
    return "\n".join(lines)


class DashboardEditButton(discord.ui.Button):
    def __init__(self, system: str, page: int):
        super().__init__(
            label="Editar",
            emoji="📝",
            style=discord.ButtonStyle.secondary,
            custom_id=f"dash:edit:{page}:{system}",
        )
        self.system = system
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)
        await interaction.response.edit_message(view=SystemConfigLayout(self.system, self.page, interaction.guild))


class DashboardNavButton(discord.ui.Button):
    def __init__(self, target_page: int, direction: str):
        super().__init__(
            label="←" if direction == "back" else "→",
            style=discord.ButtonStyle.secondary,
            custom_id=f"dash:page:{target_page}",
        )
        self.target_page = target_page

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)
        await interaction.response.edit_message(view=DashboardLayout(self.target_page))


class DashboardHomeButton(discord.ui.Button):
    def __init__(self, page=1):
        super().__init__(label="🏠", style=discord.ButtonStyle.secondary, custom_id=f"dash:home:{page}")
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=DashboardLayout(self.page))


class ResetDashboardButton(discord.ui.Button):
    def __init__(self, page: int):
        super().__init__(
            label="Resetar Configuração",
            emoji="⚠️",
            style=discord.ButtonStyle.danger,
            custom_id=f"dash:reset:{page}",
        )
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)
        await interaction.response.send_message(
            "⚠️ Isso vai resetar as configurações dos sistemas desta página. Confirmar?",
            view=ResetConfirmView(self.page, interaction.user.id),
            ephemeral=True,
        )


class ResetConfirmView(discord.ui.View):
    def __init__(self, page: int, author_id: int):
        super().__init__(timeout=60)
        self.page = page
        self.author_id = author_id

    @discord.ui.button(label="CONFIRMAR RESET", emoji="⚠️", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await deny(interaction)
        for system in DASHBOARD_PAGES[self.page]:
            save_config(interaction.guild.id, system, dict(DEFAULTS))
        await interaction.response.edit_message(content="✅ Configurações desta página resetadas.", view=None)


class DashboardLayout(discord.ui.LayoutView):
    def __init__(self, page: int = 1):
        super().__init__(timeout=600)
        page = 1 if page not in DASHBOARD_PAGES else page
        self.page = page

        container = discord.ui.Container(accent_colour=discord.Colour.from_rgb(35, 38, 32))
        container.add_item(discord.ui.TextDisplay(dashboard_header(page)))
        container.add_item(discord.ui.Separator())

        # IMPORTANTE: Components V2 permite no máximo 40 componentes filhos
        # por LayoutView. Cada Section conta também seus componentes internos,
        # então não usamos um Separator após cada sistema.
        for system in DASHBOARD_PAGES[page]:
            meta = SYSTEMS.get(system, {"label": str(system).title(), "emoji": "⚙️", "description": "Sistema administrativo.", "public_title": "⚙️ SISTEMA", "public_description": "Sistema administrativo.", "has_public_panel": False})
            text = f"**{meta['emoji']} Sistema de {meta['label']}**\n{meta['description']}"
            container.add_item(
                discord.ui.Section(
                    text,
                    accessory=DashboardEditButton(system, page),
                )
            )

        nav = discord.ui.ActionRow()
        total_pages = len(DASHBOARD_PAGES)

        if page > 1:
            nav.add_item(DashboardNavButton(page - 1, "back"))
        else:
            nav.add_item(discord.ui.Button(label="←", style=discord.ButtonStyle.secondary, disabled=True))

        if page < total_pages:
            nav.add_item(DashboardNavButton(page + 1, "next"))
        else:
            nav.add_item(discord.ui.Button(label="→", style=discord.ButtonStyle.secondary, disabled=True))

        nav.add_item(ResetDashboardButton(page))
        container.add_item(nav)
        self.add_item(container)


class ConfigActionButton(discord.ui.Button):
    def __init__(self, system: str, page: int, action: str, label: str, emoji: str, style=discord.ButtonStyle.secondary):
        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            custom_id=f"cfg:{system}:{action}",
        )
        self.system = system
        self.page = page
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)
        system = self.system
        action = self.action
        cfg = get_config(interaction.guild.id, system)

        if action == "toggle":
            update_config(interaction.guild.id, system, enabled=not cfg.get("enabled", False))
            return await interaction.response.edit_message(view=SystemConfigLayout(system, self.page, interaction.guild))

        if action == "logs":
            view = discord.ui.View(timeout=120)
            view.add_item(LogChannelSelect(system))
            return await interaction.response.send_message("Selecione o canal de logs:", view=view, ephemeral=True)

        if action == "access":
            view = discord.ui.View(timeout=120)
            view.add_item(AccessRoleSelect(system))
            return await interaction.response.send_message("Selecione os cargos de acesso:", view=view, ephemeral=True)

        if action == "approvers":
            view = discord.ui.View(timeout=120)
            view.add_item(ApproverRoleSelect(system))
            return await interaction.response.send_message("Selecione os cargos aprovadores:", view=view, ephemeral=True)

        if action == "url":
            return await interaction.response.send_modal(URLModal(system))

        if action == "special":
            special_view = SpecialOptionsView(system)
            if not special_view.children:
                return await interaction.response.send_message(
                    "ℹ️ Este sistema não possui configurações específicas adicionais.",
                    ephemeral=True,
                )
            return await interaction.response.send_message(
                f"⚙️ **Configurações específicas — {SYSTEMS.get(system, {"label": str(system).title()})['label']}**",
                view=special_view,
                ephemeral=True,
            )

        if action == "panel":
            if not SYSTEMS.get(system, {}).get("has_public_panel"):
                return await interaction.response.send_message(
                    "ℹ️ Este sistema é administrativo e não possui painel público.",
                    ephemeral=True,
                )
            return await interaction.response.send_message(
                "Escolha o canal para receber o painel:",
                view=PanelChannelView(system),
                ephemeral=True,
            )

        if action == "security_spam":
            update_config(interaction.guild.id, system, anti_spam_enabled=not cfg.get("anti_spam_enabled", True))
            return await interaction.response.edit_message(view=SystemConfigLayout(system, self.page, interaction.guild))

        if action == "security_raid":
            update_config(interaction.guild.id, system, anti_raid_enabled=not cfg.get("anti_raid_enabled", True))
            return await interaction.response.edit_message(view=SystemConfigLayout(system, self.page, interaction.guild))

        if action == "backup_auto":
            update_config(interaction.guild.id, system, auto_backup_enabled=not cfg.get("auto_backup_enabled", True))
            return await interaction.response.edit_message(view=SystemConfigLayout(system, self.page, interaction.guild))


class SystemConfigLayout(discord.ui.LayoutView):
    def __init__(self, system: str, page: int, guild: discord.Guild | None = None):
        super().__init__(timeout=600)
        self.system = system
        self.page = page
        meta = SYSTEMS.get(system, {"label": str(system).title(), "emoji": "⚙️", "description": "Sistema administrativo.", "public_title": "⚙️ SISTEMA", "public_description": "Sistema administrativo.", "has_public_panel": False})

        container = discord.ui.Container(accent_colour=discord.Colour.from_rgb(35, 38, 32))
        container.add_item(discord.ui.TextDisplay(
            f"# {meta['emoji']} Sistema de {meta['label']}\n{meta['description']}"
        ))
        container.add_item(discord.ui.Separator())

        # Cada configuração também usa texto + botão à direita, igual à referência.
        container.add_item(discord.ui.Section(
            "**👁️ Status**\nAtive ou desative o sistema.",
            accessory=ConfigActionButton(system, page, "toggle", "Alterar", "🔄", discord.ButtonStyle.success),
        ))
        container.add_item(discord.ui.Section(
            "**🖥️ Canal de Logs**\nEscolha o canal onde os registros desse sistema serão enviados.",
            accessory=ConfigActionButton(system, page, "logs", "Editar", "📝"),
        ))
        container.add_item(discord.ui.Section(
            "**🔐 Cargos de Acesso**\nDefina quais cargos podem utilizar o sistema.",
            accessory=ConfigActionButton(system, page, "access", "Editar", "📝"),
        ))

        if system in APPROVAL_SYSTEMS:
            container.add_item(discord.ui.Section(
                "**✅ Cargos de Aprovadores**\nDefina quem pode aprovar e reprovar solicitações.",
                accessory=ConfigActionButton(system, page, "approvers", "Editar", "📝"),
            ))

        container.add_item(discord.ui.Section(
            "**🖼️ URL na Embed**\nConfigure uma imagem para a apresentação do sistema.",
            accessory=ConfigActionButton(system, page, "url", "Editar", "📝"),
        ))
        container.add_item(discord.ui.Section(
            "**⚙️ Configurações Específicas**\nOpções próprias deste sistema.",
            accessory=ConfigActionButton(system, page, "special", "Abrir", "⚙️", discord.ButtonStyle.primary),
        ))

        if system == "seguranca":
            container.add_item(discord.ui.Section(
                "**🚫 Anti-Spam**\nAtive ou desative a proteção contra spam.",
                accessory=ConfigActionButton(system, page, "security_spam", "Alternar", "🛡️"),
            ))
            container.add_item(discord.ui.Section(
                "**🚨 Anti-Raid**\nAtive ou desative a detecção de entradas em massa.",
                accessory=ConfigActionButton(system, page, "security_raid", "Alternar", "🛡️"),
            ))

        if system == "backup":
            container.add_item(discord.ui.Section(
                "**💾 Backup Automático**\nAtive ou desative a rotina automática de backup.",
                accessory=ConfigActionButton(system, page, "backup_auto", "Alternar", "🔄"),
            ))

        if meta.get("has_public_panel"):
            container.add_item(discord.ui.Section(
                "**📨 Enviar Painel**\nPublique o painel deste sistema no canal escolhido.",
                accessory=ConfigActionButton(system, page, "panel", "Enviar", "📨", discord.ButtonStyle.primary),
            ))

        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            "## Configuração atual\n" + (system_config_lines(guild, system) if guild else system_config_lines_placeholder(system))
        ))

        nav = discord.ui.ActionRow()
        nav.add_item(DashboardHomeButton(page))
        nav.add_item(DashboardNavButton(page, "back") if False else discord.ui.Button(label="← Voltar", style=discord.ButtonStyle.secondary, custom_id=f"cfgback:{page}"))
        # callback dinâmico do botão Voltar
        back_btn = nav.children[-1]
        async def _back(interaction: discord.Interaction):
            await interaction.response.edit_message(view=DashboardLayout(page))
        back_btn.callback = _back
        container.add_item(nav)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await deny(interaction)
            return False
        # Atualiza o resumo visual antes de cada interação futura quando a tela for refeita.
        return True


def system_config_lines_placeholder(system: str):
    # O LayoutView é construído antes de receber Interaction/Guild. A tela mostra
    # os controles; após cada alteração ela é reconstruída. O estado detalhado
    # é exibido na resposta das opções e no status visual dos controles.
    meta = SYSTEMS.get(system, {"label": str(system).title(), "emoji": "⚙️", "description": "Sistema administrativo.", "public_title": "⚙️ SISTEMA", "public_description": "Sistema administrativo.", "has_public_panel": False})
    return f"Sistema: **{meta['label']}** • alterações salvas automaticamente."


class AccessRoleSelect(discord.ui.RoleSelect):
    def __init__(self, system):
        self.system = system
        super().__init__(placeholder="Selecione até 5 cargos de acesso", min_values=0, max_values=5)
    async def callback(self, interaction):
        update_config(interaction.guild.id, self.system, access_role_ids=[r.id for r in self.values])
        await interaction.response.send_message("✅ Cargos de acesso atualizados.", ephemeral=True)


class ApproverRoleSelect(discord.ui.RoleSelect):
    def __init__(self, system):
        self.system = system
        super().__init__(placeholder="Selecione até 5 cargos aprovadores", min_values=0, max_values=5)
    async def callback(self, interaction):
        update_config(interaction.guild.id, self.system, approver_role_ids=[r.id for r in self.values])
        await interaction.response.send_message("✅ Cargos aprovadores atualizados.", ephemeral=True)


class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, system):
        self.system = system
        super().__init__(placeholder="Selecione o canal de logs", channel_types=[discord.ChannelType.text], min_values=1, max_values=1)
    async def callback(self, interaction):
        update_config(interaction.guild.id, self.system, log_channel_id=self.values[0].id)
        await interaction.response.send_message("✅ Canal de logs atualizado.", ephemeral=True)


class SingleRoleSelect(discord.ui.RoleSelect):
    def __init__(self, system, field, placeholder):
        self.system = system
        self.field = field
        super().__init__(placeholder=placeholder, min_values=1, max_values=1)
    async def callback(self, interaction):
        update_config(interaction.guild.id, self.system, **{self.field: self.values[0].id})
        await interaction.response.send_message("✅ Cargo atualizado.", ephemeral=True)


class URLModal(discord.ui.Modal, title="Configurar URL da Embed"):
    url = discord.ui.TextInput(label="URL da imagem", placeholder="https://...", required=False, max_length=500)
    def __init__(self, system):
        super().__init__()
        self.system = system
    async def on_submit(self, interaction):
        update_config(interaction.guild.id, self.system, embed_url=str(self.url).strip())
        await interaction.response.send_message("✅ URL atualizada.", ephemeral=True)


class NamePatternModal(discord.ui.Modal, title="Configurar Padrão de Nome"):
    pattern = discord.ui.TextInput(label="Padrão", placeholder="{id} | {nome}", max_length=50)
    async def on_submit(self, interaction):
        value = str(self.pattern).strip()
        if "{nome}" not in value:
            return await interaction.response.send_message("❌ O padrão precisa conter `{nome}`.", ephemeral=True)
        update_config(interaction.guild.id, "registro", name_pattern=value)
        await interaction.response.send_message("✅ Padrão atualizado.", ephemeral=True)


class LaundryRateModal(discord.ui.Modal, title="Taxa de Lavagem"):
    rate = discord.ui.TextInput(label="Taxa (%)", placeholder="25", max_length=8)
    async def on_submit(self, interaction):
        try:
            rate = float(str(self.rate).replace(",", "."))
            if not 0 <= rate <= 100: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Taxa inválida.", ephemeral=True)
        update_config(interaction.guild.id, "lavagem", laundry_rate=rate)
        await interaction.response.send_message("✅ Taxa atualizada.", ephemeral=True)


class PartnerDiscountModal(discord.ui.Modal, title="Desconto de Parceria"):
    discount = discord.ui.TextInput(label="Desconto (%)", placeholder="10", max_length=8)
    async def on_submit(self, interaction):
        try:
            rate = float(str(self.discount).replace(",", "."))
            if not 0 <= rate <= 100: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Desconto inválido.", ephemeral=True)
        update_config(interaction.guild.id, "vendas", partner_discount=rate)
        await interaction.response.send_message("✅ Desconto atualizado.", ephemeral=True)


class ProductModal(discord.ui.Modal, title="Adicionar Produto"):
    name = discord.ui.TextInput(label="Nome do produto", placeholder="Ex: Produto A", max_length=80)
    price = discord.ui.TextInput(label="Preço unitário", placeholder="Ex: 90000", max_length=20)
    async def on_submit(self, interaction):
        try:
            price = parse_money(self.price)
            if price < 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Preço inválido.", ephemeral=True)
        cfg = get_config(interaction.guild.id, "vendas")
        products = [p for p in cfg.get("products", []) if p.get("name", "").lower() != str(self.name).lower()]
        products.append({"name": str(self.name), "price": price})
        update_config(interaction.guild.id, "vendas", products=products)
        await interaction.response.send_message(f"✅ Produto **{self.name}** adicionado.", ephemeral=True)


class WelcomeMessageModal(discord.ui.Modal, title="Mensagem de Boas Vindas"):
    message = discord.ui.TextInput(
        label="Mensagem",
        placeholder="Bem-vindo(a), {membro}!",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    async def on_submit(self, interaction):
        update_config(interaction.guild.id, "boas_vindas", welcome_message=str(self.message))
        await interaction.response.send_message("✅ Mensagem de boas-vindas atualizada.", ephemeral=True)



class GenericChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, system, field, placeholder):
        self.system = system
        self.field = field
        super().__init__(
            placeholder=placeholder,
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction):
        update_config(
            interaction.guild.id,
            self.system,
            **{self.field: self.values[0].id}
        )
        await interaction.response.send_message("✅ Canal atualizado.", ephemeral=True)


class MultiRoleFieldSelect(discord.ui.RoleSelect):
    def __init__(self, system, field, placeholder, max_values=10):
        self.system = system
        self.field = field
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=max_values
        )

    async def callback(self, interaction):
        update_config(
            interaction.guild.id,
            self.system,
            **{self.field: [r.id for r in self.values]}
        )
        await interaction.response.send_message("✅ Cargos atualizados.", ephemeral=True)


class RankingPointsModal(discord.ui.Modal, title="Configurar Pontuação"):
    sale_points = discord.ui.TextInput(
        label="Pontos por venda",
        placeholder="2",
        max_length=6
    )
    register_points = discord.ui.TextInput(
        label="Pontos por registro aprovado",
        placeholder="5",
        max_length=6
    )
    farm_divisor = discord.ui.TextInput(
        label="Divisor do Farm",
        placeholder="100 = 1 ponto a cada 100 itens",
        max_length=8
    )

    async def on_submit(self, interaction):
        try:
            sale = int(str(self.sale_points))
            reg = int(str(self.register_points))
            divisor = int(str(self.farm_divisor))
            if sale < 0 or reg < 0 or divisor <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Valores inválidos.",
                ephemeral=True
            )

        update_config(
            interaction.guild.id,
            "ranking",
            sale_points=sale,
            register_points=reg,
            farm_points_divisor=divisor
        )
        await interaction.response.send_message("✅ Pontuação atualizada.", ephemeral=True)


class SecurityLimitsModal(discord.ui.Modal, title="Limites de Segurança"):
    spam_count = discord.ui.TextInput(label="Mensagens para detectar spam", placeholder="6", max_length=4)
    spam_window = discord.ui.TextInput(label="Janela do spam (segundos)", placeholder="5", max_length=4)
    spam_timeout = discord.ui.TextInput(label="Timeout aplicado (segundos)", placeholder="45", max_length=5)
    raid_count = discord.ui.TextInput(label="Entradas para detectar raid", placeholder="10", max_length=4)
    raid_window = discord.ui.TextInput(label="Janela do raid (segundos)", placeholder="15", max_length=4)

    async def on_submit(self, interaction):
        try:
            values = [int(str(x)) for x in (
                self.spam_count, self.spam_window, self.spam_timeout,
                self.raid_count, self.raid_window
            )]
            if any(v <= 0 for v in values):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Valores inválidos.", ephemeral=True)

        update_config(
            interaction.guild.id,
            "seguranca",
            spam_count=values[0],
            spam_window=values[1],
            spam_timeout=values[2],
            raid_count=values[3],
            raid_window=values[4]
        )
        await interaction.response.send_message("✅ Limites de segurança atualizados.", ephemeral=True)


class BotStatusModal(discord.ui.Modal, title="Alterar Status do Bot"):
    status = discord.ui.TextInput(label="Status", placeholder="Gerenciando a facção", max_length=100)

    async def on_submit(self, interaction):
        await bot.change_presence(activity=discord.Game(name=str(self.status)))
        await interaction.response.send_message("✅ Status atualizado.", ephemeral=True)


class BotNicknameModal(discord.ui.Modal, title="Alterar Nome no Servidor"):
    nickname = discord.ui.TextInput(label="Nome do bot", placeholder="Bot Facção", max_length=32)

    async def on_submit(self, interaction):
        try:
            await interaction.guild.me.edit(nick=str(self.nickname))
            await interaction.response.send_message("✅ Nome do bot atualizado neste servidor.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não consegui alterar meu nome. Verifique minhas permissões.",
                ephemeral=True
            )


class SimpleEmbedModal(discord.ui.Modal, title="Criar Embed"):
    titulo = discord.ui.TextInput(label="Título", max_length=200)
    descricao = discord.ui.TextInput(
        label="Descrição",
        style=discord.TextStyle.paragraph,
        max_length=3500
    )

    async def on_submit(self, interaction):
        await interaction.response.send_message(
            "Escolha o canal onde deseja enviar:",
            view=EmbedTargetChannelView(str(self.titulo), str(self.descricao)),
            ephemeral=True
        )


class EmbedTargetSelect(discord.ui.ChannelSelect):
    def __init__(self, title, description):
        self.title_text = title
        self.description_text = description
        super().__init__(
            placeholder="Selecione o canal",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction):
        selected = self.values[0]
        ch = interaction.guild.get_channel(int(selected.id))
        if ch is None:
            try:
                ch = await interaction.guild.fetch_channel(int(selected.id))
            except Exception:
                ch = None
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("❌ Canal inválido.", ephemeral=True)

        await ch.send(embed=embed(self.title_text, self.description_text))
        await interaction.response.send_message(f"✅ Embed enviada em {ch.mention}.", ephemeral=True)


class EmbedTargetChannelView(discord.ui.View):
    def __init__(self, title, description):
        super().__init__(timeout=120)
        self.add_item(EmbedTargetSelect(title, description))


class AnnouncementModal(discord.ui.Modal, title="Anúncio no Privado"):
    titulo = discord.ui.TextInput(label="Título", max_length=200)
    mensagem = discord.ui.TextInput(label="Mensagem", style=discord.TextStyle.paragraph, max_length=1800)

    def __init__(self, role_id):
        super().__init__()
        self.role_id = int(role_id)

    async def on_submit(self, interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message("❌ Cargo não encontrado.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        sent = 0
        failed = 0
        e = embed(str(self.titulo), str(self.mensagem))

        for member in role.members:
            if member.bot:
                continue
            try:
                await member.send(embed=e)
                sent += 1
                await asyncio.sleep(0.25)
            except Exception:
                failed += 1

        await interaction.followup.send(
            f"✅ Enviados: **{sent}**\n❌ Falhas/DM fechada: **{failed}**",
            ephemeral=True
        )


class AnnouncementRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o cargo alvo", min_values=1, max_values=1)

    async def callback(self, interaction):
        await interaction.response.send_modal(AnnouncementModal(self.values[0].id))


class AnnouncementRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(AnnouncementRoleSelect())


class PurgeAmountModal(discord.ui.Modal, title="Limpar Mensagens"):
    quantidade = discord.ui.TextInput(label="Quantidade", placeholder="20", max_length=3)

    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = int(channel_id)

    async def on_submit(self, interaction):
        try:
            qty = int(str(self.quantidade))
            if qty <= 0 or qty > 100:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Use um número de 1 a 100.", ephemeral=True)

        ch = interaction.guild.get_channel(self.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("❌ Canal inválido.", ephemeral=True)

        try:
            deleted = await ch.purge(limit=qty)
            await interaction.response.send_message(
                f"✅ **{len(deleted)}** mensagens removidas em {ch.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Sem permissão para limpar esse canal.", ephemeral=True)


class PurgeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Escolha o canal",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction):
        await interaction.response.send_modal(PurgeAmountModal(self.values[0].id))


class PurgeChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(PurgeChannelSelect())


async def ranking_embed_for_guild(guild):
    conn = connect()
    rows = conn.execute(
        "SELECT user_id,pontos FROM pontos WHERE guild_id=? ORDER BY pontos DESC LIMIT 15",
        (guild.id,)
    ).fetchall()
    conn.close()
    lines = [f"**{i+1}.** <@{r['user_id']}> — **{r['pontos']} pts**" for i, r in enumerate(rows)]
    return embed("🏆 Ranking Geral", "\n".join(lines) or "Sem pontuação registrada.", guild_id=guild.id)


async def hierarchy_embed_for_guild(guild):
    cfg = get_config(guild.id, "hierarquia")
    role_ids = cfg.get("hierarchy_role_ids", [])
    roles = [guild.get_role(int(rid)) for rid in role_ids]
    roles = [r for r in roles if r]

    if not roles:
        return embed(
            "🏰 Hierarquia",
            "Nenhum cargo foi configurado ainda.\nUse `/gerenciar` → Hierarquia → Configurações Específicas.",
            guild_id=guild.id
        )

    lines = []
    for role in roles:
        members = [m.mention for m in role.members[:12]]
        value = ", ".join(members) if members else "Nenhum membro"
        if len(role.members) > 12:
            value += f" e +{len(role.members)-12}"
        lines.append(f"**{role.mention}**\n{value}")

    return embed("🏰 Hierarquia da Organização", "\n\n".join(lines), guild_id=guild.id)


class HierarquiaPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Atualizar Hierarquia",
        emoji="🏰",
        style=discord.ButtonStyle.secondary,
        custom_id="public:hierarquia:refresh"
    )
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(
            embed=await hierarchy_embed_for_guild(interaction.guild),
            view=self
        )


class RankingPublicPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Atualizar Ranking",
        emoji="🏆",
        style=discord.ButtonStyle.secondary,
        custom_id="public:ranking:refresh"
    )
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(
            embed=await ranking_embed_for_guild(interaction.guild),
            view=self
        )


class BackupRestoreConfirm(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=60)
        self.author_id = int(author_id)

    @discord.ui.button(label="Restaurar Configurações", emoji="⚠️", style=discord.ButtonStyle.danger)
    async def restore(self, interaction, button):
        if interaction.user.id != self.author_id:
            return await deny(interaction)

        path = BACKUP_DIR / f"{interaction.guild.id}.json"
        if not path.exists():
            return await interaction.response.send_message("❌ Nenhum backup encontrado.", ephemeral=True)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            configs = data.get("configs", {})
            for system, cfg in configs.items():
                if system in SYSTEMS and isinstance(cfg, dict):
                    save_config(interaction.guild.id, system, cfg)
            await interaction.response.edit_message(
                content="✅ Configurações restauradas a partir do último backup.",
                view=None
            )
        except Exception as exc:
            await interaction.response.edit_message(
                content=f"❌ Falha ao restaurar: `{type(exc).__name__}`",
                view=None
            )



class FarmItemAddModal(discord.ui.Modal, title="Adicionar Item de Farm"):
    item_name = discord.ui.TextInput(
        label="Nome do item",
        placeholder="Ex: Munição, Cápsula, Pólvora...",
        max_length=80
    )

    async def on_submit(self, interaction):
        name = str(self.item_name).strip()
        if not name:
            return await interaction.response.send_message("❌ Informe um nome.", ephemeral=True)

        cfg = get_config(interaction.guild.id, "farm")
        items = [str(x) for x in cfg.get("farm_items", [])]
        if name.lower() not in {x.lower() for x in items}:
            items.append(name)
        update_config(interaction.guild.id, "farm", farm_items=items[:25])

        await interaction.response.send_message(
            f"✅ **{name}** adicionado às opções de Farm.",
            ephemeral=True
        )


class StockItemAddModal(discord.ui.Modal, title="Adicionar Item ao Baú"):
    item_name = discord.ui.TextInput(
        label="Nome do item",
        placeholder="Ex: Munição, Kit, Material...",
        max_length=80
    )

    async def on_submit(self, interaction):
        name = str(self.item_name).strip()
        if not name:
            return await interaction.response.send_message("❌ Informe um nome.", ephemeral=True)

        cfg = get_config(interaction.guild.id, "bau")
        items = [str(x) for x in cfg.get("stock_items", [])]
        if name.lower() not in {x.lower() for x in items}:
            items.append(name)

        update_config(interaction.guild.id, "bau", stock_items=items[:25])
        await interaction.response.send_message(
            f"✅ **{name}** adicionado às opções do Baú.",
            ephemeral=True
        )


class ThemeColorModal(discord.ui.Modal, title="Cor Principal do Bot"):
    color_hex = discord.ui.TextInput(
        label="Cor HEX",
        placeholder="#C89B3C",
        max_length=7
    )

    async def on_submit(self, interaction):
        raw = str(self.color_hex).strip()
        normalized = raw if raw.startswith("#") else f"#{raw}"
        try:
            value = parse_hex_color(normalized)
            if len(normalized.replace("#", "")) not in {3, 6}:
                raise ValueError
        except Exception:
            return await interaction.response.send_message(
                "❌ Cor inválida. Use algo como `#C89B3C`, `#5865F2` ou `#00FF88`.",
                ephemeral=True
            )

        update_config(interaction.guild.id, "personalizacao", theme_color=normalized.upper())
        await interaction.response.send_message(
            embed=embed(
                "🎨 Cor Atualizada",
                f"A nova cor principal é **{normalized.upper()}**.",
                value,
                guild_id=interaction.guild.id
            ),
            ephemeral=True
        )


class MessageImageModal(discord.ui.Modal, title="Imagem das Mensagens"):
    image_url = discord.ui.TextInput(
        label="Banner dos painéis (URL)",
        placeholder="https://...",
        required=False,
        max_length=500
    )
    thumbnail_url = discord.ui.TextInput(
        label="Logo pequena / miniatura (URL)",
        placeholder="https://...",
        required=False,
        max_length=500
    )
    footer_text = discord.ui.TextInput(
        label="Texto do rodapé",
        placeholder="Nome da facção • Bot Facção",
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction):
        image_url = str(self.image_url).strip()
        thumb_url = str(self.thumbnail_url).strip()
        footer = str(self.footer_text).strip()

        for url in (image_url, thumb_url):
            if url and not (url.startswith("http://") or url.startswith("https://")):
                return await interaction.response.send_message(
                    "❌ As imagens precisam usar uma URL começando com `http://` ou `https://`.",
                    ephemeral=True
                )

        update_config(
            interaction.guild.id,
            "personalizacao",
            message_image_url=image_url,
            message_thumbnail_url=thumb_url,
            message_footer_text=footer
        )

        await interaction.response.send_message(
            embed=embed(
                "🖼️ Aparência Atualizada",
                "Imagem, miniatura e rodapé foram atualizados. A imagem grande será usada nos painéis principais.",
                guild_id=interaction.guild.id,
                use_theme_image=True,
                use_theme_thumbnail=True
            ),
            ephemeral=True
        )


class ThemePreviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Ver Painel de Exemplo", emoji="👁️", style=discord.ButtonStyle.secondary)
    async def preview(self, interaction, button):
        await interaction.response.send_message(
            embed=embed(
                "✨ Prévia do Tema",
                "A imagem grande aparece nos painéis principais. Nas respostas menores fica apenas a miniatura.",
                guild_id=interaction.guild.id,
                use_theme_image=True,
                use_theme_thumbnail=True
            ),
            ephemeral=True
        )

class SpecialOptionsView(discord.ui.View):
    def __init__(self, system):
        super().__init__(timeout=180)
        self.system = system

        if system == "boas_vindas":
            self.add_item(SpecialActionButton(system, "welcome_message", "Mensagem", "💬"))
            self.add_item(SpecialActionButton(system, "welcome_channel", "Canal Público", "📢"))
            self.add_item(SpecialActionButton(system, "welcome_test", "Testar Boas-vindas", "🧪"))

        elif system == "registro":
            self.add_item(SpecialActionButton(system, "pattern", "Padrão de Nome", "🪪"))
            self.add_item(SpecialActionButton(system, "approved_role", "Cargo Aprovado", "🎭"))
            self.add_item(SpecialActionButton(system, "visitor_role", "Cargo Visitante", "🧳"))
            self.add_item(SpecialActionButton(system, "visitor_toggle", "Ativar/Desativar Visitante", "🔄"))

        elif system == "vendas":
            self.add_item(SpecialActionButton(system, "product", "Adicionar Produto", "📦"))
            self.add_item(SpecialActionButton(system, "products_list", "Ver Catálogo", "📋"))
            self.add_item(SpecialActionButton(system, "products_clear", "Limpar Catálogo", "🗑️"))
            self.add_item(SpecialActionButton(system, "discount", "Desconto Parceria", "🤝"))

        elif system == "banco":
            self.add_item(SpecialActionButton(system, "bank_summary", "Resumo do Banco", "🏦"))

        elif system == "farm":
            self.add_item(SpecialActionButton(system, "farm_add_item", "Adicionar Item", "➕"))
            self.add_item(SpecialActionButton(system, "farm_items_list", "Ver Itens", "📋"))
            self.add_item(SpecialActionButton(system, "farm_items_clear", "Limpar Itens", "🗑️"))
            self.add_item(SpecialActionButton(system, "farm_rank", "Ver Ranking", "🏆"))
            self.add_item(SpecialActionButton(system, "farm_pdf", "Gerar PDF", "📄"))

        elif system == "acoes":
            self.add_item(SpecialActionButton(system, "actions_open", "Ações Abertas", "🎯"))
            self.add_item(SpecialActionButton(system, "actions_history", "Histórico", "📜"))
            self.add_item(SpecialActionButton(system, "action_ping_role", "Cargo para Ping", "📣"))

        elif system == "hierarquia":
            self.add_item(SpecialActionButton(system, "hierarchy_roles", "Cargos da Hierarquia", "🏰"))
            self.add_item(SpecialActionButton(system, "hierarchy_preview", "Prévia da Hierarquia", "👁️"))

        elif system == "ausencia":
            self.add_item(SpecialActionButton(system, "absence_pending", "Ver Pendentes", "⌛"))

        elif system == "lavagem":
            self.add_item(SpecialActionButton(system, "laundry", "Taxa de Lavagem", "📊"))

        elif system == "encomendas":
            self.add_item(SpecialActionButton(system, "orders_pending", "Ver Pendentes", "📦"))

        elif system == "bau":
            self.add_item(SpecialActionButton(system, "stock_add_item", "Adicionar Item", "➕"))
            self.add_item(SpecialActionButton(system, "stock_items_list", "Ver Itens", "📋"))
            self.add_item(SpecialActionButton(system, "stock_items_clear", "Limpar Itens", "🗑️"))
            self.add_item(SpecialActionButton(system, "leader_roles", "Cargos de Líder", "👑"))
            self.add_item(SpecialActionButton(system, "stock_preview", "Ver Estoque", "🧰"))

        elif system == "advertencias":
            self.add_item(SpecialActionButton(system, "warnings_panel", "Abrir Painel", "⚠️"))
            self.add_item(SpecialActionButton(system, "warnings_summary", "Resumo", "📊"))

        elif system == "ranking":
            self.add_item(SpecialActionButton(system, "ranking_points", "Configurar Pontos", "⚙️"))
            self.add_item(SpecialActionButton(system, "ranking_preview", "Ver Ranking", "🏆"))

        elif system == "metas":
            self.add_item(SpecialActionButton(system, "metas_config", "Configurar Metas", "🎯"))
            self.add_item(SpecialActionButton(system, "metas_rank", "Ranking Semanal", "🏆"))

        elif system == "promocoes":
            self.add_item(SpecialActionButton(system, "promocoes_info", "Como Funciona", "⬆️"))

        elif system == "inicio":
            self.add_item(SpecialActionButton(system, "inicio_preview", "Prévia do Comece Aqui", "👋"))

        elif system == "logs":
            self.add_item(SpecialActionButton(system, "logs_test", "Testar Canal de Logs", "🧪"))

        elif system == "seguranca":
            self.add_item(SpecialActionButton(system, "security_limits", "Limites de Segurança", "🛡️"))

        elif system == "backup":
            self.add_item(SpecialActionButton(system, "create_backup", "Criar Backup Agora", "💾"))
            self.add_item(SpecialActionButton(system, "restore_backup", "Restaurar Configurações", "♻️"))

        elif system == "personalizacao":
            self.add_item(SpecialActionButton(system, "theme_color", "Cor Principal", "🎨"))
            self.add_item(SpecialActionButton(system, "message_image", "Imagem das Mensagens", "🖼️"))
            self.add_item(SpecialActionButton(system, "theme_preview", "Prévia do Tema", "👁️"))
            self.add_item(SpecialActionButton(system, "bot_status", "Status do Bot", "🎮"))
            self.add_item(SpecialActionButton(system, "bot_nickname", "Nome no Servidor", "✏️"))

        elif system == "utilidades":
            self.add_item(SpecialActionButton(system, "embed_creator", "Criador de Embed", "🎨"))
            self.add_item(SpecialActionButton(system, "dm_announcement", "Anúncio Privado", "📢"))
            self.add_item(SpecialActionButton(system, "purge_messages", "Limpar Mensagens", "🧹"))


class SpecialActionButton(discord.ui.Button):
    def __init__(self, system, action, label, emoji):
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary)
        self.system = system
        self.action = action

    async def callback(self, interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)

        action = self.action

        if action == "pattern":
            return await interaction.response.send_modal(NamePatternModal())

        if action == "approved_role":
            v = discord.ui.View(timeout=120)
            v.add_item(SingleRoleSelect("registro", "approved_role_id", "Selecione o cargo pós-aprovação"))
            return await interaction.response.send_message("Escolha o cargo:", view=v, ephemeral=True)

        if action == "visitor_role":
            v = discord.ui.View(timeout=120)
            v.add_item(SingleRoleSelect("registro", "visitor_role_id", "Selecione o cargo visitante"))
            return await interaction.response.send_message("Escolha o cargo:", view=v, ephemeral=True)

        if action == "visitor_toggle":
            cfg = get_config(interaction.guild.id, "registro")
            update_config(
                interaction.guild.id,
                "registro",
                visitor_enabled=not cfg.get("visitor_enabled")
            )
            return await interaction.response.send_message("✅ Visitante atualizado.", ephemeral=True)

        if action == "product":
            return await interaction.response.send_modal(ProductModal())

        if action == "products_list":
            cfg = get_config(interaction.guild.id, "vendas")
            products = cfg.get("products", [])
            lines = [
                f"**{i+1}. {p.get('name', 'Produto')}** — {money(float(p.get('price', 0)))}"
                for i, p in enumerate(products)
            ]
            return await interaction.response.send_message(
                embed=embed("📋 Catálogo de Produtos", "\n".join(lines) or "Nenhum produto cadastrado.", guild_id=interaction.guild.id),
                ephemeral=True
            )

        if action == "products_clear":
            update_config(interaction.guild.id, "vendas", products=[])
            return await interaction.response.send_message("✅ Catálogo limpo.", ephemeral=True)

        if action == "discount":
            return await interaction.response.send_modal(PartnerDiscountModal())

        if action == "laundry":
            return await interaction.response.send_modal(LaundryRateModal())

        if action == "welcome_message":
            return await interaction.response.send_modal(WelcomeMessageModal())

        if action == "welcome_channel":
            v = discord.ui.View(timeout=120)
            v.add_item(GenericChannelSelect("boas_vindas", "welcome_channel_id", "Selecione o canal público"))
            return await interaction.response.send_message("Escolha o canal:", view=v, ephemeral=True)

        if action == "welcome_test":
            cfg = get_config(interaction.guild.id, "boas_vindas")
            msg = str(cfg.get("welcome_message", "Bem-vindo(a), {membro}!"))
            msg = msg.replace("{membro}", interaction.user.mention).replace("{servidor}", interaction.guild.name)
            return await interaction.response.send_message(
                embed=embed("🏠 Teste de Boas-vindas", msg, GREEN, cfg.get("embed_url", ""), guild_id=interaction.guild.id),
                ephemeral=True
            )

        if action == "bank_summary":
            conn = connect()
            rows = conn.execute(
                "SELECT tipo,valor FROM banco WHERE guild_id=?",
                (interaction.guild.id,)
            ).fetchall()
            conn.close()
            entradas = sum(float(r["valor"]) for r in rows if r["tipo"] == "entrada")
            saidas = sum(float(r["valor"]) for r in rows if r["tipo"] == "saida")
            return await interaction.response.send_message(
                embed=embed(
                    "🏦 Resumo do Banco",
                    f"**Entradas:** {money(entradas)}\n**Saídas:** {money(saidas)}\n**Saldo:** {money(entradas-saidas)}"
                ),
                ephemeral=True
            )

        if action == "farm_add_item":
            return await interaction.response.send_modal(FarmItemAddModal())

        if action == "farm_items_list":
            cfg = get_config(interaction.guild.id, "farm")
            items = cfg.get("farm_items", [])
            lines = [f"**{i+1}.** {item}" for i, item in enumerate(items)]
            return await interaction.response.send_message(
                embed=embed(
                    "📋 Itens disponíveis no Farm",
                    "\n".join(lines) or "Nenhum item cadastrado.",
                    guild_id=interaction.guild.id
                ),
                ephemeral=True
            )

        if action == "farm_items_clear":
            update_config(interaction.guild.id, "farm", farm_items=[])
            return await interaction.response.send_message(
                "✅ Lista de itens do Farm limpa.",
                ephemeral=True
            )

        if action == "farm_rank":
            conn = connect()
            rows = conn.execute(
                """SELECT user_id,SUM(quantidade) total FROM farms
                   WHERE guild_id=? AND status='aprovado'
                   GROUP BY user_id ORDER BY total DESC LIMIT 15""",
                (interaction.guild.id,)
            ).fetchall()
            conn.close()
            lines = [f"**{i+1}.** <@{r['user_id']}> — **{r['total']}**" for i, r in enumerate(rows)]
            return await interaction.response.send_message(
                embed=embed("🏆 Ranking de Farm", "\n".join(lines) or "Sem farms aprovados.", guild_id=interaction.guild.id),
                ephemeral=True
            )

        if action == "farm_pdf":
            await interaction.response.defer(ephemeral=True)
            conn = connect()
            rows = conn.execute(
                "SELECT user_id,item,quantidade,status,created_at FROM farms WHERE guild_id=? ORDER BY id DESC LIMIT 500",
                (interaction.guild.id,)
            ).fetchall()
            conn.close()
            lines = [
                f"{r['created_at'][:10]} | {r['user_id']} | {r['item']} | {r['quantidade']} | {r['status']}"
                for r in rows
            ]
            return await interaction.followup.send(
                file=discord.File(simple_pdf(f"Relatorio de Farm - {FAC_NAME}", lines), filename="relatorio_farm.pdf"),
                ephemeral=True
            )

        if action == "actions_open":
            return await interaction.response.send_message(
                embed=build_actions_list_embed(interaction.guild, only_open=True),
                view=ActionBrowserView(interaction.guild.id, only_open=True),
                ephemeral=True
            )

        if action == "actions_history":
            return await interaction.response.send_message(
                embed=build_actions_list_embed(interaction.guild, only_open=False),
                view=ActionBrowserView(interaction.guild.id, only_open=False),
                ephemeral=True
            )

        if action == "action_ping_role":
            v = discord.ui.View(timeout=120)
            v.add_item(SingleRoleSelect("acoes", "action_ping_role_id", "Selecione o cargo para ping"))
            return await interaction.response.send_message("Escolha o cargo:", view=v, ephemeral=True)

        if action == "hierarchy_roles":
            v = discord.ui.View(timeout=120)
            v.add_item(MultiRoleFieldSelect("hierarquia", "hierarchy_role_ids", "Selecione os cargos da hierarquia", 10))
            return await interaction.response.send_message("Escolha os cargos:", view=v, ephemeral=True)

        if action == "hierarchy_preview":
            return await interaction.response.send_message(
                embed=await hierarchy_embed_for_guild(interaction.guild),
                ephemeral=True
            )

        if action == "absence_pending":
            conn = connect()
            rows = conn.execute(
                "SELECT user_id,periodo,motivo FROM ausencias WHERE guild_id=? AND status='pendente' ORDER BY id DESC LIMIT 15",
                (interaction.guild.id,)
            ).fetchall()
            conn.close()
            lines = [f"<@{r['user_id']}> • **{r['periodo']}**\n{r['motivo']}" for r in rows]
            return await interaction.response.send_message(
                embed=embed("⌛ Ausências Pendentes", "\n\n".join(lines) or "Nenhuma solicitação pendente.", guild_id=interaction.guild.id),
                ephemeral=True
            )

        if action == "orders_pending":
            conn = connect()
            rows = conn.execute(
                """SELECT responsavel_id,descricao,data_hora,destinatario
                   FROM encomendas WHERE guild_id=? AND status='pendente'
                   ORDER BY id DESC LIMIT 15""",
                (interaction.guild.id,)
            ).fetchall()
            conn.close()
            lines = [
                f"**Responsável:** <@{r['responsavel_id']}>\n**Data:** {r['data_hora']}\n**Destino:** {r['destinatario']}\n{r['descricao']}"
                for r in rows
            ]
            return await interaction.response.send_message(
                embed=embed("📦 Encomendas Pendentes", "\n\n".join(lines) or "Nenhuma encomenda pendente.", guild_id=interaction.guild.id),
                ephemeral=True
            )

        if action == "stock_add_item":
            return await interaction.response.send_modal(StockItemAddModal())

        if action == "stock_items_list":
            cfg = get_config(interaction.guild.id, "bau")
            items = cfg.get("stock_items", [])
            lines = [f"**{i+1}.** {item}" for i, item in enumerate(items)]
            return await interaction.response.send_message(
                embed=embed(
                    "📋 Itens do Baú",
                    "\n".join(lines) or "Nenhum item configurado.",
                    guild_id=interaction.guild.id
                ),
                ephemeral=True
            )

        if action == "stock_items_clear":
            update_config(interaction.guild.id, "bau", stock_items=[])
            return await interaction.response.send_message("✅ Lista de itens do Baú limpa.", ephemeral=True)

        if action == "leader_roles":
            v = discord.ui.View(timeout=120)
            v.add_item(MultiRoleFieldSelect("bau", "leader_role_ids", "Selecione cargos de líder", 5))
            return await interaction.response.send_message("Escolha os cargos:", view=v, ephemeral=True)

        if action == "stock_preview":
            conn = connect()
            rows = conn.execute(
                "SELECT bau,item,quantidade FROM estoque WHERE guild_id=? ORDER BY bau,item",
                (interaction.guild.id,)
            ).fetchall()
            conn.close()
            lines = [f"`{r['bau'].upper():5}` **{r['item']}** — {r['quantidade']}" for r in rows[:40]]
            return await interaction.response.send_message(
                embed=embed("🧰 Estoque Atual", "\n".join(lines) or "Estoque vazio.", guild_id=interaction.guild.id),
                ephemeral=True
            )

        if action == "warnings_panel":
            return await interaction.response.send_message(
                embed=embed(
                    "⚠️ Painel de Advertências",
                    "Selecione um membro para gerenciar as advertências.",
                    guild_id=interaction.guild.id
                ),
                view=AdvertenciasPanel(),
                ephemeral=True
            )

        if action == "warnings_summary":
            conn = connect()
            rows = conn.execute(
                """SELECT user_id,COUNT(*) total,SUM(pontos) pontos
                   FROM advertencias
                   WHERE guild_id=? AND COALESCE(active,1)=1
                   GROUP BY user_id ORDER BY pontos DESC LIMIT 15""",
                (interaction.guild.id,)
            ).fetchall()
            conn.close()
            lines = [
                f"<@{r['user_id']}> — **{r['total']} advertência(s)** • **{r['pontos'] or 0} ponto(s)**"
                for r in rows
            ]
            return await interaction.response.send_message(
                embed=embed("⚠️ Resumo de Advertências", "\n".join(lines) or "Nenhuma advertência registrada.", guild_id=interaction.guild.id),
                ephemeral=True
            )

        if action == "ranking_points":
            return await interaction.response.send_modal(RankingPointsModal())

        if action == "ranking_preview":
            return await interaction.response.send_message(
                embed=await ranking_embed_for_guild(interaction.guild),
                ephemeral=True
            )

        if action == "metas_config":
            return await interaction.response.send_modal(WeeklyGoalsModal())

        if action == "metas_rank":
            return await interaction.response.send_message(
                embed=weekly_ranking_embed(interaction.guild),
                ephemeral=True
            )

        if action == "promocoes_info":
            return await interaction.response.send_message(
                embed=embed(
                    "⬆️ Sistema de Promoções",
                    (
                        "A liderança pode usar **/analisar-promocao** e selecionar um membro.\n\n"
                        "A análise considera **Farm**, **Vendas**, **participação em Ações**, "
                        "**Ranking** e **Advertências ativas**.\n"
                        "O bot apenas recomenda; a decisão continua com a liderança."
                    ),
                    guild_id=interaction.guild.id,
                    use_theme_image=False,
                    use_theme_thumbnail=True
                ),
                ephemeral=True
            )

        if action == "inicio_preview":
            return await interaction.response.send_message(
                embed=comece_aqui_embed(interaction.guild),
                view=ComeceAquiView(),
                ephemeral=True
            )

        if action == "logs_test":
            await log_event(
                interaction.guild,
                "logs",
                "🧪 Teste de Logs",
                f"Teste realizado por {interaction.user.mention}.",
                GREEN
            )
            return await interaction.response.send_message(
                "✅ Teste enviado ao canal configurado em Logs.",
                ephemeral=True
            )

        if action == "security_limits":
            return await interaction.response.send_modal(SecurityLimitsModal())

        if action == "create_backup":
            path = await create_backup(interaction.guild)
            return await interaction.response.send_message(
                "✅ Backup criado.",
                file=discord.File(path),
                ephemeral=True
            )

        if action == "restore_backup":
            path = BACKUP_DIR / f"{interaction.guild.id}.json"
            if not path.exists():
                return await interaction.response.send_message("❌ Nenhum backup encontrado.", ephemeral=True)
            return await interaction.response.send_message(
                "⚠️ Restaurar as configurações salvas no último backup?",
                view=BackupRestoreConfirm(interaction.user.id),
                ephemeral=True
            )

        if action == "theme_color":
            return await interaction.response.send_modal(ThemeColorModal())

        if action == "message_image":
            return await interaction.response.send_modal(MessageImageModal())

        if action == "theme_preview":
            return await interaction.response.send_message(
                "Prévia atual do tema:",
                view=ThemePreviewView(),
                ephemeral=True
            )

        if action == "bot_status":
            return await interaction.response.send_modal(BotStatusModal())

        if action == "bot_nickname":
            return await interaction.response.send_modal(BotNicknameModal())

        if action == "embed_creator":
            return await interaction.response.send_modal(SimpleEmbedModal())

        if action == "dm_announcement":
            return await interaction.response.send_message(
                "Escolha o cargo que receberá o anúncio:",
                view=AnnouncementRoleView(),
                ephemeral=True
            )

        if action == "purge_messages":
            return await interaction.response.send_message(
                "Escolha o canal que deseja limpar:",
                view=PurgeChannelView(),
                ephemeral=True
            )

        await interaction.response.send_message("✅ Opção executada.", ephemeral=True)


class PanelChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, system):
        self.system = system
        super().__init__(
            placeholder="Escolha o canal do painel",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction):
        # ChannelSelect pode retornar um AppCommandChannel.
        # Ele tem ID/mention, mas NÃO possui o método .send().
        selected = self.values[0]
        channel_id = int(selected.id)

        # Resolve o ID para um canal real do servidor.
        ch = interaction.guild.get_channel(channel_id)
        if ch is None:
            try:
                ch = await interaction.guild.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                ch = None

        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Não consegui acessar esse canal de texto. "
                "Verifique se o bot possui **Ver Canal** e **Enviar Mensagens**.",
                ephemeral=True
            )

        try:
            await send_public_panel(interaction.guild, ch, self.system)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Não tenho permissão para enviar mensagens nesse canal.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            return await interaction.response.send_message(
                f"❌ O Discord recusou o envio do painel (`HTTP {e.status}`).",
                ephemeral=True
            )

        update_config(
            interaction.guild.id,
            self.system,
            public_channel_id=channel_id
        )

        await interaction.response.send_message(
            f"✅ Painel enviado em {ch.mention}.",
            ephemeral=True
        )


class PanelChannelView(discord.ui.View):
    def __init__(self, system):
        super().__init__(timeout=120)
        self.add_item(PanelChannelSelect(system))

# ============================================================
# PAINÉIS PÚBLICOS
# ============================================================

async def send_public_panel(guild, channel, system):
    meta = SYSTEMS.get(system, {"label": str(system).title(), "emoji": "⚙️", "description": "Sistema administrativo.", "public_title": "⚙️ SISTEMA", "public_description": "Sistema administrativo.", "has_public_panel": False})
    cfg = get_config(guild.id, system)
    e = embed(
        meta["public_title"],
        meta["public_description"],
        None,
        cfg.get("embed_url", ""),
        guild_id=guild.id,
        use_theme_image=True,
        use_theme_thumbnail=True
    )
    e.add_field(
        name="Status",
        value="🟢 Sistema disponível" if cfg["enabled"] else "🔴 Sistema indisponível",
        inline=False
    )

    view_map = {
        "registro": RegistroPanel(),
        "vendas": VendasPanel(),
        "banco": BancoPanel(),
        "lavagem": LavagemPanel(),
        "encomendas": EncomendasPanel(),
        "ausencia": AusenciaPanel(),
        "farm": FarmPanel(),
        "bau": BauPanel(),
        "acoes": AcoesPanel(),
        "hierarquia": HierarquiaPanel(),
        "ranking": RankingPublicPanel(),
        "metas": MetasPanel(),
        "inicio": ComeceAquiView(),
    }
    if system == "hierarquia":
        e = await hierarchy_embed_for_guild(guild)
    elif system == "ranking":
        e = await ranking_embed_for_guild(guild)
    elif system == "metas":
        e = weekly_ranking_embed(guild)
    elif system == "inicio":
        e = comece_aqui_embed(guild)

    view = view_map.get(system)
    if view is None:
        raise ValueError(f"O sistema {system!r} não possui painel público.")
    await channel.send(embed=e, view=view)

# ============================================================
# REGISTRO
# ============================================================

class RegistroModal(discord.ui.Modal, title="Realizar Registro"):
    nome = discord.ui.TextInput(label="Nome", placeholder="Nome do personagem", max_length=80)
    identificacao = discord.ui.TextInput(label="ID / Passaporte", placeholder="Ex: 123", max_length=30)
    telefone = discord.ui.TextInput(label="Telefone", required=False, max_length=40)
    recrutador = discord.ui.TextInput(label="Recrutador", required=False, max_length=80)

    async def on_submit(self, interaction):
        if not enabled(interaction.guild.id, "registro"):
            return await interaction.response.send_message("❌ Sistema de registro está desligado.", ephemeral=True)

        conn = connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO registros(guild_id,user_id,nome,identificacao,telefone,recrutador,status,created_at)
               VALUES(?,?,?,?,?,?,'pendente',?)""",
            (
                interaction.guild.id, interaction.user.id, str(self.nome), str(self.identificacao),
                str(self.telefone), str(self.recrutador), now_iso()
            )
        )
        rid = cur.lastrowid
        conn.commit()
        conn.close()

        e = embed("👤 Novo Registro", "Aguardando aprovação.")
        e.add_field(name="Usuário", value=interaction.user.mention, inline=False)
        e.add_field(name="Nome", value=str(self.nome), inline=True)
        e.add_field(name="ID", value=str(self.identificacao), inline=True)
        e.add_field(name="Telefone", value=str(self.telefone) or "Não informado", inline=True)
        e.add_field(name="Recrutador", value=str(self.recrutador) or "Não informado", inline=True)
        e.set_footer(text=f"REG#{rid} • {FOOTER}")

        cfg = get_config(interaction.guild.id, "registro")
        ch = interaction.guild.get_channel(int(cfg["log_channel_id"])) if cfg.get("log_channel_id") else None
        if ch:
            await ch.send(embed=e, view=ApprovalView("registro", rid, interaction.user.id))

        await interaction.response.send_message("✅ Registro enviado para análise.", ephemeral=True)

class RegistroPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Realizar Registro", emoji="👤", style=discord.ButtonStyle.primary, custom_id="public:registro")
    async def register(self, interaction, button):
        await interaction.response.send_modal(RegistroModal())

    @discord.ui.button(label="Entrar como Visitante", emoji="🧳", style=discord.ButtonStyle.secondary, custom_id="public:visitor")
    async def visitor(self, interaction, button):
        cfg = get_config(interaction.guild.id, "registro")
        if not cfg.get("visitor_enabled") or not cfg.get("visitor_role_id"):
            return await interaction.response.send_message("❌ Sistema de visitante está desativado.", ephemeral=True)
        role = interaction.guild.get_role(int(cfg["visitor_role_id"]))
        if not role:
            return await interaction.response.send_message("❌ Cargo visitante não encontrado.", ephemeral=True)
        try:
            await interaction.user.add_roles(role, reason="Acesso visitante")
            await interaction.response.send_message("✅ Cargo de visitante aplicado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Não consegui aplicar o cargo. Verifique a hierarquia.", ephemeral=True)

# ============================================================
# APROVAÇÃO GENÉRICA
# ============================================================

class ApprovalView(discord.ui.View):
    def __init__(self, system, record_id, target_id):
        super().__init__(timeout=None)
        self.system = system
        self.record_id = int(record_id)
        self.target_id = int(target_id)

    @discord.ui.button(label="Aprovar", emoji="✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction, button):
        if not can_approve(interaction.user, self.system):
            return await deny(interaction, "❌ Você não é aprovador deste sistema.")

        await self.process(interaction, True)

    @discord.ui.button(label="Reprovar", emoji="❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction, button):
        if not can_approve(interaction.user, self.system):
            return await deny(interaction, "❌ Você não é aprovador deste sistema.")

        await self.process(interaction, False)

    async def process(self, interaction, approved):
        status = "aprovado" if approved else "reprovado"
        table = {
            "registro": "registros",
            "farm": "farms",
            "ausencia": "ausencias",
            "encomendas": "encomendas"
        }[self.system]

        conn = connect()
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (self.record_id,)).fetchone()
        if not row or row["status"] != "pendente":
            conn.close()
            return await interaction.response.send_message("Esta solicitação já foi processada.", ephemeral=True)

        conn.execute(
            f"UPDATE {table} SET status=?, reviewer_id=? WHERE id=?",
            (status, interaction.user.id, self.record_id)
        )
        conn.commit()
        conn.close()

        if self.system == "registro" and approved:
            member = interaction.guild.get_member(self.target_id)
            cfg = get_config(interaction.guild.id, "registro")
            if member:
                role = interaction.guild.get_role(int(cfg["approved_role_id"])) if cfg.get("approved_role_id") else None
                try:
                    if role:
                        await member.add_roles(role, reason="Registro aprovado")
                    visitor_role = (
                        interaction.guild.get_role(int(cfg["visitor_role_id"]))
                        if cfg.get("visitor_role_id") else None
                    )
                    if visitor_role and visitor_role in member.roles:
                        await member.remove_roles(visitor_role, reason="Registro aprovado")
                    pattern = cfg.get("name_pattern", "{id} | {nome}")
                    nick = pattern.replace("{id}", str(row["identificacao"])).replace("{nome}", str(row["nome"]))[:32]
                    await member.edit(nick=nick)
                except discord.Forbidden:
                    pass
            rcfg = get_config(interaction.guild.id, "ranking")
            add_points(interaction.guild.id, self.target_id, int(rcfg.get("register_points", 5)))

        if self.system == "farm" and approved:
            rcfg = get_config(interaction.guild.id, "ranking")
            divisor = max(1, int(rcfg.get("farm_points_divisor", 100)))
            add_points(interaction.guild.id, self.target_id, max(1, int(row["quantidade"]) // divisor))

        e = interaction.message.embeds[0] if interaction.message.embeds else embed("Solicitação")
        e.color = GREEN if approved else RED
        e.add_field(
            name="Resultado",
            value=f"{'✅ Aprovado' if approved else '❌ Reprovado'} por {interaction.user.mention}",
            inline=False
        )
        if self.system == "encomendas" and approved:
            await interaction.response.edit_message(
                embed=e,
                view=OrderManageView(self.record_id)
            )
        else:
            await interaction.response.edit_message(
                embed=e,
                view=None
            )

# ============================================================
# VENDAS
# ============================================================

class ProductSelect(discord.ui.Select):
    def __init__(self, products):
        opts = [
            discord.SelectOption(
                label=p["name"][:100],
                value=str(i),
                description=money(float(p["price"]))[:100],
                emoji="📦"
            )
            for i, p in enumerate(products[:25])
        ]
        super().__init__(
            placeholder="1️⃣ Escolha o produto vendido",
            options=opts,
            min_values=1,
            max_values=1
        )


class SaleStepView(discord.ui.View):
    def __init__(self, products):
        super().__init__(timeout=180)
        self.products = products
        sel = ProductSelect(products)
        sel.callback = self.product_callback
        self.add_item(sel)

    async def product_callback(self, interaction):
        idx = int(self.children[0].values[0])
        product = self.products[idx]
        await interaction.response.edit_message(
            content=f"**Produto:** {product['name']}\\n2️⃣ Agora escolha o tipo da venda:",
            view=PartnershipChoiceView(product["name"], float(product["price"]))
        )


class PartnershipChoiceView(discord.ui.View):
    def __init__(self, product, price):
        super().__init__(timeout=180)
        self.product = product
        self.price = price

    @discord.ui.button(label="Com Parceria", emoji="🤝", style=discord.ButtonStyle.success)
    async def partner(self, interaction, button):
        await interaction.response.send_modal(
            SaleQuantityModal(self.product, self.price, True)
        )

    @discord.ui.button(label="Sem Parceria", emoji="💵", style=discord.ButtonStyle.secondary)
    async def no_partner(self, interaction, button):
        await interaction.response.send_modal(
            SaleQuantityModal(self.product, self.price, False)
        )


class SaleQuantityModal(discord.ui.Modal, title="Registrar Nova Venda"):
    quantidade = discord.ui.TextInput(
        label="Quantidade",
        placeholder="Ex: 2",
        max_length=10
    )

    def __init__(self, product, price, is_partner):
        super().__init__()
        self.product = product
        self.price = float(price)
        self.is_partner = bool(is_partner)

    async def on_submit(self, interaction):
        if not enabled(interaction.guild.id, "vendas"):
            return await interaction.response.send_message(
                "❌ Sistema de vendas está desligado.",
                ephemeral=True
            )
        if not has_access(interaction.user, "vendas"):
            return await interaction.response.send_message(
                "❌ Você não possui o cargo necessário para registrar vendas.",
                ephemeral=True
            )

        try:
            qty = parse_int(self.quantidade)
            if qty <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Quantidade inválida.",
                ephemeral=True
            )

        cfg = get_config(interaction.guild.id, "vendas")
        price = self.price
        if self.is_partner:
            price *= (1 - float(cfg.get("partner_discount", 0)) / 100)
        total = price * qty

        conn = connect()
        conn.execute(
            """INSERT INTO vendas(guild_id,user_id,produto,parceria,quantidade,unit_price,total,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                interaction.guild.id,
                interaction.user.id,
                self.product,
                int(self.is_partner),
                qty,
                price,
                total,
                now_iso()
            )
        )
        conn.commit()
        conn.close()

        rcfg = get_config(interaction.guild.id, "ranking")
        add_points(
            interaction.guild.id,
            interaction.user.id,
            int(rcfg.get("sale_points", 2))
        )

        await interaction.response.send_message(
            embed=embed(
                "✅ Venda Registrada",
                f"**Produto:** {self.product}\\n"
                f"**Quantidade:** {qty}\\n"
                f"**Parceria:** {'Sim' if self.is_partner else 'Não'}\\n"
                f"**Total:** {money(total)}",
                GREEN,
                guild_id=interaction.guild.id
            ),
            ephemeral=True
        )

        await log_event(
            interaction.guild,
            "vendas",
            "💵 Nova Venda",
            f"{interaction.user.mention}\\n"
            f"**{self.product}** x {qty}\\n"
            f"**Parceria:** {'Sim' if self.is_partner else 'Não'}\\n"
            f"**Total:** {money(total)}",
            GREEN
        )


class VendasPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Registrar Venda",
        emoji="📦",
        style=discord.ButtonStyle.secondary,
        custom_id="public:venda"
    )
    async def sale(self, interaction, button):
        cfg = get_config(interaction.guild.id, "vendas")
        products = cfg.get("products", [])

        if not enabled(interaction.guild.id, "vendas"):
            return await deny(interaction, "❌ Sistema desligado.")
        if not products:
            return await interaction.response.send_message(
                "❌ Nenhum produto cadastrado.",
                ephemeral=True
            )
        if not has_access(interaction.user, "vendas"):
            return await interaction.response.send_message(
                "❌ Você não possui o cargo necessário para registrar vendas.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "1️⃣ Selecione o produto:",
            view=SaleStepView(products),
            ephemeral=True
        )

# ============================================================
# BANCO
# ============================================================

class BankDescriptionModal(discord.ui.Modal):
    descricao = discord.ui.TextInput(
        label="Descrição",
        placeholder="Motivo da movimentação",
        max_length=200
    )

    def __init__(self, tipo, valor):
        super().__init__(title=f"{'Depositar' if tipo == 'entrada' else 'Retirar'} no Banco")
        self.tipo = tipo
        self.valor = float(valor)

    async def on_submit(self, interaction):
        if not has_access(interaction.user, "banco"):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        conn = connect()
        conn.execute(
            "INSERT INTO banco(guild_id,user_id,tipo,valor,descricao,created_at) VALUES(?,?,?,?,?,?)",
            (
                interaction.guild.id,
                interaction.user.id,
                self.tipo,
                self.valor,
                str(self.descricao),
                now_iso()
            )
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            embed=embed(
                "✅ Movimentação Registrada",
                f"**Tipo:** {'Depósito' if self.tipo == 'entrada' else 'Retirada'}\\n"
                f"**Valor:** {money(self.valor)}\\n"
                f"**Descrição:** {self.descricao}",
                GREEN,
                guild_id=interaction.guild.id
            ),
            ephemeral=True
        )

        await log_event(
            interaction.guild,
            "banco",
            "🏦 Movimentação Bancária",
            f"{interaction.user.mention}\\n"
            f"**Tipo:** {self.tipo}\\n"
            f"**Valor:** {money(self.valor)}\\n"
            f"**Descrição:** {self.descricao}"
        )


class BankCustomAmountModal(discord.ui.Modal, title="Outro Valor"):
    valor = discord.ui.TextInput(label="Valor", placeholder="Ex: 250000", max_length=20)
    descricao = discord.ui.TextInput(label="Descrição", placeholder="Motivo da movimentação", max_length=200)

    def __init__(self, tipo):
        super().__init__()
        self.tipo = tipo

    async def on_submit(self, interaction):
        if not has_access(interaction.user, "banco"):
            return await deny(interaction)
        try:
            value = parse_money(self.valor)
            if value <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Valor inválido.", ephemeral=True)

        conn = connect()
        conn.execute(
            "INSERT INTO banco(guild_id,user_id,tipo,valor,descricao,created_at) VALUES(?,?,?,?,?,?)",
            (interaction.guild.id, interaction.user.id, self.tipo, value, str(self.descricao), now_iso())
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            embed=embed(
                "✅ Movimentação Registrada",
                f"**Tipo:** {'Depósito' if self.tipo == 'entrada' else 'Retirada'}\\n"
                f"**Valor:** {money(value)}\\n"
                f"**Descrição:** {self.descricao}",
                GREEN,
                guild_id=interaction.guild.id
            ),
            ephemeral=True
        )
        await log_event(
            interaction.guild, "banco", "🏦 Movimentação Bancária",
            f"{interaction.user.mention}\\n**Tipo:** {self.tipo}\\n**Valor:** {money(value)}\\n**Descrição:** {self.descricao}"
        )


class BankAmountView(discord.ui.View):
    def __init__(self, tipo):
        super().__init__(timeout=120)
        self.tipo = tipo

    @discord.ui.button(label="R$ 100 mil", style=discord.ButtonStyle.secondary)
    async def a100(self, interaction, button):
        await interaction.response.send_modal(BankDescriptionModal(self.tipo, 100000))

    @discord.ui.button(label="R$ 500 mil", style=discord.ButtonStyle.secondary)
    async def a500(self, interaction, button):
        await interaction.response.send_modal(BankDescriptionModal(self.tipo, 500000))

    @discord.ui.button(label="R$ 1 milhão", style=discord.ButtonStyle.secondary)
    async def a1m(self, interaction, button):
        await interaction.response.send_modal(BankDescriptionModal(self.tipo, 1000000))

    @discord.ui.button(label="Outro valor", emoji="✏️", style=discord.ButtonStyle.primary)
    async def other(self, interaction, button):
        await interaction.response.send_modal(BankCustomAmountModal(self.tipo))


def bank_balance(guild_id):
    conn = connect()
    rows = conn.execute("SELECT tipo,valor FROM banco WHERE guild_id=?", (guild_id,)).fetchall()
    conn.close()
    return sum(float(r["valor"]) if r["tipo"] == "entrada" else -float(r["valor"]) for r in rows)



def bank_history_embed(guild_id, limit=20):
    conn = connect()
    rows = conn.execute(
        """SELECT user_id,tipo,valor,descricao,created_at
           FROM banco WHERE guild_id=?
           ORDER BY id DESC LIMIT ?""",
        (guild_id, limit)
    ).fetchall()
    conn.close()

    if not rows:
        return embed("📊 Histórico Financeiro", "Nenhuma movimentação registrada.", guild_id=guild_id)

    lines = []
    for r in rows:
        icon = "🟢" if r["tipo"] == "entrada" else "🔴"
        origem = str(r["descricao"] or "Movimentação")
        lines.append(
            f"{icon} **{money(float(r['valor']))}** • {origem[:70]}\n"
            f"<@{r['user_id']}>"
        )
    return embed(
        "📊 Histórico Financeiro",
        "\n\n".join(lines),
        guild_id=guild_id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )


def financial_summary_embed(guild_id):
    conn = connect()
    rows = conn.execute(
        "SELECT tipo,valor,descricao FROM banco WHERE guild_id=?",
        (guild_id,)
    ).fetchall()
    conn.close()

    total_in = sum(float(r["valor"]) for r in rows if r["tipo"] == "entrada")
    total_out = sum(float(r["valor"]) for r in rows if r["tipo"] != "entrada")
    actions = sum(
        float(r["valor"]) for r in rows
        if r["tipo"] == "entrada" and "Resultado da ação" in str(r["descricao"] or "")
    )
    manual = total_in - actions

    return embed(
        "💰 Resumo Financeiro",
        f"**Saldo:** {money(total_in-total_out)}\n"
        f"**Entradas:** {money(total_in)}\n"
        f"**Saídas:** {money(total_out)}\n\n"
        f"🎯 **Ações:** {money(actions)}\n"
        f"🏦 **Outras entradas:** {money(manual)}",
        guild_id=guild_id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )

class BancoPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Depositar", emoji="➕", style=discord.ButtonStyle.success, custom_id="public:bank_in")
    async def deposit(self, interaction, button):
        if not enabled(interaction.guild.id, "banco"):
            return await deny(interaction, "❌ Sistema desligado.")
        if not has_access(interaction.user, "banco"):
            return await deny(interaction)
        await interaction.response.send_message("💰 Escolha o valor do depósito:", view=BankAmountView("entrada"), ephemeral=True)

    @discord.ui.button(label="Retirar", emoji="➖", style=discord.ButtonStyle.danger, custom_id="public:bank_out")
    async def withdraw(self, interaction, button):
        if not enabled(interaction.guild.id, "banco"):
            return await deny(interaction, "❌ Sistema desligado.")
        if not has_access(interaction.user, "banco"):
            return await deny(interaction)
        await interaction.response.send_message("💰 Escolha o valor da retirada:", view=BankAmountView("saida"), ephemeral=True)

    @discord.ui.button(label="Ver Saldo", emoji="💰", style=discord.ButtonStyle.secondary, custom_id="public:bank_balance")
    async def balance(self, interaction, button):
        if not has_access(interaction.user, "banco"):
            return await deny(interaction)
        await interaction.response.send_message(
            embed=embed("🏦 Saldo Atual", f"**{money(bank_balance(interaction.guild.id))}**", guild_id=interaction.guild.id),
            ephemeral=True
        )

    @discord.ui.button(label="Histórico", emoji="📊", style=discord.ButtonStyle.secondary, custom_id="public:bank_history")
    async def history(self, interaction, button):
        if not has_access(interaction.user, "banco"):
            return await deny(interaction)
        await interaction.response.send_message(
            embed=bank_history_embed(interaction.guild.id),
            ephemeral=True
        )

    @discord.ui.button(label="Resumo", emoji="📈", style=discord.ButtonStyle.primary, custom_id="public:bank_summary")
    async def summary(self, interaction, button):
        if not has_access(interaction.user, "banco"):
            return await deny(interaction)
        await interaction.response.send_message(
            embed=financial_summary_embed(interaction.guild.id),
            ephemeral=True
        )


# ============================================================
# LAVAGEM
# ============================================================

async def process_laundry(interaction, bruto):
    if not has_access(interaction.user, "lavagem"):
        return await deny(interaction)

    cfg = get_config(interaction.guild.id, "lavagem")
    taxa = float(cfg.get("laundry_rate", 25))
    liquido = bruto * (1 - taxa / 100)

    conn = connect()
    conn.execute(
        "INSERT INTO lavagens(guild_id,user_id,bruto,taxa,liquido,created_at) VALUES(?,?,?,?,?,?)",
        (interaction.guild.id, interaction.user.id, bruto, taxa, liquido, now_iso())
    )
    conn.commit()
    conn.close()

    await interaction.response.send_message(
        embed=embed(
            "✅ Lavagem Registrada",
            f"**Bruto:** {money(bruto)}\\n**Taxa:** {taxa:.2f}%\\n**Líquido:** {money(liquido)}",
            GREEN,
            guild_id=interaction.guild.id
        ),
        ephemeral=True
    )
    await log_event(
        interaction.guild, "lavagem", "💸 Lavagem",
        f"{interaction.user.mention}\\nBruto: **{money(bruto)}**\\nLíquido: **{money(liquido)}**"
    )


class LaundryCustomModal(discord.ui.Modal, title="Outro Valor de Lavagem"):
    bruto = discord.ui.TextInput(label="Valor bruto", placeholder="Ex: 750000", max_length=20)

    async def on_submit(self, interaction):
        try:
            bruto = parse_money(self.bruto)
            if bruto <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Valor inválido.", ephemeral=True)

        await process_laundry(interaction, bruto)


class LaundryAmountView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="R$ 100 mil", style=discord.ButtonStyle.secondary)
    async def a100(self, interaction, button):
        await process_laundry(interaction, 100000)

    @discord.ui.button(label="R$ 500 mil", style=discord.ButtonStyle.secondary)
    async def a500(self, interaction, button):
        await process_laundry(interaction, 500000)

    @discord.ui.button(label="R$ 1 milhão", style=discord.ButtonStyle.secondary)
    async def a1m(self, interaction, button):
        await process_laundry(interaction, 1000000)

    @discord.ui.button(label="Outro valor", emoji="✏️", style=discord.ButtonStyle.primary)
    async def other(self, interaction, button):
        await interaction.response.send_modal(LaundryCustomModal())


class LavagemPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Registrar Lavagem", emoji="💸", style=discord.ButtonStyle.primary, custom_id="public:laundry")
    async def register(self, interaction, button):
        if not enabled(interaction.guild.id, "lavagem"):
            return await deny(interaction, "❌ Sistema desligado.")
        if not has_access(interaction.user, "lavagem"):
            return await deny(interaction)
        await interaction.response.send_message("💸 Escolha o valor bruto:", view=LaundryAmountView(), ephemeral=True)

# ============================================================
# ENCOMENDAS
# ============================================================

async def save_order(interaction, responsavel_id, destinatario_id, prazo, descricao):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO encomendas(guild_id,author_id,responsavel_id,descricao,data_hora,destinatario,status,created_at)
           VALUES(?,?,?,?,?,?,'pendente',?)""",
        (
            interaction.guild.id, interaction.user.id, responsavel_id, descricao,
            prazo, f"<@{destinatario_id}>", now_iso()
        )
    )
    oid = cur.lastrowid
    conn.commit()
    conn.close()

    e = embed("📦 Nova Encomenda", "Aguardando aprovação.", guild_id=interaction.guild.id)
    e.add_field(name="Responsável", value=f"<@{responsavel_id}>", inline=False)
    e.add_field(name="Destinatário", value=f"<@{destinatario_id}>", inline=False)
    e.add_field(name="Prazo", value=prazo, inline=True)
    e.add_field(name="Pedido", value=descricao, inline=False)
    e.set_footer(text=f"ENC#{oid} • {get_theme(interaction.guild.id)['footer']}")

    cfg = get_config(interaction.guild.id, "encomendas")
    ch = interaction.guild.get_channel(int(cfg["log_channel_id"])) if cfg.get("log_channel_id") else None
    if ch:
        await ch.send(embed=e, view=ApprovalView("encomendas", oid, responsavel_id))

    await interaction.response.send_message("✅ Encomenda enviada para análise.", ephemeral=True)


class OrderDescriptionModal(discord.ui.Modal, title="Descrição da Encomenda"):
    descricao = discord.ui.TextInput(label="Descrição do Pedido", style=discord.TextStyle.paragraph, max_length=800)

    def __init__(self, responsavel_id, destinatario_id, prazo):
        super().__init__()
        self.responsavel_id = int(responsavel_id)
        self.destinatario_id = int(destinatario_id)
        self.prazo = str(prazo)

    async def on_submit(self, interaction):
        if not has_access(interaction.user, "encomendas"):
            return await deny(interaction)
        await save_order(
            interaction,
            self.responsavel_id,
            self.destinatario_id,
            self.prazo,
            str(self.descricao)
        )


class OrderCustomModal(discord.ui.Modal, title="Encomenda Personalizada"):
    prazo = discord.ui.TextInput(label="Data / horário", placeholder="Ex: 02/09 às 20:00", max_length=80)
    descricao = discord.ui.TextInput(label="Descrição do Pedido", style=discord.TextStyle.paragraph, max_length=800)

    def __init__(self, responsavel_id, destinatario_id):
        super().__init__()
        self.responsavel_id = int(responsavel_id)
        self.destinatario_id = int(destinatario_id)

    async def on_submit(self, interaction):
        if not has_access(interaction.user, "encomendas"):
            return await deny(interaction)
        await save_order(
            interaction,
            self.responsavel_id,
            self.destinatario_id,
            str(self.prazo),
            str(self.descricao)
        )


class OrderDeadlineView(discord.ui.View):
    def __init__(self, responsavel_id, destinatario_id):
        super().__init__(timeout=120)
        self.responsavel_id = int(responsavel_id)
        self.destinatario_id = int(destinatario_id)

    @discord.ui.button(label="Hoje", emoji="📅", style=discord.ButtonStyle.secondary)
    async def today(self, interaction, button):
        await interaction.response.send_modal(OrderDescriptionModal(self.responsavel_id, self.destinatario_id, "Hoje"))

    @discord.ui.button(label="Amanhã", emoji="➡️", style=discord.ButtonStyle.secondary)
    async def tomorrow(self, interaction, button):
        await interaction.response.send_modal(OrderDescriptionModal(self.responsavel_id, self.destinatario_id, "Amanhã"))

    @discord.ui.button(label="Em 3 dias", emoji="3️⃣", style=discord.ButtonStyle.secondary)
    async def three(self, interaction, button):
        await interaction.response.send_modal(OrderDescriptionModal(self.responsavel_id, self.destinatario_id, "Em 3 dias"))

    @discord.ui.button(label="Personalizar", emoji="✏️", style=discord.ButtonStyle.primary)
    async def custom(self, interaction, button):
        await interaction.response.send_modal(OrderCustomModal(self.responsavel_id, self.destinatario_id))


class RecipientUserSelect(discord.ui.UserSelect):
    def __init__(self, responsavel_id):
        self.responsavel_id = int(responsavel_id)
        super().__init__(placeholder="Selecione quem receberá a encomenda", min_values=1, max_values=1)

    async def callback(self, interaction):
        await interaction.response.edit_message(
            content="📅 Agora escolha o prazo:",
            view=OrderDeadlineView(self.responsavel_id, self.values[0].id)
        )


class RecipientUserView(discord.ui.View):
    def __init__(self, responsavel_id):
        super().__init__(timeout=120)
        self.add_item(RecipientUserSelect(responsavel_id))


class ResponsibleUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o responsável pelo pedido", min_values=1, max_values=1)

    async def callback(self, interaction):
        await interaction.response.edit_message(
            content="👤 Agora selecione o destinatário:",
            view=RecipientUserView(self.values[0].id)
        )


class OrderStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ResponsibleUserSelect())


class OrderStatusSelect(discord.ui.Select):
    def __init__(self, guild_id: int, user_id: int):
        conn = connect()
        rows = conn.execute(
            """SELECT * FROM encomendas
               WHERE guild_id=?
                 AND (author_id=? OR responsavel_id=? OR claimed_by=?)
               ORDER BY id DESC LIMIT 25""",
            (guild_id, user_id, user_id, user_id)
        ).fetchall()
        conn.close()

        options = [
            discord.SelectOption(
                label=f"ENC#{r['id']} • {str(r['status']).upper()}"[:100],
                value=str(r["id"]),
                description=str(r["descricao"])[:100],
                emoji="📦"
            )
            for r in rows
        ]

        if not options:
            options = [
                discord.SelectOption(
                    label="Nenhuma encomenda encontrada",
                    value="none",
                    emoji="📭"
                )
            ]

        super().__init__(
            placeholder="Selecione uma encomenda",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message(
                "📭 Nenhuma encomenda encontrada.",
                ephemeral=True
            )

        order_id = int(self.values[0])
        await interaction.response.edit_message(
            content=None,
            embed=order_detail_embed(
                interaction.guild,
                order_id
            ),
            view=OrderManageView(order_id)
        )


class OrderStatusSelectView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=180)
        self.add_item(OrderStatusSelect(guild_id, user_id))


def get_order(order_id: int):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM encomendas WHERE id=?",
        (int(order_id),)
    ).fetchone()
    conn.close()
    return row


def order_detail_embed(guild: discord.Guild, order_id: int):
    row = get_order(order_id)
    if not row:
        return embed(
            "❌ Encomenda não encontrada",
            "Essa encomenda não existe.",
            RED,
            guild_id=guild.id
        )

    status_icons = {
        "pendente": "🟡",
        "aprovado": "🟢",
        "assumida": "🔵",
        "concluida": "✅",
        "cancelada": "❌",
        "reprovado": "🔴",
    }
    icon = status_icons.get(str(row["status"]), "⚪")

    claimed = (
        f"<@{row['claimed_by']}>"
        if row["claimed_by"]
        else "Ninguém"
    )

    return embed(
        f"📦 ENC#{row['id']}",
        (
            f"**Status:** {icon} {str(row['status']).upper()}\n"
            f"**Responsável original:** <@{row['responsavel_id']}>\n"
            f"**Assumida por:** {claimed}\n"
            f"**Destinatário:** {row['destinatario']}\n"
            f"**Prazo:** {row['data_hora']}\n\n"
            f"**Pedido**\n{row['descricao']}"
        ),
        guild_id=guild.id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )


class OrderCancelModal(discord.ui.Modal, title="Cancelar Encomenda"):
    motivo = discord.ui.TextInput(
        label="Motivo do cancelamento",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, order_id: int):
        super().__init__()
        self.order_id = int(order_id)

    async def on_submit(self, interaction):
        row = get_order(self.order_id)
        if not row:
            return await interaction.response.send_message(
                "❌ Encomenda não encontrada.",
                ephemeral=True
            )

        allowed = (
            is_admin(interaction.user)
            or interaction.user.id == int(row["responsavel_id"])
            or (
                row["claimed_by"]
                and interaction.user.id == int(row["claimed_by"])
            )
        )
        if not allowed:
            return await deny(interaction)

        conn = connect()
        conn.execute(
            """UPDATE encomendas
               SET status='cancelada', cancelled_at=?
               WHERE id=?""",
            (now_iso(), self.order_id)
        )
        conn.commit()
        conn.close()

        await log_event(
            interaction.guild,
            "encomendas",
            f"❌ Encomenda ENC#{self.order_id} cancelada",
            (
                f"**Responsável:** {interaction.user.mention}\n"
                f"**Motivo:** {self.motivo}"
            ),
            RED
        )

        await interaction.response.edit_message(
            content="❌ Encomenda cancelada.",
            embed=order_detail_embed(
                interaction.guild,
                self.order_id
            ),
            view=OrderManageView(self.order_id)
        )


class OrderManageView(discord.ui.View):
    def __init__(self, order_id: int):
        super().__init__(timeout=180)
        self.order_id = int(order_id)

    @discord.ui.button(
        label="Assumir",
        emoji="🙋",
        style=discord.ButtonStyle.primary
    )
    async def claim(self, interaction, button):
        row = get_order(self.order_id)
        if not row:
            return await interaction.response.send_message(
                "❌ Encomenda não encontrada.",
                ephemeral=True
            )

        if str(row["status"]) not in {"aprovado", "assumida"}:
            return await interaction.response.send_message(
                "❌ Essa encomenda não pode ser assumida nesse status.",
                ephemeral=True
            )

        if not has_access(interaction.user, "encomendas") and not is_admin(interaction.user):
            return await deny(interaction)

        if row["claimed_by"] and int(row["claimed_by"]) != interaction.user.id and not is_admin(interaction.user):
            return await interaction.response.send_message(
                f"❌ Essa encomenda já foi assumida por <@{row['claimed_by']}>.",
                ephemeral=True
            )

        conn = connect()
        conn.execute(
            """UPDATE encomendas
               SET status='assumida', claimed_by=?, claimed_at=?
               WHERE id=?""",
            (
                interaction.user.id,
                now_iso(),
                self.order_id
            )
        )
        conn.commit()
        conn.close()

        await log_event(
            interaction.guild,
            "encomendas",
            f"🙋 Encomenda ENC#{self.order_id} assumida",
            f"Assumida por {interaction.user.mention}.",
            BLUE
        )

        await interaction.response.edit_message(
            embed=order_detail_embed(interaction.guild, self.order_id),
            view=self
        )

    @discord.ui.button(
        label="Concluir",
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def complete(self, interaction, button):
        row = get_order(self.order_id)
        if not row:
            return await interaction.response.send_message(
                "❌ Encomenda não encontrada.",
                ephemeral=True
            )

        allowed = (
            is_admin(interaction.user)
            or (
                row["claimed_by"]
                and int(row["claimed_by"]) == interaction.user.id
            )
            or int(row["responsavel_id"]) == interaction.user.id
        )
        if not allowed:
            return await deny(
                interaction,
                "❌ Só o responsável, quem assumiu ou um administrador pode concluir."
            )

        if str(row["status"]) not in {"aprovado", "assumida"}:
            return await interaction.response.send_message(
                "❌ Essa encomenda não pode ser concluída agora.",
                ephemeral=True
            )

        conn = connect()
        conn.execute(
            """UPDATE encomendas
               SET status='concluida', completed_at=?
               WHERE id=?""",
            (now_iso(), self.order_id)
        )
        conn.commit()
        conn.close()

        add_points(
            interaction.guild.id,
            interaction.user.id,
            3
        )

        await log_event(
            interaction.guild,
            "encomendas",
            f"✅ Encomenda ENC#{self.order_id} concluída",
            f"Concluída por {interaction.user.mention}.",
            GREEN
        )

        await interaction.response.edit_message(
            content="✅ Encomenda concluída.",
            embed=order_detail_embed(interaction.guild, self.order_id),
            view=self
        )

    @discord.ui.button(
        label="Cancelar",
        emoji="❌",
        style=discord.ButtonStyle.danger
    )
    async def cancel(self, interaction, button):
        row = get_order(self.order_id)
        if not row:
            return await interaction.response.send_message(
                "❌ Encomenda não encontrada.",
                ephemeral=True
            )

        if str(row["status"]) in {"concluida", "cancelada", "reprovado"}:
            return await interaction.response.send_message(
                "❌ Essa encomenda já foi finalizada.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            OrderCancelModal(self.order_id)
        )

    @discord.ui.button(
        label="Atualizar",
        emoji="🔄",
        style=discord.ButtonStyle.secondary
    )
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(
            embed=order_detail_embed(
                interaction.guild,
                self.order_id
            ),
            view=self
        )


def orders_list_embed(guild_id, user_id=None):
    conn = connect()
    if user_id:
        rows = conn.execute(
            """SELECT * FROM encomendas
               WHERE guild_id=?
                 AND (author_id=? OR responsavel_id=? OR claimed_by=?)
               ORDER BY id DESC LIMIT 20""",
            (guild_id, user_id, user_id, user_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM encomendas WHERE guild_id=? ORDER BY id DESC LIMIT 20",
            (guild_id,)
        ).fetchall()
    conn.close()

    if not rows:
        return embed(
            "📦 Encomendas",
            "Nenhuma encomenda encontrada.",
            guild_id=guild_id
        )

    lines = []
    for r in rows:
        lines.append(
            f"**ENC#{r['id']} • {str(r['status']).upper()}**\n"
            f"Responsável: <@{r['responsavel_id']}> • Prazo: {r['data_hora']}"
        )

    return embed(
        "📦 Encomendas",
        "\n\n".join(lines),
        guild_id=guild_id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )


class EncomendasPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir Encomenda",
        emoji="📦",
        style=discord.ButtonStyle.secondary,
        custom_id="public:order"
    )
    async def order(self, interaction, button):
        if not enabled(interaction.guild.id, "encomendas"):
            return await deny(
                interaction,
                "❌ Sistema desligado."
            )
        if not has_access(interaction.user, "encomendas"):
            return await deny(interaction)

        await interaction.response.send_message(
            "👤 Selecione o responsável pelo pedido:",
            view=OrderStartView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="Minhas Encomendas",
        emoji="📋",
        style=discord.ButtonStyle.primary,
        custom_id="public:order:list"
    )
    async def my_orders(self, interaction, button):
        await interaction.response.send_message(
            embed=orders_list_embed(
                interaction.guild.id,
                interaction.user.id
            ),
            view=OrderStatusSelectView(
                interaction.guild.id,
                interaction.user.id
            ),
            ephemeral=True
        )

# ============================================================
# AUSÊNCIA
# ============================================================

async def save_absence(interaction, periodo, motivo):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO ausencias(guild_id,user_id,periodo,motivo,status,created_at)
           VALUES(?,?,?,?,'pendente',?)""",
        (interaction.guild.id, interaction.user.id, periodo, motivo, now_iso())
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()

    e = embed("⌛ Solicitação de Ausência", "Aguardando aprovação.", guild_id=interaction.guild.id)
    e.add_field(name="Membro", value=interaction.user.mention, inline=False)
    e.add_field(name="Período", value=periodo, inline=False)
    e.add_field(name="Motivo", value=motivo, inline=False)
    e.set_footer(text=f"AUS#{aid} • {get_theme(interaction.guild.id)['footer']}")

    cfg = get_config(interaction.guild.id, "ausencia")
    ch = interaction.guild.get_channel(int(cfg["log_channel_id"])) if cfg.get("log_channel_id") else None
    if ch:
        await ch.send(embed=e, view=ApprovalView("ausencia", aid, interaction.user.id))

    await interaction.response.send_message("✅ Solicitação enviada.", ephemeral=True)


class AbsenceReasonModal(discord.ui.Modal, title="Motivo da Ausência"):
    motivo = discord.ui.TextInput(label="Motivo", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, periodo):
        super().__init__()
        self.periodo = str(periodo)

    async def on_submit(self, interaction):
        await save_absence(interaction, self.periodo, str(self.motivo))


class AbsenceCustomModal(discord.ui.Modal, title="Ausência Personalizada"):
    periodo = discord.ui.TextInput(label="Período", placeholder="Ex: 31/08 até 05/09", max_length=80)
    motivo = discord.ui.TextInput(label="Motivo", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction):
        await save_absence(interaction, str(self.periodo), str(self.motivo))


class AbsencePeriodView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="1 dia", style=discord.ButtonStyle.secondary)
    async def one(self, interaction, button):
        await interaction.response.send_modal(AbsenceReasonModal("1 dia"))

    @discord.ui.button(label="3 dias", style=discord.ButtonStyle.secondary)
    async def three(self, interaction, button):
        await interaction.response.send_modal(AbsenceReasonModal("3 dias"))

    @discord.ui.button(label="7 dias", style=discord.ButtonStyle.secondary)
    async def seven(self, interaction, button):
        await interaction.response.send_modal(AbsenceReasonModal("7 dias"))

    @discord.ui.button(label="15 dias", style=discord.ButtonStyle.secondary)
    async def fifteen(self, interaction, button):
        await interaction.response.send_modal(AbsenceReasonModal("15 dias"))

    @discord.ui.button(label="Personalizar", emoji="✏️", style=discord.ButtonStyle.primary)
    async def custom(self, interaction, button):
        await interaction.response.send_modal(AbsenceCustomModal())


class AusenciaPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Solicitar Ausência", emoji="⌛", style=discord.ButtonStyle.secondary, custom_id="public:absence")
    async def absence(self, interaction, button):
        if not enabled(interaction.guild.id, "ausencia"):
            return await deny(interaction, "❌ Sistema desligado.")

        await interaction.response.send_message(
            "⌛ Por quanto tempo você ficará ausente?",
            view=AbsencePeriodView(),
            ephemeral=True
        )

# ============================================================
# FARM
# ============================================================

class FarmItemSelect(discord.ui.Select):
    def __init__(self, items):
        options = [
            discord.SelectOption(
                label=str(item)[:100],
                value=str(i),
                emoji="📦"
            )
            for i, item in enumerate(items[:25])
        ]
        super().__init__(
            placeholder="Escolha o item farmado",
            options=options,
            min_values=1,
            max_values=1
        )


class FarmItemSelectView(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=180)
        self.items = items
        select = FarmItemSelect(items)
        select.callback = self.select_item
        self.add_item(select)

    async def select_item(self, interaction):
        idx = int(self.children[0].values[0])
        item = self.items[idx]
        await interaction.response.send_modal(FarmQuantityModal(item))


class FarmQuantityModal(discord.ui.Modal, title="Registrar Farm"):
    quantidade = discord.ui.TextInput(
        label="Quantidade",
        placeholder="Ex: 500",
        max_length=12
    )
    comprovante = discord.ui.TextInput(
        label="Link do comprovante (opcional)",
        placeholder="https://...",
        required=False,
        max_length=500
    )

    def __init__(self, item):
        super().__init__()
        self.item = str(item)

    async def on_submit(self, interaction):
        if not enabled(interaction.guild.id, "farm"):
            return await deny(interaction, "❌ Sistema desligado.")

        try:
            qty = parse_int(self.quantidade)
            if qty <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Quantidade inválida.",
                ephemeral=True
            )

        proof = str(self.comprovante).strip()
        if proof and not (proof.startswith("http://") or proof.startswith("https://")):
            return await interaction.response.send_message(
                "❌ O comprovante precisa ser um link válido.",
                ephemeral=True
            )

        conn = connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO farms(guild_id,user_id,item,quantidade,comprovante,status,created_at)
               VALUES(?,?,?,?,?,'pendente',?)""",
            (
                interaction.guild.id,
                interaction.user.id,
                self.item,
                qty,
                proof,
                now_iso()
            )
        )
        fid = cur.lastrowid
        conn.commit()
        conn.close()

        e = embed(
            "📦 Novo Farm",
            "Aguardando aprovação.",
            guild_id=interaction.guild.id
        )
        e.add_field(name="Membro", value=interaction.user.mention, inline=False)
        e.add_field(name="Item", value=self.item, inline=True)
        e.add_field(name="Quantidade", value=str(qty), inline=True)

        if proof:
            e.add_field(name="Comprovante", value=f"[Abrir comprovante]({proof})", inline=False)

        e.set_footer(text=f"FARM#{fid} • {get_theme(interaction.guild.id)['footer']}")

        cfg = get_config(interaction.guild.id, "farm")
        ch = interaction.guild.get_channel(
            int(cfg["log_channel_id"])
        ) if cfg.get("log_channel_id") else None

        if ch:
            await ch.send(
                embed=e,
                view=ApprovalView("farm", fid, interaction.user.id)
            )

        await interaction.response.send_message(
            "✅ Farm enviado para aprovação.",
            ephemeral=True
        )


class FarmPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Registrar Farm",
        emoji="📦",
        style=discord.ButtonStyle.success,
        custom_id="public:farm"
    )
    async def farm(self, interaction, button):
        if not enabled(interaction.guild.id, "farm"):
            return await deny(interaction, "❌ Sistema desligado.")

        cfg = get_config(interaction.guild.id, "farm")
        items = cfg.get("farm_items", [])

        if not items:
            return await interaction.response.send_message(
                "❌ Ainda não existem itens configurados para o Farm.\\n"
                "Um administrador precisa usar **/gerenciar → Farm → Configurações Específicas → Adicionar Item**.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "📦 **Qual item você farmou?**",
            view=FarmItemSelectView(items),
            ephemeral=True
        )

    @discord.ui.button(
        label="Ranking",
        emoji="🏆",
        style=discord.ButtonStyle.secondary,
        custom_id="public:farm_rank"
    )
    async def rank(self, interaction, button):
        conn = connect()
        rows = conn.execute(
            """SELECT user_id,SUM(quantidade) total FROM farms
               WHERE guild_id=? AND status='aprovado'
               GROUP BY user_id ORDER BY total DESC LIMIT 10""",
            (interaction.guild.id,)
        ).fetchall()
        conn.close()

        lines = [
            f"**{i+1}.** <@{r['user_id']}> — **{r['total']}**"
            for i, r in enumerate(rows)
        ]

        # Ranking é uma resposta compacta: sem banner gigante.
        await interaction.response.send_message(
            embed=embed(
                "🏆 Ranking de Farm",
                "\\n".join(lines) or "Sem farms aprovados.",
                guild_id=interaction.guild.id,
                use_theme_image=False,
                use_theme_thumbnail=True
            ),
            ephemeral=True
        )

# ============================================================
# BAÚ
# ============================================================

class StockQuantityModal(discord.ui.Modal):
    quantidade = discord.ui.TextInput(label="Quantidade", placeholder="Ex: 100", max_length=12)

    def __init__(self, bau, tipo, item):
        super().__init__(title=f"{tipo.title()} • {item}")
        self.bau = bau
        self.tipo = tipo
        self.item = str(item)

    async def on_submit(self, interaction):
        if not has_access(interaction.user, "bau"):
            return await deny(interaction)

        if self.bau == "lider" and not is_admin(interaction.user):
            cfg = get_config(interaction.guild.id, "bau")
            leader_ids = {int(x) for x in cfg.get("leader_role_ids", [])}
            if leader_ids and not any(r.id in leader_ids for r in interaction.user.roles):
                return await deny(interaction, "❌ Você não possui um cargo autorizado para o Baú de Líder.")

        try:
            qty = parse_int(self.quantidade)
            if qty <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)

        conn = connect()
        row = conn.execute(
            "SELECT quantidade FROM estoque WHERE guild_id=? AND bau=? AND item=?",
            (interaction.guild.id, self.bau, self.item)
        ).fetchone()
        current = int(row["quantidade"]) if row else 0
        delta = qty if self.tipo == "entrada" else -qty

        if current + delta < 0:
            conn.close()
            return await interaction.response.send_message(
                f"❌ Estoque insuficiente. Atual: **{current}**.",
                ephemeral=True
            )

        conn.execute(
            """INSERT INTO estoque(guild_id,bau,item,quantidade) VALUES(?,?,?,?)
               ON CONFLICT(guild_id,bau,item) DO UPDATE SET quantidade=quantidade+excluded.quantidade""",
            (interaction.guild.id, self.bau, self.item, delta)
        )
        conn.execute(
            "INSERT INTO estoque_mov(guild_id,user_id,bau,tipo,item,quantidade,created_at) VALUES(?,?,?,?,?,?,?)",
            (interaction.guild.id, interaction.user.id, self.bau, self.tipo, self.item, qty, now_iso())
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(
            embed=embed(
                "✅ Estoque Atualizado",
                f"**Baú:** {self.bau.title()}\\n**Movimento:** {self.tipo.title()}\\n"
                f"**Item:** {self.item}\\n**Quantidade:** {qty}",
                GREEN,
                guild_id=interaction.guild.id
            ),
            ephemeral=True
        )

        await log_event(
            interaction.guild, "bau", "🧰 Movimento de Baú",
            f"{interaction.user.mention}\\n**Baú:** {self.bau}\\n**Tipo:** {self.tipo}\\n"
            f"**Item:** {self.item}\\n**Qtd:** {qty}"
        )


class StockItemSelect(discord.ui.Select):
    def __init__(self, items, bau, tipo):
        self.items_data = items
        self.bau = bau
        self.tipo = tipo
        super().__init__(
            placeholder="Escolha o item",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=str(item)[:100], value=str(i), emoji="📦")
                for i, item in enumerate(items[:25])
            ]
        )

    async def callback(self, interaction):
        item = self.items_data[int(self.values[0])]
        await interaction.response.send_modal(StockQuantityModal(self.bau, self.tipo, item))


class StockItemView(discord.ui.View):
    def __init__(self, items, bau, tipo):
        super().__init__(timeout=120)
        self.add_item(StockItemSelect(items, bau, tipo))


async def start_stock_flow(interaction, bau, tipo):
    if not enabled(interaction.guild.id, "bau"):
        return await deny(interaction, "❌ Sistema desligado.")
    if not has_access(interaction.user, "bau"):
        return await deny(interaction)

    if bau == "lider" and not is_admin(interaction.user):
        cfg = get_config(interaction.guild.id, "bau")
        leader_ids = {int(x) for x in cfg.get("leader_role_ids", [])}
        if leader_ids and not any(r.id in leader_ids for r in interaction.user.roles):
            return await deny(interaction, "❌ Você não possui um cargo autorizado para o Baú de Líder.")

    cfg = get_config(interaction.guild.id, "bau")
    items = cfg.get("stock_items", [])
    if not items:
        return await interaction.response.send_message(
            "❌ Nenhum item foi configurado no Baú.\\n"
            "Use **/gerenciar → Baús / Estoque → Configurações Específicas → Adicionar Item**.",
            ephemeral=True
        )

    await interaction.response.send_message(
        f"📦 Escolha o item para **{tipo}** no Baú **{bau.title()}**:",
        view=StockItemView(items, bau, tipo),
        ephemeral=True
    )


class BauPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrada Geral", emoji="➕", style=discord.ButtonStyle.success, custom_id="public:stock_g_in")
    async def gin(self, interaction, button):
        await start_stock_flow(interaction, "geral", "entrada")

    @discord.ui.button(label="Retirada Geral", emoji="➖", style=discord.ButtonStyle.danger, custom_id="public:stock_g_out")
    async def gout(self, interaction, button):
        await start_stock_flow(interaction, "geral", "retirada")

    @discord.ui.button(label="Entrada Líder", emoji="👑", style=discord.ButtonStyle.success, custom_id="public:stock_l_in")
    async def lin(self, interaction, button):
        await start_stock_flow(interaction, "lider", "entrada")

    @discord.ui.button(label="Retirada Líder", emoji="👑", style=discord.ButtonStyle.danger, custom_id="public:stock_l_out")
    async def lout(self, interaction, button):
        await start_stock_flow(interaction, "lider", "retirada")

    @discord.ui.button(label="Ver Estoque", emoji="📦", style=discord.ButtonStyle.secondary, custom_id="public:stock_show")
    async def show(self, interaction, button):
        if not has_access(interaction.user, "bau"):
            return await deny(interaction)

        conn = connect()
        rows = conn.execute(
            "SELECT bau,item,quantidade FROM estoque WHERE guild_id=? ORDER BY bau,item",
            (interaction.guild.id,)
        ).fetchall()
        conn.close()

        lines = [f"`{r['bau'].upper():5}` **{r['item']}** — {r['quantidade']}" for r in rows[:40]]
        await interaction.response.send_message(
            embed=embed("🧰 Estoque Atual", "\\n".join(lines) or "Estoque vazio.", guild_id=interaction.guild.id),
            ephemeral=True
        )

# ============================================================
# AÇÕES — CRIAÇÃO, PARTICIPAÇÃO, RESULTADO E FINANCEIRO
# ============================================================

def get_action(action_id: int):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM acoes WHERE id=?",
        (int(action_id),)
    ).fetchone()
    conn.close()
    return row


def get_action_participants(action_id: int):
    conn = connect()
    rows = conn.execute(
        """SELECT user_id,joined_at
           FROM acoes_participantes
           WHERE action_id=?
           ORDER BY joined_at ASC""",
        (int(action_id),)
    ).fetchall()
    conn.close()
    return rows


def get_actions(guild_id: int, only_open=True, limit=25):
    conn = connect()
    if only_open:
        rows = conn.execute(
            """SELECT * FROM acoes
               WHERE guild_id=? AND status='aberta'
               ORDER BY id DESC LIMIT ?""",
            (guild_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM acoes
               WHERE guild_id=?
               ORDER BY id DESC LIMIT ?""",
            (guild_id, limit)
        ).fetchall()
    conn.close()
    return rows


def action_status_label(row):
    if row["status"] == "aberta":
        return "🟢 Aberta"
    if row["resultado"] == "vitoria":
        return "🏆 Vitória"
    if row["resultado"] == "derrota":
        return "❌ Derrota"
    return "⚫ Encerrada"


def build_action_embed(guild: discord.Guild, action_id: int):
    row = get_action(action_id)
    if not row:
        return embed(
            "❌ Ação não encontrada",
            "Essa ação não existe mais.",
            RED,
            guild_id=guild.id
        )

    participants = get_action_participants(action_id)
    mentions = [f"<@{r['user_id']}>" for r in participants]

    if mentions:
        # Evita estourar limite da embed
        participant_text = "\n".join(
            f"• {m}" for m in mentions[:40]
        )
        if len(mentions) > 40:
            participant_text += f"\n• +{len(mentions) - 40} participante(s)"
    else:
        participant_text = "Nenhum participante ainda."

    desc = (
        f"**Criador:** <@{row['creator_id']}>\n"
        f"**Status:** {action_status_label(row)}\n"
        f"**Horário:** {row['horario'] or 'Não informado'}\n\n"
        f"**Descrição**\n{row['descricao'] or 'Sem descrição.'}"
    )

    if row["status"] != "aberta":
        desc += (
            f"\n\n**Resultado:** "
            f"{'🏆 Vitória' if row['resultado'] == 'vitoria' else '❌ Derrota'}"
        )
        if float(row["valor_ganho"] or 0) > 0:
            desc += f"\n**Valor ganho:** {money(float(row['valor_ganho']))}"

    e = embed(
        f"🎯 {row['nome']}",
        desc,
        guild_id=guild.id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )
    e.add_field(
        name=f"👥 Participantes ({len(mentions)})",
        value=participant_text,
        inline=False
    )
    e.set_footer(
        text=f"AÇÃO #{row['id']} • {get_theme(guild.id)['footer']}"
    )
    return e


def build_actions_list_embed(guild: discord.Guild, only_open=True):
    rows = get_actions(guild.id, only_open=only_open, limit=20)

    if not rows:
        return embed(
            "🎯 Ações Abertas" if only_open else "📜 Histórico de Ações",
            "Nenhuma ação encontrada.",
            guild_id=guild.id
        )

    lines = []
    for row in rows:
        count = len(get_action_participants(row["id"]))
        result = action_status_label(row)
        lines.append(
            f"**#{row['id']} • {row['nome']}**\n"
            f"{result} • 👥 {count} participante(s) • Criada por <@{row['creator_id']}>"
        )

    return embed(
        "🎯 Ações Abertas" if only_open else "📜 Histórico de Ações",
        "\n\n".join(lines),
        guild_id=guild.id
    )


class CreateActionModal(discord.ui.Modal, title="Criar Nova Ação"):
    nome = discord.ui.TextInput(
        label="Nome da ação",
        placeholder="Ex: Ação Banco Central",
        max_length=100
    )
    horario = discord.ui.TextInput(
        label="Horário",
        placeholder="Ex: Hoje 22:00",
        required=False,
        max_length=80
    )
    descricao = discord.ui.TextInput(
        label="Descrição",
        placeholder="Informações importantes da ação",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    async def on_submit(self, interaction):
        if not enabled(interaction.guild.id, "acoes"):
            return await deny(interaction, "❌ Sistema de ações está desligado.")
        if not has_access(interaction.user, "acoes"):
            return await deny(interaction)

        conn = connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO acoes(
                guild_id,creator_id,nome,descricao,horario,status,created_at
            ) VALUES(?,?,?,?,?,'aberta',?)""",
            (
                interaction.guild.id,
                interaction.user.id,
                str(self.nome).strip(),
                str(self.descricao).strip(),
                str(self.horario).strip(),
                now_iso()
            )
        )
        action_id = cur.lastrowid

        # Criador entra automaticamente na lista de participantes
        cur.execute(
            """INSERT OR IGNORE INTO acoes_participantes(
                action_id,guild_id,user_id,joined_at
            ) VALUES(?,?,?,?)""",
            (
                action_id,
                interaction.guild.id,
                interaction.user.id,
                now_iso()
            )
        )
        conn.commit()
        conn.close()

        cfg = get_config(interaction.guild.id, "acoes")
        ping_role = (
            interaction.guild.get_role(int(cfg["action_ping_role_id"]))
            if cfg.get("action_ping_role_id")
            else None
        )
        ping = ping_role.mention if ping_role else ""

        # Log da ação criada
        await log_event(
            interaction.guild,
            "acoes",
            f"🎯 Nova Ação: {self.nome}",
            (
                f"{ping}\n"
                f"**Criador:** {interaction.user.mention}\n"
                f"**Horário:** {self.horario or 'Não informado'}\n"
                f"**Descrição:** {self.descricao or 'Sem descrição'}"
            )
        )

        await interaction.response.send_message(
            content="✅ Ação criada. Esse é o painel dela:",
            embed=build_action_embed(interaction.guild, action_id),
            view=ActionDetailView(action_id),
            ephemeral=True
        )


class ActionSelect(discord.ui.Select):
    def __init__(self, guild_id: int, only_open=True):
        rows = get_actions(guild_id, only_open=only_open, limit=25)
        self.only_open = only_open

        options = []
        for row in rows:
            label = f"#{row['id']} • {row['nome']}"[:100]
            desc = (
                f"{action_status_label(row)} • "
                f"{len(get_action_participants(row['id']))} participante(s)"
            )[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(row["id"]),
                    description=desc,
                    emoji="🎯"
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="Nenhuma ação disponível",
                    value="none",
                    description="Crie uma nova ação primeiro.",
                    emoji="📭"
                )
            )

        super().__init__(
            placeholder="Selecione uma ação",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message(
                "❌ Nenhuma ação disponível.",
                ephemeral=True
            )

        action_id = int(self.values[0])
        await interaction.response.edit_message(
            content=None,
            embed=build_action_embed(interaction.guild, action_id),
            view=ActionDetailView(action_id)
        )


class ActionBrowserView(discord.ui.View):
    def __init__(self, guild_id: int, only_open=True):
        super().__init__(timeout=180)
        self.add_item(ActionSelect(guild_id, only_open=only_open))


class ActionResultView(discord.ui.View):
    def __init__(self, action_id: int, creator_id: int):
        super().__init__(timeout=120)
        self.action_id = int(action_id)
        self.creator_id = int(creator_id)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.creator_id and not is_admin(interaction.user):
            await deny(
                interaction,
                "❌ Só quem criou a ação pode informar o resultado."
            )
            return False
        return True

    @discord.ui.button(
        label="Vitória",
        emoji="🏆",
        style=discord.ButtonStyle.success
    )
    async def victory(self, interaction, button):
        await interaction.response.send_modal(
            ActionVictoryAmountModal(self.action_id, self.creator_id)
        )

    @discord.ui.button(
        label="Derrota",
        emoji="❌",
        style=discord.ButtonStyle.danger
    )
    async def defeat(self, interaction, button):
        await finish_action(
            interaction,
            self.action_id,
            "derrota",
            0
        )


class ActionVictoryAmountModal(discord.ui.Modal, title="Valor Ganho na Ação"):
    valor = discord.ui.TextInput(
        label="Valor ganho",
        placeholder="Ex: 1500000",
        max_length=20
    )

    def __init__(self, action_id: int, creator_id: int):
        super().__init__()
        self.action_id = int(action_id)
        self.creator_id = int(creator_id)

    async def on_submit(self, interaction):
        if interaction.user.id != self.creator_id and not is_admin(interaction.user):
            return await deny(
                interaction,
                "❌ Só quem criou a ação pode informar o resultado."
            )

        try:
            value = parse_money(self.valor)
            if value < 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Valor inválido.",
                ephemeral=True
            )

        await finish_action(
            interaction,
            self.action_id,
            "vitoria",
            value
        )


async def finish_action(interaction, action_id: int, result: str, value: float):
    row = get_action(action_id)
    if not row:
        return await interaction.response.send_message(
            "❌ Ação não encontrada.",
            ephemeral=True
        )

    if row["status"] != "aberta":
        return await interaction.response.send_message(
            "❌ Essa ação já foi encerrada.",
            ephemeral=True
        )

    if interaction.user.id != int(row["creator_id"]) and not is_admin(interaction.user):
        return await deny(
            interaction,
            "❌ Só quem criou a ação pode encerrar."
        )

    conn = connect()

    conn.execute(
        """UPDATE acoes
           SET status='encerrada',
               resultado=?,
               valor_ganho=?,
               closed_at=?
           WHERE id=?""",
        (
            result,
            float(value),
            now_iso(),
            action_id
        )
    )

    # Vitória: valor entra automaticamente no banco/financeiro da facção
    if result == "vitoria" and float(value) > 0:
        conn.execute(
            """INSERT INTO banco(
                guild_id,user_id,tipo,valor,descricao,created_at
            ) VALUES(?,?,?,?,?,?)""",
            (
                interaction.guild.id,
                interaction.user.id,
                "entrada",
                float(value),
                f"Resultado da ação #{action_id} - {row['nome']}",
                now_iso()
            )
        )

    conn.commit()
    conn.close()

    participants = get_action_participants(action_id)

    await log_event(
        interaction.guild,
        "acoes",
        f"{'🏆 Vitória' if result == 'vitoria' else '❌ Derrota'} • {row['nome']}",
        (
            f"**Criador:** <@{row['creator_id']}>\n"
            f"**Participantes:** {len(participants)}\n"
            f"**Valor ganho:** {money(value) if value > 0 else 'R$ 0,00'}\n"
            + (
                "**Financeiro:** valor adicionado automaticamente ao Banco da facção."
                if result == "vitoria" and value > 0
                else "**Financeiro:** nenhuma entrada registrada."
            )
        ),
        GREEN if result == "vitoria" else RED
    )

    await interaction.response.edit_message(
        content=(
            "✅ Ação encerrada. "
            + (
                f"**{money(value)}** foi adicionado ao financeiro da facção."
                if result == "vitoria" and value > 0
                else "Nenhum valor foi adicionado ao financeiro."
            )
        ),
        embed=build_action_embed(interaction.guild, action_id),
        view=ActionDetailView(action_id)
    )


class ActionDetailView(discord.ui.View):
    def __init__(self, action_id: int):
        super().__init__(timeout=180)
        self.action_id = int(action_id)

    @discord.ui.button(
        label="Participar",
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def join(self, interaction, button):
        row = get_action(self.action_id)
        if not row:
            return await interaction.response.send_message(
                "❌ Ação não encontrada.",
                ephemeral=True
            )
        if row["status"] != "aberta":
            return await interaction.response.send_message(
                "❌ Essa ação já foi encerrada.",
                ephemeral=True
            )
        if not has_access(interaction.user, "acoes"):
            return await deny(interaction)

        conn = connect()
        existing = conn.execute(
            """SELECT 1 FROM acoes_participantes
               WHERE action_id=? AND user_id=?""",
            (self.action_id, interaction.user.id)
        ).fetchone()

        if existing:
            conn.close()
            return await interaction.response.send_message(
                "ℹ️ Você já está participando dessa ação.",
                ephemeral=True
            )

        conn.execute(
            """INSERT INTO acoes_participantes(
                action_id,guild_id,user_id,joined_at
            ) VALUES(?,?,?,?)""",
            (
                self.action_id,
                interaction.guild.id,
                interaction.user.id,
                now_iso()
            )
        )
        conn.commit()
        conn.close()

        await interaction.response.edit_message(
            embed=build_action_embed(interaction.guild, self.action_id),
            view=ActionDetailView(self.action_id)
        )

    @discord.ui.button(
        label="Sair",
        emoji="🚪",
        style=discord.ButtonStyle.secondary
    )
    async def leave(self, interaction, button):
        row = get_action(self.action_id)
        if not row:
            return await interaction.response.send_message(
                "❌ Ação não encontrada.",
                ephemeral=True
            )
        if row["status"] != "aberta":
            return await interaction.response.send_message(
                "❌ Essa ação já foi encerrada.",
                ephemeral=True
            )

        # Criador permanece automaticamente na ação
        if interaction.user.id == int(row["creator_id"]):
            return await interaction.response.send_message(
                "❌ O criador da ação não pode sair da lista.",
                ephemeral=True
            )

        conn = connect()
        conn.execute(
            "DELETE FROM acoes_participantes WHERE action_id=? AND user_id=?",
            (self.action_id, interaction.user.id)
        )
        conn.commit()
        conn.close()

        await interaction.response.edit_message(
            embed=build_action_embed(interaction.guild, self.action_id),
            view=ActionDetailView(self.action_id)
        )

    @discord.ui.button(
        label="Atualizar Lista",
        emoji="🔄",
        style=discord.ButtonStyle.secondary
    )
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(
            embed=build_action_embed(interaction.guild, self.action_id),
            view=ActionDetailView(self.action_id)
        )

    @discord.ui.button(
        label="Finalizar Ação",
        emoji="🏁",
        style=discord.ButtonStyle.danger
    )
    async def finish(self, interaction, button):
        row = get_action(self.action_id)
        if not row:
            return await interaction.response.send_message(
                "❌ Ação não encontrada.",
                ephemeral=True
            )
        if row["status"] != "aberta":
            return await interaction.response.send_message(
                "❌ Essa ação já foi encerrada.",
                ephemeral=True
            )

        if interaction.user.id != int(row["creator_id"]) and not is_admin(interaction.user):
            return await deny(
                interaction,
                "❌ Só quem criou a ação pode finalizar."
            )

        await interaction.response.send_message(
            "🏁 Qual foi o resultado da ação?",
            view=ActionResultView(self.action_id, int(row["creator_id"])),
            ephemeral=True
        )


class AcoesPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Criar Ação",
        emoji="➕",
        style=discord.ButtonStyle.success,
        custom_id="public:action:create"
    )
    async def create_action(self, interaction, button):
        if not enabled(interaction.guild.id, "acoes"):
            return await deny(interaction, "❌ Sistema desligado.")
        if not has_access(interaction.user, "acoes"):
            return await deny(interaction)

        await interaction.response.send_modal(CreateActionModal())

    @discord.ui.button(
        label="Ações Abertas",
        emoji="🎯",
        style=discord.ButtonStyle.primary,
        custom_id="public:action:open"
    )
    async def open_actions(self, interaction, button):
        if not enabled(interaction.guild.id, "acoes"):
            return await deny(interaction, "❌ Sistema desligado.")

        rows = get_actions(interaction.guild.id, only_open=True, limit=25)
        if not rows:
            return await interaction.response.send_message(
                "📭 Não existe nenhuma ação aberta no momento.",
                ephemeral=True
            )

        await interaction.response.send_message(
            embed=build_actions_list_embed(interaction.guild, only_open=True),
            view=ActionBrowserView(interaction.guild.id, only_open=True),
            ephemeral=True
        )

    @discord.ui.button(
        label="Histórico",
        emoji="📜",
        style=discord.ButtonStyle.secondary,
        custom_id="public:action:history"
    )
    async def history(self, interaction, button):
        rows = get_actions(interaction.guild.id, only_open=False, limit=25)
        if not rows:
            return await interaction.response.send_message(
                "📭 Ainda não existe histórico de ações.",
                ephemeral=True
            )

        await interaction.response.send_message(
            embed=build_actions_list_embed(interaction.guild, only_open=False),
            view=ActionBrowserView(interaction.guild.id, only_open=False),
            ephemeral=True
        )

# ============================================================
# MODERAÇÃO / HIERARQUIA / RANKING
# ============================================================


# ============================================================
# PAINEL COMPLETO DE ADVERTÊNCIAS
# ============================================================

def warning_rows(guild_id: int, user_id: int | None = None, active_only=False, limit=50):
    conn = connect()
    sql = "SELECT * FROM advertencias WHERE guild_id=?"
    args = [guild_id]

    if user_id is not None:
        sql += " AND user_id=?"
        args.append(user_id)

    if active_only:
        sql += " AND COALESCE(active,1)=1"

    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)

    rows = conn.execute(sql, tuple(args)).fetchall()
    conn.close()
    return rows


def warning_member_embed(guild: discord.Guild, user_id: int):
    rows = warning_rows(guild.id, user_id=user_id, active_only=False, limit=20)
    member = guild.get_member(user_id)
    name = member.display_name if member else f"ID {user_id}"

    active = [r for r in rows if int(r["active"] or 0) == 1]
    active_points = sum(int(r["pontos"] or 0) for r in active)
    total_points = sum(int(r["pontos"] or 0) for r in rows)

    lines = []
    for r in rows[:15]:
        icon = "🟠" if int(r["active"] or 0) == 1 else "⚫"
        status = "ATIVA" if int(r["active"] or 0) == 1 else "REMOVIDA"
        lines.append(
            f"{icon} **ADV#{r['id']} • {status} • {r['pontos']} pts**\n"
            f"{r['motivo']}\n"
            f"Aplicada por <@{r['moderator_id']}>"
        )

    return embed(
        f"⚠️ Advertências • {name}",
        (
            f"**Ativas:** {len(active)}\n"
            f"**Pontos ativos:** {active_points}\n"
            f"**Pontos históricos:** {total_points}\n\n"
            + ("\n\n".join(lines) if lines else "Nenhuma advertência registrada.")
        ),
        guild_id=guild.id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )


def warnings_ranking_embed(guild: discord.Guild):
    conn = connect()
    rows = conn.execute(
        """SELECT user_id,
                  COUNT(*) qtd,
                  SUM(pontos) pontos
           FROM advertencias
           WHERE guild_id=? AND COALESCE(active,1)=1
           GROUP BY user_id
           ORDER BY pontos DESC, qtd DESC
           LIMIT 20""",
        (guild.id,)
    ).fetchall()
    conn.close()

    lines = [
        f"**{i+1}.** <@{r['user_id']}> — **{r['pontos'] or 0} pts** • {r['qtd']} advertência(s)"
        for i, r in enumerate(rows)
    ]

    return embed(
        "⚠️ Ranking de Advertências Ativas",
        "\n".join(lines) or "Nenhuma advertência ativa.",
        guild_id=guild.id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )


class WarningReasonModal(discord.ui.Modal, title="Aplicar Advertência"):
    motivo = discord.ui.TextInput(
        label="Motivo da advertência",
        style=discord.TextStyle.paragraph,
        placeholder="Descreva o motivo...",
        max_length=800
    )

    def __init__(self, member_id: int, points: int):
        super().__init__()
        self.member_id = int(member_id)
        self.points = int(points)

    async def on_submit(self, interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)

        member = interaction.guild.get_member(self.member_id)
        if not member:
            return await interaction.response.send_message(
                "❌ Membro não encontrado.",
                ephemeral=True
            )

        conn = connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO advertencias(
                guild_id,user_id,moderator_id,motivo,pontos,created_at,active
            ) VALUES(?,?,?,?,?,?,1)""",
            (
                interaction.guild.id,
                member.id,
                interaction.user.id,
                str(self.motivo),
                self.points,
                now_iso()
            )
        )
        warning_id = cur.lastrowid
        conn.commit()
        conn.close()

        await log_event(
            interaction.guild,
            "advertencias",
            f"⚠️ Advertência ADV#{warning_id}",
            (
                f"**Membro:** {member.mention}\n"
                f"**Pontos:** {self.points}\n"
                f"**Motivo:** {self.motivo}\n"
                f"**Responsável:** {interaction.user.mention}"
            ),
            RED
        )

        try:
            await member.send(
                embed=embed(
                    "⚠️ Você recebeu uma advertência",
                    (
                        f"**Servidor:** {interaction.guild.name}\n"
                        f"**Pontos:** {self.points}\n"
                        f"**Motivo:** {self.motivo}"
                    ),
                    RED,
                    guild_id=interaction.guild.id
                )
            )
        except Exception:
            pass

        await interaction.response.edit_message(
            content=f"✅ Advertência **ADV#{warning_id}** aplicada em {member.mention}.",
            embed=warning_member_embed(interaction.guild, member.id),
            view=WarningMemberPanel(member.id)
        )


class WarningPointsView(discord.ui.View):
    def __init__(self, member_id: int):
        super().__init__(timeout=120)
        self.member_id = int(member_id)

    async def open_reason(self, interaction, points):
        await interaction.response.send_modal(
            WarningReasonModal(self.member_id, points)
        )

    @discord.ui.button(label="1 ponto", style=discord.ButtonStyle.secondary)
    async def p1(self, interaction, button):
        await self.open_reason(interaction, 1)

    @discord.ui.button(label="2 pontos", style=discord.ButtonStyle.secondary)
    async def p2(self, interaction, button):
        await self.open_reason(interaction, 2)

    @discord.ui.button(label="3 pontos", style=discord.ButtonStyle.primary)
    async def p3(self, interaction, button):
        await self.open_reason(interaction, 3)

    @discord.ui.button(label="4 pontos", style=discord.ButtonStyle.danger)
    async def p4(self, interaction, button):
        await self.open_reason(interaction, 4)

    @discord.ui.button(label="5 pontos", style=discord.ButtonStyle.danger)
    async def p5(self, interaction, button):
        await self.open_reason(interaction, 5)


class WarningRemoveReasonModal(discord.ui.Modal, title="Remover Advertência"):
    motivo = discord.ui.TextInput(
        label="Motivo da remoção",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: punição cumprida, aplicada por engano...",
        max_length=500
    )

    def __init__(self, warning_id: int, member_id: int):
        super().__init__()
        self.warning_id = int(warning_id)
        self.member_id = int(member_id)

    async def on_submit(self, interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)

        conn = connect()
        row = conn.execute(
            """SELECT * FROM advertencias
               WHERE id=? AND guild_id=?""",
            (self.warning_id, interaction.guild.id)
        ).fetchone()

        if not row or int(row["active"] or 0) != 1:
            conn.close()
            return await interaction.response.send_message(
                "❌ Essa advertência não está ativa.",
                ephemeral=True
            )

        conn.execute(
            """UPDATE advertencias
               SET active=0, removed_by=?, removed_at=?, removal_reason=?
               WHERE id=?""",
            (
                interaction.user.id,
                now_iso(),
                str(self.motivo),
                self.warning_id
            )
        )
        conn.commit()
        conn.close()

        await log_event(
            interaction.guild,
            "advertencias",
            f"🗑️ Advertência ADV#{self.warning_id} removida",
            (
                f"**Membro:** <@{self.member_id}>\n"
                f"**Motivo da remoção:** {self.motivo}\n"
                f"**Responsável:** {interaction.user.mention}"
            ),
            GREEN
        )

        member = interaction.guild.get_member(self.member_id)
        if member:
            try:
                await member.send(
                    embed=embed(
                        "✅ Advertência removida",
                        (
                            f"A advertência **ADV#{self.warning_id}** foi removida.\n"
                            f"**Motivo:** {self.motivo}"
                        ),
                        GREEN,
                        guild_id=interaction.guild.id
                    )
                )
            except Exception:
                pass

        await interaction.response.edit_message(
            content=f"✅ Advertência **ADV#{self.warning_id}** removida.",
            embed=warning_member_embed(interaction.guild, self.member_id),
            view=WarningMemberPanel(self.member_id)
        )


class ActiveWarningSelect(discord.ui.Select):
    def __init__(self, guild_id: int, member_id: int):
        rows = warning_rows(
            guild_id,
            user_id=member_id,
            active_only=True,
            limit=25
        )
        self.member_id = int(member_id)

        options = [
            discord.SelectOption(
                label=f"ADV#{r['id']} • {r['pontos']} pts",
                value=str(r["id"]),
                description=str(r["motivo"])[:100],
                emoji="⚠️"
            )
            for r in rows
        ]

        if not options:
            options = [
                discord.SelectOption(
                    label="Nenhuma advertência ativa",
                    value="none",
                    emoji="✅"
                )
            ]

        super().__init__(
            placeholder="Selecione a advertência para remover",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message(
                "✅ Esse membro não possui advertências ativas.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            WarningRemoveReasonModal(
                int(self.values[0]),
                self.member_id
            )
        )


class ActiveWarningSelectView(discord.ui.View):
    def __init__(self, guild_id: int, member_id: int):
        super().__init__(timeout=120)
        self.add_item(ActiveWarningSelect(guild_id, member_id))


class WarningMemberPanel(discord.ui.View):
    def __init__(self, member_id: int):
        super().__init__(timeout=180)
        self.member_id = int(member_id)

    @discord.ui.button(
        label="Aplicar Advertência",
        emoji="⚠️",
        style=discord.ButtonStyle.danger
    )
    async def add_warning(self, interaction, button):
        if not is_admin(interaction.user):
            return await deny(interaction)

        await interaction.response.send_message(
            "Escolha a quantidade de pontos:",
            view=WarningPointsView(self.member_id),
            ephemeral=True
        )

    @discord.ui.button(
        label="Remover Advertência",
        emoji="🗑️",
        style=discord.ButtonStyle.secondary
    )
    async def remove_warning(self, interaction, button):
        if not is_admin(interaction.user):
            return await deny(interaction)

        await interaction.response.send_message(
            "Selecione uma advertência ativa:",
            view=ActiveWarningSelectView(
                interaction.guild.id,
                self.member_id
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="Atualizar",
        emoji="🔄",
        style=discord.ButtonStyle.secondary
    )
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(
            embed=warning_member_embed(
                interaction.guild,
                self.member_id
            ),
            view=self
        )


class WarningMemberSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Selecione o membro",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction):
        member = self.values[0]
        await interaction.response.edit_message(
            content=None,
            embed=warning_member_embed(
                interaction.guild,
                member.id
            ),
            view=WarningMemberPanel(member.id)
        )


class WarningMemberSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(WarningMemberSelect())


class AdvertenciasPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="Selecionar Membro",
        emoji="👤",
        style=discord.ButtonStyle.primary
    )
    async def select_member(self, interaction, button):
        if not is_admin(interaction.user):
            return await deny(interaction)

        await interaction.response.edit_message(
            content="👤 Selecione o membro:",
            embed=None,
            view=WarningMemberSelectView()
        )

    @discord.ui.button(
        label="Ranking",
        emoji="📊",
        style=discord.ButtonStyle.secondary
    )
    async def ranking(self, interaction, button):
        if not is_admin(interaction.user):
            return await deny(interaction)

        await interaction.response.edit_message(
            content=None,
            embed=warnings_ranking_embed(interaction.guild),
            view=AdvertenciasPanel()
        )


@app_commands.command(
    name="painel-advertencias",
    description="Abre o painel completo de advertências"
)
async def painel_advertencias(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)

    await interaction.response.send_message(
        embed=embed(
            "⚠️ Painel de Advertências",
            (
                "Selecione um membro para **consultar**, **aplicar** "
                "ou **remover** advertências.\n\n"
                "As alterações ficam registradas nos logs."
            ),
            guild_id=interaction.guild.id,
            use_theme_image=False,
            use_theme_thumbnail=True
        ),
        view=AdvertenciasPanel(),
        ephemeral=True
    )


@app_commands.command(name="advertir", description="Aplica advertência em um membro")
async def advertir(interaction: discord.Interaction, membro: discord.Member, motivo: str, pontos: app_commands.Range[int,1,5] = 1):
    if not is_admin(interaction.user):
        return await deny(interaction)
    conn = connect()
    conn.execute(
        """INSERT INTO advertencias(
            guild_id,user_id,moderator_id,motivo,pontos,created_at,active
        ) VALUES(?,?,?,?,?,?,1)""",
        (interaction.guild.id, membro.id, interaction.user.id, motivo, pontos, now_iso())
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message(
        embed=embed(
            "⚠️ Advertência",
            f"{membro.mention}\n**Motivo:** {motivo}\n**Pontos:** {pontos}\n**Responsável:** {interaction.user.mention}",
            RED
        )
    )
    await log_event(
        interaction.guild,
        "advertencias",
        "⚠️ Nova Advertência",
        f"**Membro:** {membro.mention}\n**Motivo:** {motivo}\n**Pontos:** {pontos}\n**Responsável:** {interaction.user.mention}",
        RED
    )

@app_commands.command(name="promover", description="Adiciona um cargo a um membro")
async def promover(interaction: discord.Interaction, membro: discord.Member, cargo: discord.Role):
    if not is_admin(interaction.user):
        return await deny(interaction)
    if cargo >= interaction.guild.me.top_role:
        return await deny(interaction, "❌ Esse cargo está acima do cargo do bot.")
    await membro.add_roles(cargo, reason=f"Promoção por {interaction.user}")
    add_points(interaction.guild.id, membro.id, 5)
    await interaction.response.send_message(f"✅ {membro.mention} recebeu {cargo.mention}.")

@app_commands.command(name="rebaixar", description="Remove um cargo de um membro")
async def rebaixar(interaction: discord.Interaction, membro: discord.Member, cargo: discord.Role):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await membro.remove_roles(cargo, reason=f"Rebaixamento por {interaction.user}")
    await interaction.response.send_message(f"✅ {cargo.mention} removido de {membro.mention}.")


class TeamMemberSelect(discord.ui.UserSelect):
    def __init__(self, mode):
        self.mode = mode
        super().__init__(placeholder="Selecione um membro", min_values=1, max_values=1)

    async def callback(self, interaction):
        member = self.values[0]
        if self.mode == "warnings":
            conn = connect()
            rows = conn.execute(
                """SELECT id,motivo,pontos,created_at FROM advertencias
                   WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 15""",
                (interaction.guild.id, member.id)
            ).fetchall()
            conn.close()
            lines=[f"**ADV#{r['id']}** • {r['pontos']} pts\n{r['motivo']}" for r in rows]
            return await interaction.response.edit_message(
                content=None,
                embed=embed(
                    f"⚠️ Advertências • {member.display_name}",
                    "\n\n".join(lines) or "Nenhuma advertência.",
                    guild_id=interaction.guild.id
                ),
                view=TeamPanel()
            )

        await interaction.response.edit_message(
            content=f"👤 Membro selecionado: {member.mention}\nAgora escolha o cargo:",
            view=TeamRoleView(member.id, self.mode)
        )


class TeamMemberView(discord.ui.View):
    def __init__(self, mode):
        super().__init__(timeout=120)
        self.add_item(TeamMemberSelect(mode))


class TeamRoleSelect(discord.ui.RoleSelect):
    def __init__(self, member_id, mode):
        self.member_id=int(member_id)
        self.mode=mode
        super().__init__(placeholder="Selecione o cargo", min_values=1, max_values=1)

    async def callback(self, interaction):
        member=interaction.guild.get_member(self.member_id)
        role=self.values[0]
        if not member:
            return await interaction.response.send_message("❌ Membro não encontrado.", ephemeral=True)
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ Esse cargo está acima do cargo do bot.", ephemeral=True)
        if self.mode=="promote":
            await member.add_roles(role, reason=f"Promoção por {interaction.user}")
            add_points(interaction.guild.id, member.id, 5)
            title="⬆️ Promoção"
            msg=f"{member.mention} recebeu {role.mention}."
        else:
            await member.remove_roles(role, reason=f"Rebaixamento por {interaction.user}")
            title="⬇️ Rebaixamento"
            msg=f"{role.mention} removido de {member.mention}."
        await log_event(interaction.guild, "hierarquia", title, f"{msg}\nResponsável: {interaction.user.mention}")
        await interaction.response.edit_message(content=f"✅ {msg}", embed=None, view=TeamPanel())


class TeamRoleView(discord.ui.View):
    def __init__(self, member_id, mode):
        super().__init__(timeout=120)
        self.add_item(TeamRoleSelect(member_id, mode))


class TeamPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Promover", emoji="⬆️", style=discord.ButtonStyle.success)
    async def promote(self, interaction, button):
        if not is_admin(interaction.user):
            return await deny(interaction)
        await interaction.response.edit_message(content="👤 Selecione o membro:", embed=None, view=TeamMemberView("promote"))

    @discord.ui.button(label="Rebaixar", emoji="⬇️", style=discord.ButtonStyle.danger)
    async def demote(self, interaction, button):
        if not is_admin(interaction.user):
            return await deny(interaction)
        await interaction.response.edit_message(content="👤 Selecione o membro:", embed=None, view=TeamMemberView("demote"))

    @discord.ui.button(label="Ver Advertências", emoji="⚠️", style=discord.ButtonStyle.secondary)
    async def warnings(self, interaction, button):
        if not is_admin(interaction.user):
            return await deny(interaction)
        await interaction.response.edit_message(content="👤 Selecione o membro:", embed=None, view=TeamMemberView("warnings"))


@app_commands.command(name="painel-equipe", description="Abre o painel de hierarquia e advertências")
async def painel_equipe(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await interaction.response.send_message(
        embed=embed(
            "👥 Gestão da Equipe",
            "Promova, rebaixe e consulte advertências usando os botões abaixo.",
            guild_id=interaction.guild.id,
            use_theme_image=False,
            use_theme_thumbnail=True
        ),
        view=TeamPanel(),
        ephemeral=True
    )


@app_commands.command(name="ranking", description="Mostra o ranking geral")
async def ranking(interaction: discord.Interaction):
    conn = connect()
    rows = conn.execute(
        "SELECT user_id,pontos FROM pontos WHERE guild_id=? ORDER BY pontos DESC LIMIT 15",
        (interaction.guild.id,)
    ).fetchall()
    conn.close()
    lines = [f"**{i+1}.** <@{r['user_id']}> — **{r['pontos']} pts**" for i, r in enumerate(rows)]
    await interaction.response.send_message(embed=embed("🏆 Ranking Geral", "\n".join(lines) or "Sem pontuação."))

# ============================================================
# PDF DE FARM (SEM DEPENDÊNCIA EXTERNA)
# ============================================================

def pdf_escape(s):
    return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def simple_pdf(title, lines):
    page_chunks = [lines[i:i+40] for i in range(0, len(lines), 40)] or [["Sem dados."]]
    objs = []
    objs.append("<< /Type /Catalog /Pages 2 0 R >>")
    page_nums = []
    content_nums = []
    n = 4
    for _ in page_chunks:
        page_nums.append(n)
        content_nums.append(n+1)
        n += 2
    objs.append(f"<< /Type /Pages /Kids [{' '.join(f'{x} 0 R' for x in page_nums)}] /Count {len(page_nums)} >>")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, chunk in enumerate(page_chunks):
        commands = ["BT", "/F1 15 Tf", "40 800 Td", f"({pdf_escape(title)}) Tj", "0 -26 Td", "/F1 9 Tf"]
        for line in chunk:
            clean = str(line).encode("latin-1", "replace").decode("latin-1")[:120]
            commands += [f"({pdf_escape(clean)}) Tj", "0 -16 Td"]
        commands.append("ET")
        stream = "\n".join(commands)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_nums[i]} 0 R >>")
        objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{idx} 0 obj\n{obj}\nendobj\n".encode("latin-1", "replace"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    out.seek(0)
    return out

@app_commands.command(name="relatorio-farm", description="Gera relatório PDF do farm")
async def relatorio_farm(interaction: discord.Interaction):
    if not is_admin(interaction.user) and not can_approve(interaction.user, "farm"):
        return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    conn = connect()
    rows = conn.execute(
        "SELECT user_id,item,quantidade,status,created_at FROM farms WHERE guild_id=? ORDER BY id DESC LIMIT 500",
        (interaction.guild.id,)
    ).fetchall()
    conn.close()
    lines = [
        f"{r['created_at'][:10]} | {r['user_id']} | {r['item']} | {r['quantidade']} | {r['status']}"
        for r in rows
    ]
    await interaction.followup.send(
        file=discord.File(simple_pdf(f"Relatorio de Farm - {FAC_NAME}", lines), filename="relatorio_farm.pdf"),
        ephemeral=True
    )

# ============================================================
# BACKUP
# ============================================================

async def create_backup(guild):
    data = {
        "name": guild.name,
        "created_at": now_iso(),
        "roles": [
            {"name": r.name, "permissions": r.permissions.value, "color": r.color.value}
            for r in guild.roles if not r.is_default() and not r.managed
        ],
        "categories": [{"name": c.name} for c in guild.categories],
        "channels": [
            {
                "name": ch.name,
                "type": "text" if isinstance(ch, discord.TextChannel) else "voice" if isinstance(ch, discord.VoiceChannel) else "other",
                "category": ch.category.name if ch.category else None
            }
            for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)
        ],
        "configs": {key: get_config(guild.id, key) for key in SYSTEMS}
    }
    path = BACKUP_DIR / f"{guild.id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

@app_commands.command(name="backup", description="Cria backup da estrutura e configurações")
async def backup_cmd(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    path = await create_backup(interaction.guild)
    await interaction.followup.send(file=discord.File(path), ephemeral=True)

@tasks.loop(hours=6)
async def backup_loop():
    for guild in bot.guilds:
        try:
            if not get_config(guild.id, "backup").get("auto_backup_enabled", True):
                continue
            await create_backup(guild)
        except Exception:
            traceback.print_exc()

@backup_loop.before_loop
async def before_backup():
    await bot.wait_until_ready()

# ============================================================
# LOGS / SEGURANÇA
# ============================================================

spam = defaultdict(lambda: deque(maxlen=8))
joins = defaultdict(lambda: deque(maxlen=15))

@bot.event
async def on_message(message):
    if not message.guild or message.author.bot:
        return
    q = spam[(message.guild.id, message.author.id)]
    q.append(time.monotonic())
    scfg = get_config(message.guild.id, "seguranca")
    spam_count = max(2, int(scfg.get("spam_count", 6)))
    spam_window = max(1, int(scfg.get("spam_window", 5)))
    spam_timeout = max(1, int(scfg.get("spam_timeout", 45)))
    if scfg.get("anti_spam_enabled", True) and len(q) >= spam_count and q[-1] - q[-spam_count] <= spam_window:
        try:
            await message.author.timeout(
                discord.utils.utcnow() + timedelta(seconds=spam_timeout),
                reason="Anti-spam"
            )
        except Exception:
            pass
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    # Todo novo membro começa como Visitante. O cargo é localizado pela
    # configuração do Registro e, como segurança, também pelo nome do cargo.
    rcfg = get_config(member.guild.id, "registro")
    visitor_role = None
    if rcfg.get("visitor_role_id"):
        visitor_role = member.guild.get_role(int(rcfg["visitor_role_id"]))
    if visitor_role is None:
        visitor_role = discord.utils.find(
            lambda role: role.name.casefold().replace("👤", "").strip() == "visitante",
            member.guild.roles,
        )
    if visitor_role is not None:
        try:
            await member.add_roles(visitor_role, reason="Cargo automático de entrada")
        except discord.Forbidden:
            print(
                f"⚠️ Não consegui aplicar Visitante a {member}. "
                "Coloque o cargo do bot acima do cargo Visitante."
            )
        except discord.HTTPException as exc:
            print(f"⚠️ Falha ao aplicar Visitante a {member}: {exc}")

    # Boas-vindas configurável
    wcfg = get_config(member.guild.id, "boas_vindas")
    if wcfg.get("enabled"):
        text = str(wcfg.get("welcome_message", "Bem-vindo(a), {membro}!"))
        text = text.replace("{membro}", member.mention).replace("{servidor}", member.guild.name)
        try:
            await member.send(embed=embed("🏠 Boas Vindas", text, GREEN, wcfg.get("embed_url", "")))
        except Exception:
            pass

        public_cid = wcfg.get("welcome_channel_id")
        if public_cid:
            public_ch = member.guild.get_channel(int(public_cid))
            if isinstance(public_ch, discord.TextChannel):
                try:
                    await public_ch.send(embed=embed("🏠 Boas Vindas", text, GREEN, wcfg.get("embed_url", "")))
                except Exception:
                    pass

        await log_event(member.guild, "boas_vindas", "📥 Novo Membro", f"{member.mention} entrou no servidor.", GREEN)

    q = joins[member.guild.id]
    q.append(time.monotonic())
    scfg = get_config(member.guild.id, "seguranca")
    raid_count = max(2, int(scfg.get("raid_count", 10)))
    raid_window = max(1, int(scfg.get("raid_window", 15)))
    if scfg.get("anti_raid_enabled", True) and len(q) >= raid_count and q[-1] - q[-raid_count] <= raid_window:
        await log_event(
            member.guild,
            "seguranca",
            "🚨 Possível Raid Detectada",
            f"{raid_count} ou mais membros entraram em aproximadamente {raid_window} segundos.",
            RED
        )

@bot.event
async def on_message_delete(message):
    if not message.guild or message.author.bot:
        return
    # Usa primeiro canal de log configurado encontrado.
    for key in SYSTEMS:
        cfg = get_config(message.guild.id, key)
        if cfg.get("log_channel_id"):
            await log_event(
                message.guild, key, "🗑️ Mensagem Apagada",
                f"**Autor:** {message.author.mention}\n**Canal:** {message.channel.mention}\n"
                f"**Conteúdo:** {(message.content or 'Sem texto')[:1200]}",
                RED
            )
            break


# ============================================================
# METAS SEMANAIS + PROMOÇÕES + CENTRAL DE INÍCIO
# ============================================================

def week_start_iso():
    now = datetime.now(timezone.utc)
    start = now - timedelta(
        days=now.weekday(),
        hours=now.hour,
        minutes=now.minute,
        seconds=now.second,
        microseconds=now.microsecond
    )
    return start.isoformat()


def weekly_member_stats(guild_id: int, user_id: int):
    start = week_start_iso()
    conn = connect()

    farm_row = conn.execute(
        """SELECT COALESCE(SUM(quantidade),0) total
           FROM farms
           WHERE guild_id=? AND user_id=? AND status='aprovado' AND created_at>=?""",
        (guild_id, user_id, start)
    ).fetchone()

    sales_row = conn.execute(
        """SELECT COALESCE(SUM(total),0) total
           FROM vendas
           WHERE guild_id=? AND user_id=? AND created_at>=?""",
        (guild_id, user_id, start)
    ).fetchone()

    actions_row = conn.execute(
        """SELECT COUNT(DISTINCT ap.action_id) total
           FROM acoes_participantes ap
           JOIN acoes a ON a.id=ap.action_id
           WHERE ap.guild_id=? AND ap.user_id=?
             AND a.status!='aberta'
             AND COALESCE(a.closed_at,a.created_at)>=?""",
        (guild_id, user_id, start)
    ).fetchone()

    points_row = conn.execute(
        "SELECT pontos FROM pontos WHERE guild_id=? AND user_id=?",
        (guild_id, user_id)
    ).fetchone()

    warnings_row = conn.execute(
        """SELECT COUNT(*) qtd, COALESCE(SUM(pontos),0) pontos
           FROM advertencias
           WHERE guild_id=? AND user_id=? AND active=1""",
        (guild_id, user_id)
    ).fetchone()

    conn.close()
    return {
        "farm": int(farm_row["total"] or 0),
        "sales": float(sales_row["total"] or 0),
        "actions": int(actions_row["total"] or 0),
        "points": int(points_row["pontos"] if points_row else 0),
        "warnings": int(warnings_row["qtd"] or 0),
        "warning_points": int(warnings_row["pontos"] or 0),
    }


def goal_bar(current, goal, size=10):
    if goal <= 0:
        return "██████████ 100%"
    ratio = max(0.0, min(float(current) / float(goal), 1.0))
    filled = round(ratio * size)
    pct = round(ratio * 100)
    return "█" * filled + "░" * (size - filled) + f" {pct}%"


def metas_embed_for_member(guild: discord.Guild, member: discord.Member):
    cfg = get_config(guild.id, "metas")
    stats = weekly_member_stats(guild.id, member.id)
    farm_goal = max(0, int(cfg.get("weekly_farm_goal", 500)))
    sales_goal = max(0, float(cfg.get("weekly_sales_goal", 2000000)))
    actions_goal = max(0, int(cfg.get("weekly_actions_goal", 3)))

    desc = (
        f"**Membro:** {member.mention}\n"
        f"**Semana iniciada em:** <t:{int(datetime.fromisoformat(week_start_iso()).timestamp())}:d>\n\n"
        f"📦 **Farm:** {stats['farm']}/{farm_goal}\n`{goal_bar(stats['farm'], farm_goal)}`\n\n"
        f"💰 **Vendas:** {money(stats['sales'])}/{money(sales_goal)}\n"
        f"`{goal_bar(stats['sales'], sales_goal)}`\n\n"
        f"🎯 **Ações:** {stats['actions']}/{actions_goal}\n"
        f"`{goal_bar(stats['actions'], actions_goal)}`"
    )
    return embed(
        "🎯 Metas Semanais",
        desc,
        guild_id=guild.id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )


def weekly_ranking_embed(guild: discord.Guild):
    cfg = get_config(guild.id, "metas")
    farm_goal = max(1, int(cfg.get("weekly_farm_goal", 500)))
    sales_goal = max(1.0, float(cfg.get("weekly_sales_goal", 2000000)))
    actions_goal = max(1, int(cfg.get("weekly_actions_goal", 3)))

    candidates = [m for m in guild.members if not m.bot]
    rows = []
    for member in candidates:
        st = weekly_member_stats(guild.id, member.id)
        score = (
            min(st["farm"] / farm_goal, 1.0) +
            min(st["sales"] / sales_goal, 1.0) +
            min(st["actions"] / actions_goal, 1.0)
        ) / 3 * 100
        if st["farm"] or st["sales"] or st["actions"]:
            rows.append((score, member.id, st))
    rows.sort(reverse=True, key=lambda x: x[0])
    lines = []
    for i, (score, uid, st) in enumerate(rows[:15], 1):
        lines.append(
            f"**{i}.** <@{uid}> — **{score:.0f}%** "
            f"• 📦 {st['farm']} • 💰 {money(st['sales'])} • 🎯 {st['actions']}"
        )
    return embed(
        "🏆 Ranking Semanal",
        "\n".join(lines) or "Ainda não há atividade registrada nesta semana.",
        guild_id=guild.id,
        use_theme_image=False,
        use_theme_thumbnail=True
    )


class WeeklyGoalsModal(discord.ui.Modal, title="Configurar Metas Semanais"):
    farm = discord.ui.TextInput(label="Meta de farm", placeholder="500", max_length=12)
    sales = discord.ui.TextInput(label="Meta de vendas (R$)", placeholder="2000000", max_length=20)
    actions = discord.ui.TextInput(label="Meta de participação em ações", placeholder="3", max_length=6)

    async def on_submit(self, interaction):
        if not is_admin(interaction.user):
            return await deny(interaction)
        try:
            farm = parse_int(self.farm)
            sales = parse_money(self.sales)
            actions = parse_int(self.actions)
            if farm < 0 or sales < 0 or actions < 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Informe metas válidas.", ephemeral=True)

        update_config(
            interaction.guild.id,
            "metas",
            enabled=True,
            weekly_farm_goal=farm,
            weekly_sales_goal=sales,
            weekly_actions_goal=actions
        )
        await interaction.response.send_message(
            f"✅ Metas atualizadas:\n📦 **{farm}**\n💰 **{money(sales)}**\n🎯 **{actions} ações**",
            ephemeral=True
        )


class MetasPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Minhas Metas", emoji="🎯", style=discord.ButtonStyle.primary, custom_id="public:metas:me")
    async def my_goals(self, interaction, button):
        await interaction.response.send_message(
            embed=metas_embed_for_member(interaction.guild, interaction.user),
            ephemeral=True
        )

    @discord.ui.button(label="Ranking Semanal", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="public:metas:rank")
    async def rank(self, interaction, button):
        await interaction.response.send_message(
            embed=weekly_ranking_embed(interaction.guild),
            ephemeral=True
        )


class ComeceAquiView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Registro", emoji="👤", style=discord.ButtonStyle.success, custom_id="public:inicio:registro")
    async def registro(self, interaction, button):
        if not enabled(interaction.guild.id, "registro"):
            return await deny(interaction, "❌ O sistema de registro está desligado.")
        await interaction.response.send_modal(RegistroModal())

    @discord.ui.button(label="Minhas Metas", emoji="🎯", style=discord.ButtonStyle.primary, custom_id="public:inicio:metas")
    async def metas(self, interaction, button):
        await interaction.response.send_message(
            embed=metas_embed_for_member(interaction.guild, interaction.user),
            ephemeral=True
        )

    @discord.ui.button(label="Ranking", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="public:inicio:ranking")
    async def ranking(self, interaction, button):
        await interaction.response.send_message(
            embed=await ranking_embed_for_guild(interaction.guild),
            ephemeral=True
        )


def comece_aqui_embed(guild: discord.Guild):
    rules = next((c for c in guild.text_channels if c.name.endswith("regras") or c.name == "regras"), None)
    hierarchy = next((c for c in guild.text_channels if "hierarquia" in c.name.lower()), None)
    register = next((c for c in guild.text_channels if c.name.endswith("registro") or c.name == "registro"), None)
    metas = next((c for c in guild.text_channels if "metas" in c.name.lower()), None)

    def mention(ch):
        return ch.mention if ch else "canal configurado pela liderança"

    desc = (
        "Bem-vindo(a)! Use esta central para seguir o fluxo da organização.\n\n"
        f"**1. 📜 Regras** — leia {mention(rules)}.\n"
        f"**2. 👤 Registro** — faça seu registro em {mention(register)} ou pelo botão abaixo.\n"
        f"**3. 🏰 Hierarquia** — consulte {mention(hierarchy)}.\n"
        "**4. 📦 Participação** — Farm, Vendas e Ações contam para sua atividade.\n"
        f"**5. 🎯 Metas** — acompanhe seu progresso em {mention(metas)} ou pelo botão abaixo.\n"
        "**6. ⬆️ Evolução** — a liderança pode analisar metas, ranking, ações e advertências antes de uma promoção."
    )
    return embed(
        "👋 Comece Aqui",
        desc,
        guild_id=guild.id,
        use_theme_image=True,
        use_theme_thumbnail=True
    )


@app_commands.command(name="metas", description="Mostra suas metas e progresso da semana")
async def metas_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=metas_embed_for_member(interaction.guild, interaction.user),
        ephemeral=True
    )


@app_commands.command(name="configurar-metas", description="Configura as metas semanais da facção")
@app_commands.default_permissions(administrator=True)
async def configurar_metas(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await interaction.response.send_modal(WeeklyGoalsModal())


@app_commands.command(name="analisar-promocao", description="Analisa atividade, metas e advertências de um membro")
@app_commands.default_permissions(administrator=True)
async def analisar_promocao(interaction: discord.Interaction, membro: discord.Member):
    if not is_admin(interaction.user):
        return await deny(interaction)

    cfg = get_config(interaction.guild.id, "metas")
    st = weekly_member_stats(interaction.guild.id, membro.id)
    fg = max(1, int(cfg.get("weekly_farm_goal", 500)))
    sg = max(1.0, float(cfg.get("weekly_sales_goal", 2000000)))
    ag = max(1, int(cfg.get("weekly_actions_goal", 3)))

    activity = (
        min(st["farm"] / fg, 1.0) +
        min(st["sales"] / sg, 1.0) +
        min(st["actions"] / ag, 1.0)
    ) / 3 * 75
    ranking_bonus = min(max(st["points"], 0), 100) / 100 * 25
    penalty = min(st["warning_points"] * 12, 50)
    score = max(0, min(100, round(activity + ranking_bonus - penalty)))

    if score >= 80 and st["warnings"] == 0:
        verdict = "🟢 **Bom candidato para análise da liderança**"
    elif score >= 55:
        verdict = "🟡 **Candidato em observação**"
    else:
        verdict = "🔴 **Ainda precisa evoluir antes da promoção**"

    desc = (
        f"**Membro:** {membro.mention}\n{verdict}\n"
        f"**Índice de apoio:** {score}/100\n\n"
        f"🏆 **Pontos gerais:** {st['points']}\n"
        f"⚠️ **Advertências ativas:** {st['warnings']} ({st['warning_points']} pts)\n"
        f"📦 **Farm semanal:** {st['farm']}/{fg}\n"
        f"💰 **Vendas semanais:** {money(st['sales'])}/{money(sg)}\n"
        f"🎯 **Ações semanais:** {st['actions']}/{ag}\n\n"
        "ℹ️ Este resultado é apenas apoio para a liderança. O bot não promove automaticamente."
    )
    await interaction.response.send_message(
        embed=embed("⬆️ Análise de Promoção", desc, guild_id=interaction.guild.id),
        ephemeral=True
    )


@app_commands.command(name="comece-aqui", description="Envia a central de início no canal atual")
@app_commands.default_permissions(administrator=True)
async def comece_aqui(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await interaction.response.send_message(
        embed=comece_aqui_embed(interaction.guild),
        view=ComeceAquiView()
    )



# ============================================================
# AUTO-CONFIGURAÇÃO DO SERVIDOR
# Usa nomes dos canais/cargos existentes, sem criar nada.
# Gerente é o principal cargo de liberação.
# ============================================================

def _norm_discord_name(value: str) -> str:
    import unicodedata
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _find_text_channel_by_names(guild: discord.Guild, *names):
    targets = {_norm_discord_name(n) for n in names if n}
    for ch in guild.text_channels:
        if _norm_discord_name(ch.name) in targets:
            return ch
    return None


def _find_role_by_names(guild: discord.Guild, *names):
    targets = {_norm_discord_name(n) for n in names if n}
    for role in guild.roles:
        if _norm_discord_name(role.name) in targets:
            return role
    return None


def _role_ids(*roles):
    return [r.id for r in roles if r is not None]


# Estrutura oficial criada/aplicada pelo /reset. As permissões perigosas ficam
# somente com a direção; os demais acessos são controlados por canal/categoria.
ROLE_BLUEPRINT = [
    ("👑 Dono", 0xE74C3C, discord.Permissions(administrator=True)),
    ("👑 Sub-Dono", 0xC0392B, discord.Permissions(administrator=True)),
    ("🔱 Líder", 0xF1C40F, discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True,
        connect=True, speak=True, stream=True, use_voice_activation=True,
        manage_channels=True, manage_roles=True, manage_messages=True,
        manage_nicknames=True, mention_everyone=True,
    )),
    ("🛡️ Sub-Líder", 0xE67E22, discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True,
        connect=True, speak=True, stream=True, use_voice_activation=True,
        manage_messages=True, manage_nicknames=True, mention_everyone=True,
    )),
    ("⚜️ Gerente", 0x9B59B6, discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True,
        connect=True, speak=True, stream=True, use_voice_activation=True,
        manage_messages=True, manage_nicknames=True, mention_everyone=True,
    )),
    ("🎯 Gerente de Ação", 0x3498DB, discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True,
        connect=True, speak=True, stream=True, use_voice_activation=True,
    )),
    ("💼 Gerente de Farm", 0x2ECC71, discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True,
        connect=True, speak=True, stream=True, use_voice_activation=True,
    )),
    ("🔴 Membro", 0xE74C3C, discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True,
        add_reactions=True, attach_files=True, embed_links=True,
        connect=True, speak=True, stream=True, use_voice_activation=True,
        use_application_commands=True,
    )),
    ("🆕 Recruta", 0x95A5A6, discord.Permissions(
        view_channel=True, send_messages=True, read_message_history=True,
        add_reactions=True, attach_files=True, embed_links=True,
        connect=True, speak=True, stream=True, use_voice_activation=True,
        use_application_commands=True,
    )),
    ("👤 Visitante", 0x7F8C8D, discord.Permissions(
        view_channel=True, read_message_history=True,
        use_application_commands=True,
    )),
    ("💤 Ausente", 0x34495E, discord.Permissions(
        view_channel=True, read_message_history=True,
    )),
]


def _ow(view=False, send=False, voice=False, mention=False, manage=False):
    """Overwrite explícito para impedir heranças abertas acidentalmente."""
    return discord.PermissionOverwrite(
        view_channel=view,
        read_message_history=view,
        send_messages=send,
        send_messages_in_threads=send,
        create_public_threads=send,
        create_private_threads=False,
        add_reactions=send,
        attach_files=send,
        embed_links=send,
        use_application_commands=view,
        connect=voice,
        speak=voice,
        stream=voice,
        use_voice_activation=voice,
        mention_everyone=mention,
        manage_messages=manage,
    )


async def _ensure_server_roles(guild: discord.Guild):
    roles = {}
    created = 0
    updated = 0
    for name, color, permissions in reversed(ROLE_BLUEPRINT):
        role = _find_role_by_names(guild, name)
        if role is None:
            role = await guild.create_role(
                name=name, colour=discord.Colour(color), permissions=permissions,
                hoist=name not in {"🔴 Membro", "🆕 Recruta", "👤 Visitante", "💤 Ausente"},
                mentionable=False, reason="Configuração completa pelo /reset",
            )
            created += 1
        else:
            # Não tenta editar cargos gerenciados por integração.
            if not role.managed and guild.me and role < guild.me.top_role:
                await role.edit(
                    name=name, colour=discord.Colour(color), permissions=permissions,
                    hoist=name not in {"🔴 Membro", "🆕 Recruta", "👤 Visitante", "💤 Ausente"},
                    mentionable=False, reason="Atualização completa pelo /reset",
                )
                updated += 1
        roles[_norm_discord_name(name)] = role

    # Tenta colocar os cargos na ordem correta, sempre abaixo do cargo do bot.
    if guild.me:
        ordered = [_find_role_by_names(guild, item[0]) for item in ROLE_BLUEPRINT]
        ordered = [r for r in ordered if r and r < guild.me.top_role and not r.managed]
        if ordered:
            top = max(1, guild.me.top_role.position - 1)
            positions = {role: max(1, top - index) for index, role in enumerate(ordered)}
            try:
                await guild.edit_role_positions(positions=positions, reason="Hierarquia do /reset")
            except discord.HTTPException:
                pass
    return roles, created, updated


def _access_group_for_channel(channel):
    """Retorna o nível de acesso a partir da categoria e das exceções do canal."""
    cname = _norm_discord_name(channel.category.name if channel.category else "")
    chname = _norm_discord_name(channel.name)

    # Exceções sensíveis sempre vencem a regra da categoria.
    if any(x in chname for x in ("logs", "backup", "advertencia", "promoco", "gerenciarmembro", "anuncioprivado", "criadordeembed")):
        return "gestao"
    if any(x in chname for x in ("registrospondentes", "aprovacaofarm", "aprovacaoausencia", "baulideranca")):
        return "staff"
    if chname in {_norm_discord_name(x) for x in ("registro", "boas-vindas", "regras", "informações", "informacoes")}:
        return "entrada"
    if any(x in cname for x in ("lideranca", "gestao", "administracao", "logs")):
        return "gestao"
    if "registro" in cname or any(x in cname for x in ("inicio", "comeceaqui")):
        return "entrada"
    return "membros"


async def _reset_channel_permissions(guild: discord.Guild, roles: dict):
    everyone = guild.default_role
    bot_role = guild.me.top_role if guild.me else None
    get = lambda name: roles.get(_norm_discord_name(name)) or _find_role_by_names(guild, name)

    dono, sub_dono = get("Dono"), get("Sub-Dono")
    lider, sub_lider, gerente = get("Líder"), get("Sub-Líder"), get("Gerente")
    gerente_acao, gerente_farm = get("Gerente de Ação"), get("Gerente de Farm")
    membro, recruta, visitante, ausente = get("Membro"), get("Recruta"), get("Visitante"), get("Ausente")
    all_roles = [r for r in (dono, sub_dono, lider, sub_lider, gerente, gerente_acao, gerente_farm, membro, recruta, visitante, ausente) if r]
    management = [r for r in (dono, sub_dono, lider, sub_lider, gerente) if r]
    staff = list(dict.fromkeys(management + [r for r in (gerente_acao, gerente_farm) if r]))
    members = list(dict.fromkeys(staff + [r for r in (membro, recruta, ausente) if r]))

    async def apply(target, level):
        is_voice = isinstance(target, (discord.VoiceChannel, discord.StageChannel))
        overwrites = {everyone: _ow(False, False, False)}
        if bot_role and not bot_role.is_default():
            overwrites[bot_role] = _ow(True, True, True, True, True)

        if level == "entrada":
            # Apenas os canais de entrada aparecem para quem acabou de chegar.
            if visitante:
                can_write = "registro" in _norm_discord_name(target.name)
                overwrites[visitante] = _ow(True, can_write, False)
            for role in members:
                overwrites[role] = _ow(True, True, is_voice, role in management, role in management)
        elif level == "membros":
            for role in members:
                overwrites[role] = _ow(True, True, is_voice, role in management, role in management)
            if visitante:
                overwrites[visitante] = _ow(False, False, False)
        elif level == "staff":
            for role in staff:
                overwrites[role] = _ow(True, True, is_voice, role in management, role in management)
        else:  # gestão/liderança/logs
            for role in management:
                overwrites[role] = _ow(True, True, is_voice, True, True)

        # Substitui overrides antigos: um allow direto no canal não poderá furar
        # o bloqueio definido pelo reset.
        await target.edit(overwrites=overwrites, reason="Permissões completas pelo /reset")

    for category in guild.categories:
        # A categoria recebe a base; cada canal recebe também um overwrite
        # explícito para neutralizar permissões antigas que estavam abertas.
        fake_level = _access_group_for_channel(category)
        await apply(category, fake_level)
        for channel in category.channels:
            await apply(channel, _access_group_for_channel(channel))

    for channel in [ch for ch in guild.channels if not isinstance(ch, discord.CategoryChannel) and ch.category is None]:
        await apply(channel, _access_group_for_channel(channel))


async def reset_server_setup(guild: discord.Guild):
    roles, created, updated = await _ensure_server_roles(guild)
    await _reset_channel_permissions(guild, roles)
    apply_server_autoconfig(guild)
    # O cargo automático precisa estar ligado; antes o ID era salvo mas a chave
    # continuava False, fazendo o painel dizer que Visitante estava desativado.
    visitante = _find_role_by_names(guild, "👤 Visitante", "Visitante")
    membro = _find_role_by_names(guild, "🔴 Membro", "Membro")
    update_config(
        guild.id, "registro", visitor_enabled=True,
        visitor_role_id=visitante.id if visitante else None,
        approved_role_id=membro.id if membro else None,
    )
    assigned = 0
    faction_roles = {
        _find_role_by_names(guild, item[0]).id
        for item in ROLE_BLUEPRINT
        if _find_role_by_names(guild, item[0]) is not None
    }
    if visitante:
        for member_obj in guild.members:
            if member_obj.bot or member_obj == guild.owner:
                continue
            if not any(role.id in faction_roles for role in member_obj.roles):
                try:
                    await member_obj.add_roles(visitante, reason="Visitante aplicado pelo /reset")
                    assigned += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
    return created, updated, assigned


def apply_server_autoconfig(guild: discord.Guild):
    """Mapeia os canais/cargos já existentes no servidor para os sistemas do bot.

    Não cria nem apaga canais/cargos. Só atualiza IDs de configuração.
    """
    # -------- Cargos --------
    dono = _find_role_by_names(guild, "👑 Dono", "Dono")
    sub_dono = _find_role_by_names(guild, "👑 Sub-Dono", "Sub-Dono")
    lider = _find_role_by_names(guild, "🔱 Líder", "Líder", "Lider")
    sub_lider = _find_role_by_names(guild, "🛡️ Sub-Líder", "Sub-Líder", "Sub-Lider")
    gerente = _find_role_by_names(guild, "⚜️ Gerente", "Gerente")
    gerente_acao = _find_role_by_names(guild, "🎯 Gerente de Ação", "Gerente de Ação", "Gerente de Acao")
    gerente_farm = _find_role_by_names(guild, "💼 Gerente de Farm", "Gerente de Farm")
    membro = _find_role_by_names(guild, "🔴 Membro", "Membro")
    recruta = _find_role_by_names(guild, "🆕 Recruta", "Recruta")
    visitante = _find_role_by_names(guild, "👤 Visitante", "Visitante")
    ausente = _find_role_by_names(guild, "💤 Ausente", "Ausente")

    # Gerente é o principal liberador. Cargos superiores também entram.
    gestao = _role_ids(gerente, sub_lider, lider, sub_dono, dono)
    lideranca = _role_ids(sub_lider, lider, sub_dono, dono)
    aprovadores = _role_ids(gerente, sub_lider, lider, sub_dono, dono)
    farm_staff = _role_ids(gerente_farm, gerente, sub_lider, lider, sub_dono, dono)
    action_staff = _role_ids(gerente_acao, gerente, sub_lider, lider, sub_dono, dono)

    # -------- Canais --------
    canais = {
        "regras": _find_text_channel_by_names(guild, "📜・regras", "📜 regras", "regras"),
        "anuncios": _find_text_channel_by_names(guild, "📢・anúncios", "📢・anuncios", "anúncios", "anuncios"),
        "informacoes": _find_text_channel_by_names(guild, "📋・informações", "📋・informacoes", "informações", "informacoes"),
        "hierarquia": _find_text_channel_by_names(guild, "🎭・hierarquia", "hierarquia"),
        "comandos": _find_text_channel_by_names(guild, "🤖・comandos", "comandos"),

        "registro": _find_text_channel_by_names(guild, "📝・registro", "registro"),
        "registros_pendentes": _find_text_channel_by_names(guild, "⏳・registros-pendentes", "registros-pendentes"),
        "visitantes": _find_text_channel_by_names(guild, "👤・visitantes", "visitantes"),
        "boas_vindas": _find_text_channel_by_names(guild, "👋・boas-vindas", "boas-vindas"),

        "painel_farm": _find_text_channel_by_names(guild, "📦・painel-farm", "painel-farm"),
        "aprovacao_farm": _find_text_channel_by_names(guild, "⏳・aprovação-farm", "⏳・aprovacao-farm", "aprovação-farm", "aprovacao-farm"),
        "ranking_farm": _find_text_channel_by_names(guild, "🏆・ranking-farm", "ranking-farm"),
        "metas": _find_text_channel_by_names(guild, "🎯・metas", "metas"),
        "relatorios_farm": _find_text_channel_by_names(guild, "📊・relatórios-farm", "📊・relatorios-farm", "relatórios-farm", "relatorios-farm"),

        "estoque": _find_text_channel_by_names(guild, "📦・estoque", "estoque"),
        "bau_lideranca": _find_text_channel_by_names(guild, "🔐・baú-liderança", "🔐・bau-lideranca", "baú-liderança", "bau-lideranca"),
        "banco": _find_text_channel_by_names(guild, "🏦・banco", "banco"),
        "vendas": _find_text_channel_by_names(guild, "💵・vendas", "vendas"),
        "encomendas": _find_text_channel_by_names(guild, "📋・encomendas", "encomendas"),
        "lavagem": _find_text_channel_by_names(guild, "💸・lavagem", "lavagem"),
        "ranking_geral": _find_text_channel_by_names(guild, "📊・ranking-geral", "ranking-geral"),

        "painel_acoes": _find_text_channel_by_names(guild, "📋・painel-ações", "📋・painel-acoes", "painel-ações", "painel-acoes"),
        "acoes_marcadas": _find_text_channel_by_names(guild, "📅・ações-marcadas", "📅・acoes-marcadas", "ações-marcadas", "acoes-marcadas"),
        "resultados": _find_text_channel_by_names(guild, "📸・resultados", "resultados"),
        "ranking_acoes": _find_text_channel_by_names(guild, "🏆・ranking-ações", "🏆・ranking-acoes", "ranking-ações", "ranking-acoes"),

        "solicitar_ausencia": _find_text_channel_by_names(guild, "📋・solicitar-ausência", "📋・solicitar-ausencia", "solicitar-ausência", "solicitar-ausencia"),
        "aprovacao_ausencia": _find_text_channel_by_names(guild, "⏳・aprovação-ausência", "⏳・aprovacao-ausencia", "aprovação-ausência", "aprovacao-ausencia"),

        "gerenciar_membros": _find_text_channel_by_names(guild, "👥・gerenciar-membros", "gerenciar-membros"),
        "promocoes": _find_text_channel_by_names(guild, "⬆️・promoções-rebaixamentos", "⬆️・promocoes-rebaixamentos", "promoções-rebaixamentos", "promocoes-rebaixamentos"),
        "advertencias": _find_text_channel_by_names(guild, "⚠️・advertências", "⚠️・advertencias", "advertências", "advertencias"),
        "relatorios": _find_text_channel_by_names(guild, "📊・relatórios", "📊・relatorios", "relatórios", "relatorios"),
        "anuncio_privado": _find_text_channel_by_names(guild, "📢・anúncio-privado", "📢・anuncio-privado", "anúncio-privado", "anuncio-privado"),
        "criador_embeds": _find_text_channel_by_names(guild, "🎨・criador-de-embeds", "criador-de-embeds"),
        "backups": _find_text_channel_by_names(guild, "💾・backups", "backups"),

        "logs_gerais": _find_text_channel_by_names(guild, "📑・logs-gerais", "logs-gerais"),
        "logs_membros": _find_text_channel_by_names(guild, "👥・logs-membros", "logs-membros"),
        "logs_mensagens": _find_text_channel_by_names(guild, "💬・logs-mensagens", "logs-mensagens"),
        "logs_voz": _find_text_channel_by_names(guild, "🔊・logs-voz", "logs-voz"),
        "logs_cargos": _find_text_channel_by_names(guild, "🎭・logs-cargos", "logs-cargos"),
        "logs_financeiro": _find_text_channel_by_names(guild, "💰・logs-financeiro", "logs-financeiro"),
        "logs_farm": _find_text_channel_by_names(guild, "📦・logs-farm", "logs-farm"),
        "logs_seguranca": _find_text_channel_by_names(guild, "🛡️・logs-segurança", "🛡️・logs-seguranca", "logs-segurança", "logs-seguranca"),
    }

    def cid(key):
        ch = canais.get(key)
        return ch.id if ch else None

    # -------- Configurações dos sistemas --------
    # Registro
    update_config(
        guild.id, "registro",
        enabled=True,
        public_channel_id=cid("registro"),
        log_channel_id=cid("registros_pendentes") or cid("logs_membros"),
        access_role_ids=gestao,
        approver_role_ids=aprovadores,
        approved_role_id=(membro.id if membro else None),
        visitor_role_id=(visitante.id if visitante else None),
    )

    # Boas-vindas
    update_config(
        guild.id, "boas_vindas",
        enabled=True,
        welcome_channel_id=cid("boas_vindas"),
        log_channel_id=cid("logs_membros"),
        access_role_ids=gestao,
    )

    # Farm
    update_config(
        guild.id, "farm",
        enabled=True,
        public_channel_id=cid("painel_farm"),
        log_channel_id=cid("logs_farm") or cid("aprovacao_farm"),
        access_role_ids=farm_staff,
        approver_role_ids=farm_staff,
    )

    # Ações
    update_config(
        guild.id, "acoes",
        enabled=True,
        public_channel_id=cid("painel_acoes"),
        log_channel_id=cid("acoes_marcadas") or cid("logs_gerais"),
        access_role_ids=action_staff,
        approver_role_ids=action_staff,
        action_ping_role_id=(gerente_acao.id if gerente_acao else gerente.id if gerente else None),
    )

    # Banco / Vendas / Lavagem / Encomendas / Baú
    for system, public_key in (
        ("banco", "banco"),
        ("vendas", "vendas"),
        ("lavagem", "lavagem"),
        ("encomendas", "encomendas"),
        ("bau", "estoque"),
    ):
        changes = {
            "enabled": True,
            "public_channel_id": cid(public_key),
            "access_role_ids": gestao,
        }
        if system in {"encomendas"}:
            changes["approver_role_ids"] = aprovadores
        if system in {"banco", "vendas", "lavagem"}:
            changes["log_channel_id"] = cid("logs_financeiro")
        elif system == "bau":
            changes["log_channel_id"] = cid("logs_gerais")
            changes["leader_role_ids"] = lideranca
        elif system == "encomendas":
            changes["log_channel_id"] = cid("logs_gerais")
        update_config(guild.id, system, **changes)

    # Ausência
    update_config(
        guild.id, "ausencia",
        enabled=True,
        public_channel_id=cid("solicitar_ausencia"),
        log_channel_id=cid("aprovacao_ausencia"),
        access_role_ids=gestao,
        approver_role_ids=aprovadores,
    )

    # Hierarquia / Ranking
    hierarchy_ids = _role_ids(
        dono, sub_dono, lider, sub_lider, gerente,
        gerente_acao, gerente_farm, membro, recruta
    )
    update_config(
        guild.id, "hierarquia",
        enabled=True,
        public_channel_id=cid("hierarquia"),
        log_channel_id=cid("logs_cargos"),
        access_role_ids=gestao,
        hierarchy_role_ids=hierarchy_ids,
    )
    update_config(
        guild.id, "ranking",
        enabled=True,
        public_channel_id=cid("ranking_geral"),
        log_channel_id=cid("relatorios"),
        access_role_ids=gestao,
    )

    # Advertências e promoções: Gerente é o principal liberador.
    update_config(
        guild.id, "advertencias",
        enabled=True,
        log_channel_id=cid("advertencias"),
        access_role_ids=gestao,
        approver_role_ids=aprovadores,
    )
    update_config(
        guild.id, "promocoes",
        enabled=True,
        log_channel_id=cid("promocoes"),
        access_role_ids=gestao,
        approver_role_ids=aprovadores,
    )

    # Metas
    update_config(
        guild.id, "metas",
        enabled=True,
        public_channel_id=cid("metas"),
        log_channel_id=cid("relatorios_farm") or cid("relatorios"),
        access_role_ids=gestao,
    )

    # Comece Aqui - reaproveita canais existentes.
    update_config(
        guild.id, "inicio",
        enabled=True,
        public_channel_id=cid("informacoes") or cid("comandos"),
        log_channel_id=cid("logs_gerais"),
        access_role_ids=gestao,
        rules_channel_id=cid("regras"),
        hierarchy_channel_id=cid("hierarquia"),
    )

    # Logs / Segurança / Backup / Utilidades
    update_config(
        guild.id, "logs",
        enabled=True,
        log_channel_id=cid("logs_gerais"),
        access_role_ids=gestao,
    )
    update_config(
        guild.id, "seguranca",
        enabled=True,
        log_channel_id=cid("logs_seguranca") or cid("logs_gerais"),
        access_role_ids=gestao,
    )
    update_config(
        guild.id, "backup",
        enabled=True,
        log_channel_id=cid("backups"),
        access_role_ids=gestao,
    )
    update_config(
        guild.id, "utilidades",
        enabled=True,
        log_channel_id=cid("logs_gerais"),
        access_role_ids=gestao,
    )

    # Personalização não é zerada; só garante acesso da gestão.
    update_config(
        guild.id, "personalizacao",
        enabled=True,
        access_role_ids=gestao,
    )

    found_channels = sum(1 for ch in canais.values() if ch is not None)
    found_roles = sum(1 for r in [
        dono, sub_dono, lider, sub_lider, gerente, gerente_acao,
        gerente_farm, membro, recruta, visitante, ausente
    ] if r is not None)
    print(
        f"✅ Auto-configuração aplicada em {guild.name}: "
        f"{found_channels} canais encontrados, {found_roles} cargos encontrados. "
        "Gerente definido como principal cargo de liberação."
    )


# ============================================================
# COMANDOS PRINCIPAIS
# ============================================================

@bot.tree.command(name="reset", description="Configura cargos e todas as permissões do servidor")
@app_commands.default_permissions(administrator=True)
async def reset_cmd(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)
    if interaction.guild is None:
        return await interaction.response.send_message(
            "❌ Use este comando dentro do servidor.", ephemeral=True
        )

    me = interaction.guild.me
    missing = []
    if not me or not me.guild_permissions.manage_roles:
        missing.append("Gerenciar Cargos")
    if not me or not me.guild_permissions.manage_channels:
        missing.append("Gerenciar Canais")
    if missing:
        return await interaction.response.send_message(
            "❌ O cargo do bot precisa destas permissões: **" + ", ".join(missing) +
            "**. Coloque também o cargo do bot acima de todos os cargos da facção.",
            ephemeral=True,
        )

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        created, updated, assigned = await reset_server_setup(interaction.guild)
        await interaction.followup.send(
            "✅ **Servidor configurado com sucesso.**\n"
            f"• Cargos criados: **{created}**\n"
            f"• Cargos atualizados: **{updated}**\n"
            f"• Visitantes aplicados agora: **{assigned}**\n"
            "• Permissões antigas dos canais foram substituídas\n"
            "• Visitante automático foi ativado\n"
            "• Visitante vê somente entrada/registro\n"
            "• Texto, marcações e calls foram configurados por hierarquia\n\n"
            "Teste com uma conta comum, sem Administrador. A conta dona do servidor sempre vê tudo.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ O Discord bloqueou uma alteração. Coloque o cargo do bot acima de todos os "
            "cargos da facção e habilite **Gerenciar Cargos** e **Gerenciar Canais**.",
            ephemeral=True,
        )
    except discord.HTTPException as exc:
        await interaction.followup.send(
            f"❌ Falha temporária do Discord (código {getattr(exc, 'code', '?')}). Tente o `/reset` novamente.",
            ephemeral=True,
        )

@bot.tree.command(name="gerenciar", description="Abre o painel de gerenciamento do Bot Facção")
@app_commands.default_permissions(administrator=True)
async def gerenciar(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await interaction.response.send_message(
        view=DashboardLayout(1),
        ephemeral=True
    )

@bot.tree.command(name="painel", description="Envia o painel público de um sistema")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(sistema=[
    app_commands.Choice(name=meta["label"], value=key)
    for key, meta in SYSTEMS.items()
])
async def painel(interaction: discord.Interaction, sistema: app_commands.Choice[str], canal: discord.TextChannel):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await send_public_panel(interaction.guild, canal, sistema.value)
    await interaction.response.send_message(
        f"✅ Painel de **{SYSTEMS.get(sistema.value, {"label": str(sistema.value).title()})['label']}** enviado em {canal.mention}.",
        ephemeral=True
    )

@bot.tree.command(name="status-bot", description="Altera o status do bot")
@app_commands.default_permissions(administrator=True)
async def status_bot(interaction: discord.Interaction, texto: str):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await bot.change_presence(activity=discord.Game(name=texto))
    await interaction.response.send_message("✅ Status atualizado.", ephemeral=True)

@bot.tree.command(name="limpar", description="Limpa mensagens")
async def limpar(interaction: discord.Interaction, quantidade: app_commands.Range[int,1,100] = 20):
    if not interaction.user.guild_permissions.manage_messages:
        return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    msgs = await interaction.channel.purge(limit=quantidade)
    await interaction.followup.send(f"✅ {len(msgs)} mensagens removidas.", ephemeral=True)

@bot.tree.command(name="anuncio-privado", description="Envia anúncio por DM para membros de um cargo")
async def anuncio_privado(interaction: discord.Interaction, cargo: discord.Role, titulo: str, mensagem: str):
    if not is_admin(interaction.user):
        return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    sent = 0
    failed = 0
    e = embed(titulo, mensagem)
    for member in cargo.members:
        if member.bot:
            continue
        try:
            await member.send(embed=e)
            sent += 1
            await asyncio.sleep(0.35)
        except Exception:
            failed += 1
    await interaction.followup.send(f"✅ Enviados: {sent}\n❌ Falhas: {failed}", ephemeral=True)

# Registra comandos que foram criados com @app_commands.command
bot.tree.add_command(advertir)
bot.tree.add_command(painel_advertencias)
bot.tree.add_command(metas_cmd)
bot.tree.add_command(configurar_metas)
bot.tree.add_command(analisar_promocao)
bot.tree.add_command(comece_aqui)
bot.tree.add_command(painel_equipe)
bot.tree.add_command(promover)
bot.tree.add_command(rebaixar)
bot.tree.add_command(ranking)
bot.tree.add_command(relatorio_farm)
bot.tree.add_command(backup_cmd)



def _component_safety_audit():
    """Falha cedo se um emoji textual conhecido por ser inválido voltar ao código."""
    invalid_component_emojis = {"⏻", "←", "→"}
    # Setas são permitidas em labels, mas não devem voltar ao parâmetro emoji.
    source_markers = [
        ("visitor_toggle", "🔄"),
        ("toggle", "🔄"),
    ]
    for name, emoji in source_markers:
        if emoji in invalid_component_emojis:
            raise RuntimeError(f"Emoji inválido em componente: {name} -> {emoji}")

_component_safety_audit()

# ============================================================
# STARTUP / READY
# ============================================================

_STARTUP_VIEWS_REGISTERED = False

async def _setup_hook():
    """Executa uma única vez por processo, antes da conexão ficar pronta.

    Evita registrar views e sincronizar comandos novamente em cada reconexão
    do Gateway, que era uma das fontes de instabilidade durante os testes.
    """
    global _STARTUP_VIEWS_REGISTERED

    init_db()

    if not _STARTUP_VIEWS_REGISTERED:
        bot.add_view(RegistroPanel())
        bot.add_view(VendasPanel())
        bot.add_view(BancoPanel())
        bot.add_view(LavagemPanel())
        bot.add_view(EncomendasPanel())
        bot.add_view(AusenciaPanel())
        bot.add_view(FarmPanel())
        bot.add_view(BauPanel())
        bot.add_view(AcoesPanel())
        bot.add_view(MetasPanel())
        bot.add_view(ComeceAquiView())
        bot.add_view(HierarquiaPanel())
        bot.add_view(RankingPublicPanel())
        _STARTUP_VIEWS_REGISTERED = True

    if AUTO_SYNC_COMMANDS:
        try:
            if GUILD_ID.isdigit():
                guild_obj = discord.Object(id=int(GUILD_ID))
                bot.tree.copy_global_to(guild=guild_obj)
                synced = await bot.tree.sync(guild=guild_obj)
                print(f"✅ {len(synced)} comando(s) sincronizado(s) no servidor configurado.")
            else:
                synced = await bot.tree.sync()
                print(f"✅ {len(synced)} comando(s) global(is) sincronizado(s).")
        except discord.HTTPException as exc:
            # Não despeja páginas HTML inteiras do Cloudflare no log.
            print(
                "⚠️ Falha temporária ao sincronizar comandos com o Discord: "
                f"HTTP {getattr(exc, 'status', '?')} / código {getattr(exc, 'code', '?')}. "
                "O bot continuará online; use /sincronizar quando a API normalizar."
            )
        except Exception as exc:
            print(f"⚠️ Falha ao sincronizar comandos: {type(exc).__name__}: {exc}")

# setup_hook é chamado uma vez pelo discord.py durante o login.
bot.setup_hook = _setup_hook


@bot.tree.command(name="sincronizar", description="Sincroniza os comandos do bot manualmente")
@app_commands.default_permissions(administrator=True)
async def sincronizar(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await deny(interaction)

    await interaction.response.defer(ephemeral=True)
    try:
        if GUILD_ID.isdigit():
            guild_obj = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
        else:
            synced = await bot.tree.sync()
        await interaction.followup.send(
            f"✅ **{len(synced)}** comando(s) sincronizado(s).",
            ephemeral=True,
        )
    except discord.HTTPException as exc:
        await interaction.followup.send(
            f"⚠️ O Discord recusou temporariamente a sincronização (HTTP {getattr(exc, 'status', '?')}). "
            "Aguarde alguns minutos e tente novamente.",
            ephemeral=True,
        )


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Resposta curta para o usuário e log legível no Railway.
    original = getattr(error, "original", error)
    print(f"❌ Erro em comando/interação: {type(original).__name__}: {original}")
    try:
        await deny(interaction, f"❌ Ocorreu um erro: `{type(original).__name__}`. Veja o log do Railway.")
    except Exception:
        pass


@bot.event
async def on_ready():
    try:
        for guild in bot.guilds:
            try:
                apply_server_autoconfig(guild)
            except Exception as cfg_exc:
                print(
                    f"⚠️ Falha na auto-configuração de {guild.name}: "
                    f"{type(cfg_exc).__name__}: {cfg_exc}"
                )

        if not backup_loop.is_running():
            backup_loop.start()
        await bot.change_presence(activity=discord.Game(name=f"Gerenciando {FAC_NAME}"))
        print(f"✅ Online como {bot.user} | ID {bot.user.id if bot.user else 'N/A'}")
    except Exception as exc:
        print(f"⚠️ Erro no on_ready: {type(exc).__name__}: {exc}")


bot.run(TOKEN)
