"""TDD: mensagens_novas (polling da Conversa solicitante ↔ responsável) —
app/services/conversa_chamado_service.py."""

import pytest

from app.models_historico import Historico
from app.services.conversa_chamado_service import historico_fora_da_conversa, mensagens_novas
from tests.factories import make_chamado

pytestmark = pytest.mark.usefixtures("db_session")


def _msg(chamado_id, acao, usuario_id="u1", usuario_nome="Fulano", texto="oi"):
    h = Historico(
        chamado_id=chamado_id,
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
        acao=acao,
        valor_novo=texto,
    )
    assert h.save()
    return h


class TestMensagensNovas:
    def test_sem_historico_retorna_lista_vazia(self):
        chamado = make_chamado()
        assert mensagens_novas(chamado.id) == []

    def test_ignora_eventos_que_nao_sao_conversa(self):
        chamado = make_chamado()
        Historico(
            chamado_id=chamado.id,
            usuario_id="u1",
            usuario_nome="Fulano",
            acao="alteracao_status",
            campo_alterado="status",
            valor_anterior="Aberto",
            valor_novo="Em Atendimento",
        ).save()
        assert mensagens_novas(chamado.id) == []

    def test_retorna_mensagens_de_conversa_em_ordem_cronologica(self):
        chamado = make_chamado()
        m1 = _msg(chamado.id, "resposta_solicitante", texto="primeira")
        m2 = _msg(chamado.id, "resposta_responsavel", texto="segunda")

        resultado = mensagens_novas(chamado.id)

        assert [m["texto"] for m in resultado] == ["primeira", "segunda"]
        assert resultado[0]["id"] == m1.id
        assert resultado[1]["id"] == m2.id

    def test_eh_solicitante_reflete_a_acao(self):
        chamado = make_chamado()
        _msg(chamado.id, "resposta_solicitante")
        _msg(chamado.id, "resposta_responsavel")

        resultado = mensagens_novas(chamado.id)

        assert resultado[0]["eh_solicitante"] is True
        assert resultado[1]["eh_solicitante"] is False

    def test_filtra_por_apos_id(self):
        chamado = make_chamado()
        m1 = _msg(chamado.id, "resposta_solicitante", texto="antiga")
        m2 = _msg(chamado.id, "resposta_responsavel", texto="nova")

        resultado = mensagens_novas(chamado.id, apos_id=m1.id)

        assert len(resultado) == 1
        assert resultado[0]["id"] == m2.id
        assert resultado[0]["texto"] == "nova"

    def test_apos_id_maior_que_tudo_retorna_vazio(self):
        chamado = make_chamado()
        m = _msg(chamado.id, "resposta_solicitante")

        assert mensagens_novas(chamado.id, apos_id=m.id) == []

    def test_campos_do_dict_retornado(self):
        chamado = make_chamado()
        _msg(chamado.id, "resposta_solicitante", usuario_nome="Julia", texto="Olá")

        resultado = mensagens_novas(chamado.id)

        assert set(resultado[0].keys()) == {
            "id",
            "usuario_nome",
            "eh_solicitante",
            "texto",
            "data_iso",
            "data_formatada",
        }
        assert resultado[0]["usuario_nome"] == "Julia"
        assert resultado[0]["texto"] == "Olá"
        assert resultado[0]["data_iso"] != ""


class TestHistoricoForaDaConversa:
    """Sinal pro banner "chamado atualizado" na tela de detalhe (item 2 do
    plano de tempo real — ver [[project_tempo_real_polling_planejado]]):
    True quando algo mudou no chamado que NÃO é mensagem da Conversa (essa
    já é tratada ao vivo pelo próprio polling de mensagens_novas)."""

    def test_sem_historico_retorna_false(self):
        chamado = make_chamado()
        assert historico_fora_da_conversa(chamado.id) is False

    def test_alteracao_status_retorna_true(self):
        chamado = make_chamado()
        Historico(
            chamado_id=chamado.id,
            usuario_id="u1",
            usuario_nome="Fulano",
            acao="alteracao_status",
            campo_alterado="status",
            valor_anterior="Aberto",
            valor_novo="Em Atendimento",
        ).save()

        assert historico_fora_da_conversa(chamado.id) is True

    def test_apenas_mensagens_de_conversa_retorna_false(self):
        chamado = make_chamado()
        _msg(chamado.id, "resposta_solicitante", texto="oi")
        _msg(chamado.id, "resposta_responsavel", texto="olá")

        assert historico_fora_da_conversa(chamado.id) is False

    def test_respeita_apos_id(self):
        chamado = make_chamado()
        h1 = Historico(
            chamado_id=chamado.id, usuario_id="u1", usuario_nome="Fulano", acao="criacao"
        )
        h1.save()

        assert historico_fora_da_conversa(chamado.id, apos_id=h1.id) is False

        h2 = Historico(
            chamado_id=chamado.id,
            usuario_id="u1",
            usuario_nome="Fulano",
            acao="alteracao_status",
        )
        h2.save()

        assert historico_fora_da_conversa(chamado.id, apos_id=h1.id) is True
        assert historico_fora_da_conversa(chamado.id, apos_id=h2.id) is False
