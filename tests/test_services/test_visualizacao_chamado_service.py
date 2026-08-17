"""TDD: confirmação de leitura do chamado pelo responsável (versão simples,
timestamp único, ver app/services/visualizacao_chamado_service.py)."""

from unittest.mock import MagicMock

from app.services.visualizacao_chamado_service import marcar_visualizado_pelo_responsavel


def _chamado_mock(responsavel_id="resp_1", visualizado_em=None):
    c = MagicMock()
    c.id = "ch_1"
    c.responsavel_id = responsavel_id
    c.visualizado_pelo_responsavel_em = visualizado_em
    c.atualizar_campos.return_value = True
    return c


class TestMarcarVisualizadoPeloResponsavel:
    def test_responsavel_visualiza_pela_primeira_vez_grava_timestamp(self):
        chamado = _chamado_mock()

        resultado = marcar_visualizado_pelo_responsavel(chamado, "resp_1")

        assert resultado is True
        chamado.atualizar_campos.assert_called_once()
        kwargs = chamado.atualizar_campos.call_args.kwargs
        assert "visualizado_pelo_responsavel_em" in kwargs
        assert kwargs["visualizado_pelo_responsavel_em"] is not None

    def test_ja_visualizado_nao_grava_de_novo(self):
        chamado = _chamado_mock(visualizado_em="2026-08-17T14:32:00")

        resultado = marcar_visualizado_pelo_responsavel(chamado, "resp_1")

        assert resultado is False
        chamado.atualizar_campos.assert_not_called()

    def test_usuario_diferente_do_responsavel_nao_grava(self):
        chamado = _chamado_mock(responsavel_id="resp_1")

        resultado = marcar_visualizado_pelo_responsavel(chamado, "outro_usuario")

        assert resultado is False
        chamado.atualizar_campos.assert_not_called()

    def test_chamado_sem_responsavel_id_nao_grava(self):
        chamado = _chamado_mock(responsavel_id=None)

        resultado = marcar_visualizado_pelo_responsavel(chamado, "resp_1")

        assert resultado is False
        chamado.atualizar_campos.assert_not_called()

    def test_chamado_none_retorna_false(self):
        assert marcar_visualizado_pelo_responsavel(None, "resp_1") is False

    def test_usuario_id_none_retorna_false(self):
        chamado = _chamado_mock()
        assert marcar_visualizado_pelo_responsavel(chamado, None) is False

    def test_atualizar_campos_falha_propaga_false(self):
        chamado = _chamado_mock()
        chamado.atualizar_campos.return_value = False

        resultado = marcar_visualizado_pelo_responsavel(chamado, "resp_1")

        assert resultado is False

    def test_atualizar_campos_levanta_excecao_retorna_false(self):
        chamado = _chamado_mock()
        chamado.atualizar_campos.side_effect = Exception("boom")

        resultado = marcar_visualizado_pelo_responsavel(chamado, "resp_1")

        assert resultado is False
