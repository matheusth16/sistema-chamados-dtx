"""Serviço de lembrete de MFA pendente.

Quem "não tem MFA" nunca conseguiu passar da tela de configuração
(verificar_mfa_obrigatorio em app/__init__.py bloqueia toda requisição
autenticada sem MFA) — são contas criadas que nunca fizeram login nem uma
vez. Sem acesso à sineta in-app, o único canal viável é e-mail.

Grace period de 24h após a criação (evita lembrete imediato pra conta recém
criada por um admin) e reenvio a cada 3 dias, indefinidamente, até a pessoa
configurar o MFA — decisão explícita do usuário, sem teto de tentativas.

Claim atômico via UPDATE...RETURNING, liberado em caso de falha de envio
(revertido pro valor anterior, não pra NULL, pra manter o histórico de
"já foi lembrado antes"). Sem notificação in-app (a população alvo nunca
chega na sineta) e sem Historico (é escopo de chamado, não existe
equivalente por usuário — o próprio timestamp já é o rastro).

Quem nunca chegou a trocar a senha inicial (must_change_password=True)
nunca logou nem uma vez — a senha inicial original não está salva em lugar
nenhum recuperável (só o hash), então não tem o que reenviar. Pra esses
casos o lembrete gera uma senha nova (mesmo padrão do reset manual do
admin em app/routes/usuarios.py) e manda junto no e-mail combinado.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, update

from app import db as db_module
from app.db.models.usuario import UsuarioRow
from app.models_usuario import Usuario
from app.services.notifications import (
    notificar_lembrete_mfa_pendente,
    notificar_lembrete_mfa_pendente_com_senha,
)
from app.services.senha_service import gerar_senha_aleatoria

logger = logging.getLogger(__name__)

_GRACE_HORAS = 24
_INTERVALO_DIAS = 3


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _elegivel(usuario: Usuario, agora: datetime) -> bool:
    if usuario.criado_em is None:
        return False

    idade_horas = (agora - _aware(usuario.criado_em)).total_seconds() / 3600
    if idade_horas < _GRACE_HORAS:
        return False

    if usuario.mfa_lembrete_enviado_em is None:
        return True

    return (agora - _aware(usuario.mfa_lembrete_enviado_em)) >= timedelta(days=_INTERVALO_DIAS)


def _claim(usuario_id: str, agora: datetime, cutoff: datetime) -> bool:
    stmt = (
        update(UsuarioRow)
        .where(
            UsuarioRow.id == usuario_id,
            UsuarioRow.mfa_enabled.is_(False),
            or_(
                UsuarioRow.mfa_lembrete_enviado_em.is_(None),
                UsuarioRow.mfa_lembrete_enviado_em <= cutoff,
            ),
        )
        .values(mfa_lembrete_enviado_em=agora)
        .returning(UsuarioRow.id)
    )
    with db_module.SessionLocal() as session, session.begin():
        return session.execute(stmt).scalar_one_or_none() is not None


def _liberar(usuario_id: str, valor_anterior: datetime | None) -> None:
    with db_module.SessionLocal() as session, session.begin():
        row = session.get(UsuarioRow, usuario_id)
        if row is not None:
            row.mfa_lembrete_enviado_em = valor_anterior


def processar_lembretes_mfa(agora: datetime | None = None) -> dict:
    """Verifica usuários ativos sem MFA e envia lembrete por e-mail quando elegível.

    Retorna um dict de contadores: processados, enviados, erros.
    """
    if agora is None:
        agora = datetime.now(UTC)
    cutoff = agora - timedelta(days=_INTERVALO_DIAS)

    stats = {"processados": 0, "enviados": 0, "erros": 0}

    try:
        usuarios = Usuario.get_sem_mfa()
    except Exception as exc:
        logger.exception("Lembrete MFA: erro ao consultar usuários sem MFA: %s", exc)
        stats["erros"] += 1
        return stats

    for usuario in usuarios:
        stats["processados"] += 1
        try:
            _processar_usuario(usuario, agora, cutoff, stats)
        except Exception as exc:
            logger.exception("Lembrete MFA: erro ao processar usuário %s: %s", usuario.id, exc)
            stats["erros"] += 1

    return stats


def _processar_usuario(usuario: Usuario, agora: datetime, cutoff: datetime, stats: dict) -> None:
    if not _elegivel(usuario, agora):
        return

    valor_anterior = usuario.mfa_lembrete_enviado_em
    if not _claim(usuario.id, agora, cutoff):
        return

    if usuario.must_change_password:
        senha_nova = gerar_senha_aleatoria()
        usuario.update(senha=senha_nova, must_change_password=True)
        enviado = notificar_lembrete_mfa_pendente_com_senha(usuario.email, usuario.nome, senha_nova)
        descricao = "Lembrete de MFA pendente (com senha nova)"
    else:
        enviado = notificar_lembrete_mfa_pendente(usuario.email, usuario.nome)
        descricao = "Lembrete de MFA pendente"

    if enviado:
        stats["enviados"] += 1
        logger.info("%s enviado para usuário %s", descricao, usuario.id)
    else:
        _liberar(usuario.id, valor_anterior)
        logger.warning("%s falhou para usuário %s — será tentado novamente", descricao, usuario.id)
