"""Testes de previsao_atendimento_service: solicitar_previsao_atendimento,
decidir_previsao_atendimento, resolução do gestor decisor, token de aprovação
por e-mail.

Substitui a antiga escalonamento_service.definir_previsao_atendimento (agora
em 2 passos: solicitar cria pedido 'pendente'; só decidir_previsao_atendimento
aprovando escreve em chamados.previsao_atendimento — ver módulo pra detalhe
da regra "pendente não silencia escalonamento").
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.models import Chamado
from config import Config

pytestmark = pytest.mark.usefixtures("db_session")

_ID_INEXISTENTE = 999999999


def _usuario(uid, nome, perfil="supervisor", areas=None, nivel_gestao=None, ativo=True):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    u.perfil = perfil
    u.areas = areas or []
    u.nivel_gestao = nivel_gestao
    u.ativo = ativo
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    return u


JULIA = _usuario("id_julia", "Julia Silva", areas=["Engenharia"])
ADMIN = _usuario("id_admin", "Admin User", "admin")
NAO_OWNER = _usuario("id_nao_owner", "Outro Supervisor", areas=["Outra Area"])
SOLICITANTE = _usuario("id_sol", "Sol User", "solicitante", areas=[])
GESTOR_ENGENHARIA = _usuario(
    "id_gestor_eng", "Gestor Engenharia", areas=["Engenharia"], nivel_gestao="gestor_setor"
)
GESTOR_OUTRA_AREA = _usuario(
    "id_gestor_outra", "Gestor Outra Área", areas=["Outra Area"], nivel_gestao="gestor_setor"
)


def _criar_chamado_real(
    area="Engenharia",
    responsavel_id="id_julia",
    responsavel="Julia Silva",
    status="Em Atendimento",
    categoria="Manutencao",
) -> int:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Corretiva",
        descricao="Descrição teste",
        responsavel=responsavel,
        responsavel_id=responsavel_id,
        area=area,
        status=status,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


def _futuro(**kwargs) -> datetime:
    return datetime.now() + timedelta(**kwargs)


# ── solicitar_previsao_atendimento ──────────────────────────────────────────


class TestSolicitarPrevisaoAtendimento:
    def test_cria_pedido_pendente_sem_tocar_no_chamado(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real()
        previsao = _futuro(days=5)  # depois do TAT padrão (3 dias)

        resultado = solicitar_previsao_atendimento(
            chamado_id, previsao, "Preciso de mais tempo, terceiro externo", JULIA
        )

        assert resultado["sucesso"] is True
        assert resultado["dados"]["solicitacao_id"] is not None
        # Pendente não aplica nada no chamado — só a aprovação faz isso.
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None
        assert atualizado.motivo_previsao_atendimento is None

    def test_resolve_gestor_setor_da_area_do_chamado(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        previsao = _futuro(days=5)  # depois do TAT padrão (3 dias)

        with patch("app.models_usuario.Usuario.get_all", return_value=[GESTOR_ENGENHARIA]):
            resultado = solicitar_previsao_atendimento(chamado_id, previsao, "motivo", JULIA)

        assert resultado["dados"]["gestor_id"] == "id_gestor_eng"

    def test_aog_sempre_bloqueada(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real(categoria="AOG")
        previsao = _futuro(hours=2)

        resultado = solicitar_previsao_atendimento(
            chamado_id, previsao, "Aeronave em manutenção externa", JULIA
        )

        assert resultado["sucesso"] is False

    def test_motivo_obrigatorio(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        with pytest.raises(ValueError, match="motivo"):
            solicitar_previsao_atendimento(_ID_INEXISTENTE, _futuro(days=1), "", JULIA)

    def test_data_obrigatoria(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        with pytest.raises(ValueError, match="previsao"):
            solicitar_previsao_atendimento(_ID_INEXISTENTE, None, "motivo", JULIA)

    def test_no_passado_retorna_erro(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real()
        agora_fuso_negocio = datetime.now(ZoneInfo(Config.SLA_TIMEZONE)).replace(tzinfo=None)
        previsao_passada = agora_fuso_negocio - timedelta(hours=1)

        resultado = solicitar_previsao_atendimento(chamado_id, previsao_passada, "motivo", JULIA)

        assert resultado["sucesso"] is False

    def test_nao_owner_retorna_erro(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real()
        resultado = solicitar_previsao_atendimento(chamado_id, _futuro(days=1), "motivo", NAO_OWNER)

        assert resultado["sucesso"] is False

    def test_owner_solicitante_negado(self):
        """Owner que não é supervisor+ (perfil solicitante) não pode pedir,
        mesmo sendo o responsavel_id do chamado."""
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real(responsavel_id=SOLICITANTE.id)
        resultado = solicitar_previsao_atendimento(
            chamado_id, _futuro(days=1), "motivo", SOLICITANTE
        )

        assert resultado["sucesso"] is False

    def test_admin_nao_owner_permitido(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real()
        resultado = solicitar_previsao_atendimento(chamado_id, _futuro(days=5), "motivo", ADMIN)

        assert resultado["sucesso"] is True

    def test_sem_teto_maximo(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real()
        resultado = solicitar_previsao_atendimento(chamado_id, _futuro(days=90), "motivo", JULIA)

        assert resultado["sucesso"] is True

    def test_chamado_nao_encontrado(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        resultado = solicitar_previsao_atendimento(
            _ID_INEXISTENTE, _futuro(days=1), "motivo", JULIA
        )

        assert resultado["sucesso"] is False

    def test_registra_historico(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real()
        hist_instancia = MagicMock()

        with patch("app.services.previsao_atendimento_service.Historico") as mock_hist_cls:
            mock_hist_cls.return_value = hist_instancia
            solicitar_previsao_atendimento(chamado_id, _futuro(days=5), "motivo", JULIA)

        _, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "solicitacao_previsao_atendimento"
        assert kwargs.get("campo_alterado") == "previsao_atendimento"
        hist_instancia.save.assert_called_once()

    def test_previsao_antes_do_prazo_tat_e_rejeitada(self):
        """Bug real (auditoria 2026-08-13): nada validava a previsão contra
        o prazo TAT da categoria — dava pra pedir (e aprovar) uma previsão
        de "daqui a 2 minutos" num chamado cujo TAT ainda estava a dias de
        distância, o que não faz sentido (_prazo_efetivo nunca encurta o
        prazo, então essa previsão nunca teria efeito nenhum se aprovada)."""
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        # categoria "Manutencao" (não-Projetos) usa SLA_DIAS_RESOLUCAO_PADRAO (3 dias)
        chamado_id = _criar_chamado_real(categoria="Manutencao")
        previsao_dentro_do_tat = _futuro(minutes=2)

        resultado = solicitar_previsao_atendimento(
            chamado_id, previsao_dentro_do_tat, "motivo", JULIA
        )

        assert resultado["sucesso"] is False

    def test_previsao_depois_do_prazo_tat_e_aceita(self):
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real(categoria="Manutencao")
        previsao_depois_do_tat = _futuro(days=5)  # TAT padrão = 3 dias

        resultado = solicitar_previsao_atendimento(
            chamado_id, previsao_depois_do_tat, "motivo", JULIA
        )

        assert resultado["sucesso"] is True

    def test_segundo_pedido_enquanto_pendente_e_rejeitado(self):
        """Só 1 pedido pendente por chamado — evita spam de solicitações
        empilhadas esperando decisão."""
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        chamado_id = _criar_chamado_real()
        primeiro = solicitar_previsao_atendimento(chamado_id, _futuro(days=5), "motivo 1", JULIA)
        assert primeiro["sucesso"] is True

        segundo = solicitar_previsao_atendimento(chamado_id, _futuro(days=6), "motivo 2", JULIA)

        assert segundo["sucesso"] is False


# ── decidir_previsao_atendimento ────────────────────────────────────────────


class TestDecidirPrevisaoAtendimento:
    def _pedir(self, chamado_id, previsao=None, motivo="motivo", usuario=JULIA) -> int:
        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        resultado = solicitar_previsao_atendimento(
            chamado_id, previsao or _futuro(days=5), motivo, usuario
        )
        assert resultado["sucesso"] is True
        return resultado["dados"]["solicitacao_id"]

    def test_aprovar_aplica_previsao_no_chamado(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        previsao = _futuro(days=5)  # depois do TAT padrão (3 dias)
        solicitacao_id = self._pedir(chamado_id, previsao, "motivo do pedido")

        resultado = decidir_previsao_atendimento(solicitacao_id, "aprovar", GESTOR_ENGENHARIA)

        assert resultado["sucesso"] is True
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento.replace(tzinfo=None) == previsao
        assert atualizado.motivo_previsao_atendimento == "motivo do pedido"

    def test_decisao_trava_tambem_linha_do_chamado(self, db_session):
        from sqlalchemy import event

        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)
        statements = []
        connection = db_session.get_bind()

        def _capturar(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(connection, "before_cursor_execute", _capturar)
        try:
            resultado = decidir_previsao_atendimento(
                solicitacao_id,
                "aprovar",
                GESTOR_ENGENHARIA,
            )
        finally:
            event.remove(connection, "before_cursor_execute", _capturar)

        assert resultado["sucesso"] is True
        selects_chamado = [
            sql
            for sql in statements
            if "FROM chamados" in sql and "chamado_previsao_solicitacoes" not in sql
        ]
        assert any("FOR UPDATE" in sql.upper() for sql in selects_chamado)

    def test_rejeitar_nao_aplica_previsao_no_chamado(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        resultado = decidir_previsao_atendimento(
            solicitacao_id, "rejeitar", GESTOR_ENGENHARIA, motivo_rejeicao="sem tempo hábil"
        )

        assert resultado["sucesso"] is True
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None

    def test_gestor_area_errada_negado(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        resultado = decidir_previsao_atendimento(solicitacao_id, "aprovar", GESTOR_OUTRA_AREA)

        assert resultado["sucesso"] is False
        assert resultado["codigo"] == 403
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None

    def test_supervisor_comum_sem_nivel_gestao_negado(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        resultado = decidir_previsao_atendimento(solicitacao_id, "aprovar", JULIA)

        assert resultado["sucesso"] is False
        assert resultado["codigo"] == 403

    def test_admin_sempre_pode_decidir(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        resultado = decidir_previsao_atendimento(solicitacao_id, "aprovar", ADMIN)

        assert resultado["sucesso"] is True

    def test_aprovar_pedido_de_chamado_cancelado_enquanto_pendente_e_recusado(self):
        """Bug real (auditoria 2026-08-13, TOCTOU): o pedido fica pendente por
        tempo arbitrário até o gestor decidir; se o chamado for cancelado
        nesse meio-tempo, aprovar não deveria mais escrever previsao_atendimento
        nele — a aprovação vira uma rejeição automática, sem tocar no chamado."""
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        chamado = Chamado.get_by_id(chamado_id)
        assert chamado.atualizar_campos(status="Cancelado") is True

        resultado = decidir_previsao_atendimento(solicitacao_id, "aprovar", GESTOR_ENGENHARIA)

        assert resultado["sucesso"] is False
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None

    def test_aprovar_pedido_de_chamado_concluido_enquanto_pendente_e_recusado(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        chamado = Chamado.get_by_id(chamado_id)
        assert chamado.atualizar_campos(status="Concluído") is True

        resultado = decidir_previsao_atendimento(solicitacao_id, "aprovar", GESTOR_ENGENHARIA)

        assert resultado["sucesso"] is False
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is None

    def test_rejeitar_pedido_de_chamado_cancelado_continua_permitido(self):
        """Rejeitar nunca escreve no chamado — permitir mesmo com o chamado
        já encerrado, pra fechar formalmente o pedido pendente."""
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        chamado = Chamado.get_by_id(chamado_id)
        assert chamado.atualizar_campos(status="Cancelado") is True

        resultado = decidir_previsao_atendimento(
            solicitacao_id, "rejeitar", GESTOR_ENGENHARIA, motivo_rejeicao="sem tempo"
        )

        assert resultado["sucesso"] is True

    def test_decisao_dupla_e_no_op(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)

        primeira = decidir_previsao_atendimento(solicitacao_id, "aprovar", GESTOR_ENGENHARIA)
        assert primeira["sucesso"] is True

        segunda = decidir_previsao_atendimento(solicitacao_id, "rejeitar", GESTOR_ENGENHARIA)

        assert segunda["sucesso"] is False
        assert segunda["codigo"] == 409
        # A primeira decisão (aprovação) não é desfeita pela segunda tentativa.
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.previsao_atendimento is not None

    def test_solicitacao_inexistente(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        resultado = decidir_previsao_atendimento(_ID_INEXISTENTE, "aprovar", ADMIN)

        assert resultado["sucesso"] is False
        assert resultado["codigo"] == 404

    def test_registra_historico_na_aprovacao(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)
        hist_instancia = MagicMock()

        with patch("app.services.previsao_atendimento_service.Historico") as mock_hist_cls:
            mock_hist_cls.return_value = hist_instancia
            decidir_previsao_atendimento(solicitacao_id, "aprovar", GESTOR_ENGENHARIA)

        _, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "aprovacao_previsao_atendimento"
        hist_instancia.save.assert_called_once()

    def test_registra_historico_na_rejeicao(self):
        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        chamado_id = _criar_chamado_real(area="Engenharia")
        solicitacao_id = self._pedir(chamado_id)
        hist_instancia = MagicMock()

        with patch("app.services.previsao_atendimento_service.Historico") as mock_hist_cls:
            mock_hist_cls.return_value = hist_instancia
            decidir_previsao_atendimento(
                solicitacao_id, "rejeitar", GESTOR_ENGENHARIA, motivo_rejeicao="sem tempo"
            )

        _, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "rejeicao_previsao_atendimento"
        assert kwargs.get("detalhe") == "sem tempo"
        hist_instancia.save.assert_called_once()


# ── resolução do gestor decisor ─────────────────────────────────────────────


class TestResolverGestorDecisor:
    def test_acha_gestor_setor_da_area(self):
        from app.services.previsao_atendimento_service import resolver_gestor_decisor

        with patch("app.models_usuario.Usuario.get_all", return_value=[GESTOR_ENGENHARIA]):
            gestor = resolver_gestor_decisor("Engenharia")

        assert gestor.id == "id_gestor_eng"

    def test_fallback_pro_gerente_producao_sem_gestor_setor(self):
        from app.services.previsao_atendimento_service import resolver_gestor_decisor

        gerente = _usuario(
            "id_gerente", "Gerente Producao", nivel_gestao="gerente_producao", areas=[]
        )
        gerente.email = "gerente@dtx.aero"
        with patch("app.models_usuario.Usuario.get_all", return_value=[gerente]):
            gestor = resolver_gestor_decisor("Area Sem Gestor")

        assert gestor.id == "id_gerente"

    def test_sem_ninguem_cadastrado_retorna_none(self):
        from app.services.previsao_atendimento_service import resolver_gestor_decisor

        with patch("app.models_usuario.Usuario.get_all", return_value=[]):
            gestor = resolver_gestor_decisor("Area Orfa")

        assert gestor is None


class TestUsuarioPodeDecidirPrevisaoAtendimento:
    def test_admin_sempre_pode(self):
        from app.services.previsao_atendimento_service import (
            usuario_pode_decidir_previsao_atendimento,
        )

        assert usuario_pode_decidir_previsao_atendimento(ADMIN, "Qualquer Area") is True

    def test_gestor_setor_area_correta(self):
        from app.services.previsao_atendimento_service import (
            usuario_pode_decidir_previsao_atendimento,
        )

        assert usuario_pode_decidir_previsao_atendimento(GESTOR_ENGENHARIA, "Engenharia") is True

    def test_gestor_setor_area_errada(self):
        from app.services.previsao_atendimento_service import (
            usuario_pode_decidir_previsao_atendimento,
        )

        assert usuario_pode_decidir_previsao_atendimento(GESTOR_ENGENHARIA, "Outra Area") is False

    def test_supervisor_comum_nao_pode(self):
        from app.services.previsao_atendimento_service import (
            usuario_pode_decidir_previsao_atendimento,
        )

        assert usuario_pode_decidir_previsao_atendimento(JULIA, "Engenharia") is False

    def test_gestor_setor_desativado_nao_pode(self):
        """Bug real (auditoria 2026-08-13): a checagem nunca olhava pra
        `ativo`. Um gestor_setor desativado depois que o e-mail com o link de
        aprovação (token de uso único, válido por 30 dias) já foi enviado
        continuaria conseguindo decidir via link indefinidamente, já que
        aquele fluxo não passa por login/sessão."""
        from app.services.previsao_atendimento_service import (
            usuario_pode_decidir_previsao_atendimento,
        )

        gestor_desativado = _usuario(
            "id_gestor_desativado",
            "Gestor Desativado",
            areas=["Engenharia"],
            nivel_gestao="gestor_setor",
            ativo=False,
        )

        assert usuario_pode_decidir_previsao_atendimento(gestor_desativado, "Engenharia") is False

    def test_admin_desativado_nao_pode(self):
        from app.services.previsao_atendimento_service import (
            usuario_pode_decidir_previsao_atendimento,
        )

        admin_desativado = _usuario("id_admin_desativado", "Admin Desativado", "admin", ativo=False)

        assert usuario_pode_decidir_previsao_atendimento(admin_desativado, "Qualquer Area") is False


# ── token de aprovação por e-mail ───────────────────────────────────────────


class TestTokenDecisao:
    def test_roundtrip_valido(self, app):
        from app.services.previsao_atendimento_service import (
            gerar_token_decisao,
            validar_token_decisao,
        )

        with app.app_context():
            token = gerar_token_decisao(42, "aprovar")
            payload = validar_token_decisao(token)

        assert payload == {"solicitacao_id": 42, "acao": "aprovar"}

    def test_token_adulterado_retorna_none(self, app):
        from app.services.previsao_atendimento_service import validar_token_decisao

        with app.app_context():
            payload = validar_token_decisao("token-invalido-adulterado")

        assert payload is None

    def test_token_de_outro_salt_e_rejeitado(self, app):
        """Token assinado com outro propósito (mesma SECRET_KEY, salt diferente)
        não pode ser reaproveitado aqui — a assinatura não bate."""
        from itsdangerous import URLSafeTimedSerializer

        from app.services.previsao_atendimento_service import validar_token_decisao

        with app.app_context():
            outro = URLSafeTimedSerializer(app.secret_key, salt="outro-proposito")
            token_de_outro_salt = outro.dumps({"solicitacao_id": 1, "acao": "aprovar"})
            payload = validar_token_decisao(token_de_outro_salt)

        assert payload is None

    def test_token_com_acao_invalida_no_payload_e_rejeitado(self, app):
        from itsdangerous import URLSafeTimedSerializer

        from app.services.previsao_atendimento_service import (
            _SALT_TOKEN_DECISAO,
            validar_token_decisao,
        )

        with app.app_context():
            serializer = URLSafeTimedSerializer(app.secret_key, salt=_SALT_TOKEN_DECISAO)
            token_malicioso = serializer.dumps({"solicitacao_id": 1, "acao": "apagar_tudo"})
            payload = validar_token_decisao(token_malicioso)

        assert payload is None
