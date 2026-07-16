"""Fonte única de verdade para e-mails de escalonamento gerencial (nivel_gestao).

Usado por sla_escalacao_service.py (Escada A/B, escalonamento gradual) e
notifications.py (broadcast AOG imediato) — nunca duplicar essa lógica em mais
de um lugar.

O gestor de cada nível é sempre um usuário real do sistema (nivel_gestao no
cadastro do usuário, o mesmo campo usado pelo Painel Gerencial), nunca e-mail
configurado à parte em variável de ambiente: cadastrar ou desligar alguém no
Painel de Usuários já reflete aqui automaticamente, sem precisar mexer em
código/config.
"""

import logging

from app.cache import get_static_cached

logger = logging.getLogger(__name__)

NIVEL_PARA_CHAVE_GESTOR: dict[int, str] = {
    1: "gestor_setor",
    2: "gerente_producao",
    3: "assistente_gm",
    4: "gm",
}

# Níveis de gestão company-wide (sem área): 2, 3 e 4 na escada de escalonamento.
NIVEIS_GESTAO_SUPERIORES = ("gerente_producao", "assistente_gm", "gm")


def construir_mapa_gestor_setor() -> dict[str, str]:
    """Monta {nome_setor: email} uma vez por execução do job (evita N leituras).

    O gestor de cada setor é sempre um usuário real do sistema: marcado com
    nivel_gestao == 'gestor_setor' e com as áreas que gerencia em .areas
    (mesmos campos já usados pelo cadastro de usuário / Gestor Dashboard).
    Usuários inativos ou sem nivel_gestao='gestor_setor' são ignorados. Se
    duas pessoas cobrirem a mesma área (config inconsistente), mantém a
    primeira encontrada e loga warning — não é motivo para travar o job.
    """
    from app.models_usuario import Usuario

    try:
        mapa: dict[str, str] = {}
        usuarios = get_static_cached("sla_gestores_usuarios", Usuario.get_all, ttl_seconds=300)
        for usuario in usuarios:
            if getattr(usuario, "nivel_gestao", None) != "gestor_setor":
                continue
            if not getattr(usuario, "ativo", True) or not getattr(usuario, "email", None):
                continue
            for area in usuario.areas or []:
                if area in mapa:
                    logger.warning(
                        "Escada: mais de um gestor_setor para a área '%s' — mantendo %s, "
                        "ignorando %s.",
                        area,
                        mapa[area],
                        usuario.email,
                    )
                    continue
                mapa[area] = usuario.email
        return mapa
    except Exception as exc:
        logger.warning("Falha ao montar mapa gestor_setor: %s. Sem e-mails de nível 1.", exc)
        return {}


def construir_mapa_niveis_superiores() -> dict[str, str]:
    """Monta {nivel_gestao: email} para os níveis 2–4 (gerente_producao, assistente_gm,
    gm) — abrangência de toda a empresa, sem filtro de área.

    Usuários inativos ou sem e-mail são ignorados. Se houver mais de uma pessoa
    no mesmo nível, mantém a primeira encontrada (ordem alfabética por e-mail)
    e loga warning — não é motivo para travar o job.
    """
    from app.models_usuario import Usuario

    try:
        mapa: dict[str, str] = {}
        candidatos: dict[str, list[str]] = {nivel: [] for nivel in NIVEIS_GESTAO_SUPERIORES}
        usuarios = get_static_cached("sla_gestores_usuarios", Usuario.get_all, ttl_seconds=300)
        for usuario in usuarios:
            nivel = getattr(usuario, "nivel_gestao", None)
            if nivel not in NIVEIS_GESTAO_SUPERIORES:
                continue
            if not getattr(usuario, "ativo", True) or not getattr(usuario, "email", None):
                continue
            candidatos[nivel].append(usuario.email)
        for nivel, emails in candidatos.items():
            if not emails:
                continue
            emails_ordenados = sorted(emails)
            mapa[nivel] = emails_ordenados[0]
            if len(emails_ordenados) > 1:
                logger.warning(
                    "Escada: mais de uma pessoa com nivel_gestao='%s' — mantendo %s, ignorando %s.",
                    nivel,
                    emails_ordenados[0],
                    emails_ordenados[1:],
                )
        return mapa
    except Exception as exc:
        logger.warning("Falha ao montar mapa de níveis superiores de gestão: %s. Sem e-mails.", exc)
        return {}


def resolver_email_gestor(
    chave_gestor: str | None,
    categoria: str,
    mapa_gestor_setor: dict[str, str],
    mapa_niveis_superiores: dict[str, str],
) -> str | None:
    """Resolve o e-mail de destino para o nível de escalonamento — sempre a partir
    do cadastro real de usuários (nivel_gestao), nunca de configuração estática."""
    if chave_gestor == "gestor_setor":
        return mapa_gestor_setor.get(categoria)
    if chave_gestor:
        return mapa_niveis_superiores.get(chave_gestor)
    return None


def resolver_email_gestor_com_cascata(
    chave_gestor: str,
    categoria: str,
    mapa_gestor_setor: dict[str, str],
    mapa_niveis_superiores: dict[str, str],
) -> str | None:
    """Como resolver_email_gestor, mas cai pro próximo nível de gestão acima
    quando o nível pedido não tem ninguém cadastrado — usado no broadcast
    imediato de AOG (emergência: nunca fica sem notificar por lacuna de
    cadastro; `gm` é o topo da cadeia, não tem pra onde cascatear).
    """
    ordem = tuple(NIVEL_PARA_CHAVE_GESTOR.values())
    if chave_gestor not in ordem:
        return None
    for nivel_candidato in ordem[ordem.index(chave_gestor) :]:
        email = resolver_email_gestor(
            nivel_candidato, categoria, mapa_gestor_setor, mapa_niveis_superiores
        )
        if email:
            return email
    return None
