"""Barrel de notificações: reexporta os módulos notifications_* especializados.

Todo notificar_* foi extraído para módulos por domínio (notifications_usuarios,
notifications_escalonamento, notifications_chamados) e a infraestrutura de envio
(enviar_email, links, resolver_importance) vive em notifications_core.py. Este
arquivo só reimporta tudo com __all__ explícito, preservando os ~150
`from app.services.notifications import X` espalhados pelo projeto sem precisar
tocar em nenhum — inclusive os patches de teste existentes
(`app.services.notifications.enviar_email` etc. continuam funcionando enquanto
apontarem pro nome certo; ver notas de patch por módulo em cada arquivo movido).
"""

import logging

from app.services.notifications_chamados import (
    notificar_aprovador_novo_chamado,
    notificar_owner_todos_participantes_concluiram,
    notificar_participante_incluido,
    notificar_responsavel_chamado_confirmado,
    notificar_responsavel_prazo_24h,
    notificar_responsavel_setor_adicional,
    notificar_setores_adicionais_chamado,
    notificar_solicitante_confirmacao_pendente,
    notificar_solicitante_lembrete_confirmacao,
    notificar_solicitante_status,
    notificar_supervisor_chamado_reaberto,
    notificar_supervisor_escalonamento_colega,
    notificar_supervisor_transferencia_area,
)
from app.services.notifications_core import (
    _base_url,
    _config,
    _email_envio_permitido,
    _enviar_via_graph,
    _link_chamado,
    _link_dashboard,
    _link_historico,
    _prefixar_assunto_high,
    _tc,
    _ts,
    _tsl,
    _tst,
    enviar_email,
    resolver_importance,
)
from app.services.notifications_escalonamento import (
    notificar_abertura_aog_todos_gestores,
    notificar_aviso_resolucao_supervisor,
    notificar_escalada_resolucao_gerencial,
    notificar_escalada_resposta_gerencial,
)
from app.services.notifications_usuarios import (
    notificar_admins_novo_usuario_sso,
    notificar_mudanca_perfil,
    notificar_novo_usuario_cadastrado,
    notificar_novo_usuario_sso,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_base_url",
    "_config",
    "_email_envio_permitido",
    "_enviar_via_graph",
    "_link_chamado",
    "_link_dashboard",
    "_link_historico",
    "_prefixar_assunto_high",
    "_tc",
    "_ts",
    "_tsl",
    "_tst",
    "enviar_email",
    "resolver_importance",
    "notificar_admins_novo_usuario_sso",
    "notificar_mudanca_perfil",
    "notificar_novo_usuario_cadastrado",
    "notificar_novo_usuario_sso",
    "notificar_abertura_aog_todos_gestores",
    "notificar_aviso_resolucao_supervisor",
    "notificar_escalada_resolucao_gerencial",
    "notificar_escalada_resposta_gerencial",
    "notificar_aprovador_novo_chamado",
    "notificar_owner_todos_participantes_concluiram",
    "notificar_participante_incluido",
    "notificar_responsavel_chamado_confirmado",
    "notificar_responsavel_prazo_24h",
    "notificar_responsavel_setor_adicional",
    "notificar_setores_adicionais_chamado",
    "notificar_solicitante_confirmacao_pendente",
    "notificar_solicitante_lembrete_confirmacao",
    "notificar_solicitante_status",
    "notificar_supervisor_chamado_reaberto",
    "notificar_supervisor_escalonamento_colega",
    "notificar_supervisor_transferencia_area",
]
