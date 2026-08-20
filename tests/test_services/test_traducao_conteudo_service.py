"""Testes de traducao_conteudo_service: tradução automática (LibreTranslate)
de conteúdo dinâmico (descrição, histórico, conversa) com cache em Postgres.

Mock só do urlopen (serviço genuinamente externo) — cache real via fixture
db_session (Postgres), seguindo o mesmo padrão de test_escalonamento_service.py.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


def _mock_urlopen(traduzido: str, detectado: str | None):
    """Mock de UMA resposta de tradução de item único — LibreTranslate agora é
    chamado individualmente por texto (nunca em lote com `q` como array; ver
    nota em _traduzir_via_libretranslate sobre detecção de idioma quebrada em
    lote com idiomas misturados, achado em produção 2026-08-20)."""
    payload = json.dumps(
        {
            "translatedText": traduzido,
            "detectedLanguage": ({"language": detectado, "confidence": 90} if detectado else None),
        }
    ).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@pytest.fixture
def app_libretranslate(app):
    """App com LibreTranslate habilitado — usado nos testes que exercitam a
    chamada HTTP/cache. Fixture separada da `app` padrão (que fica sem a flag
    setada) pra deixar explícito quais testes dependem do serviço ligado."""
    app.config["LIBRETRANSLATE_ENABLED"] = True
    app.config["LIBRETRANSLATE_URL"] = "http://libretranslate.local:5000"
    app.config["LIBRETRANSLATE_TIMEOUT_SECONDS"] = 5
    return app


class TestTraduzirConteudoFeatureFlag:
    def test_flag_desligada_retorna_original_sem_chamar_http(self, app):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        app.config["LIBRETRANSLATE_ENABLED"] = False
        with (
            app.app_context(),
            patch("urllib.request.urlopen", side_effect=AssertionError("não deveria chamar")),
        ):
            resultado = traduzir_conteudo("Texto em português", "en")

        assert resultado == {"texto": "Texto em português", "traduzido": False, "original": None}


class TestTraduzirConteudoTextoVazio:
    def test_texto_vazio_retorna_original_sem_chamar_http(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        with (
            app_libretranslate.app_context(),
            patch("urllib.request.urlopen", side_effect=AssertionError("não deveria chamar")),
        ):
            resultado = traduzir_conteudo("   ", "en")

        assert resultado["traduzido"] is False


class TestTraduzirConteudoCacheMiss:
    def test_cache_miss_traduz_e_persiste(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                return_value=_mock_urlopen("Deadline extended", "pt"),
            ) as mock_urlopen,
        ):
            resultado = traduzir_conteudo("Prazo estendido", "en")

        mock_urlopen.assert_called_once()
        assert resultado == {
            "texto": "Deadline extended",
            "traduzido": True,
            "original": "Prazo estendido",
        }

    def test_cache_miss_persiste_linha_reutilizada_na_proxima_chamada(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                return_value=_mock_urlopen("Deadline extended", "pt"),
            ),
        ):
            traduzir_conteudo("Prazo estendido", "en")

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen", side_effect=AssertionError("cache deveria evitar isso")
            ),
        ):
            resultado = traduzir_conteudo("Prazo estendido", "en")

        assert resultado["texto"] == "Deadline extended"
        assert resultado["traduzido"] is True


class TestTraduzirConteudoIdiomaJaBate:
    def test_idioma_detectado_igual_ao_destino_nao_traduz_nem_persiste(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                return_value=_mock_urlopen("Already in English", "en"),
            ),
        ):
            resultado = traduzir_conteudo("Already in English", "en")

        assert resultado == {"texto": "Already in English", "traduzido": False, "original": None}

    def test_idioma_igual_nao_persiste_no_cache(self, app_libretranslate, db_session):
        from app.db.models.traducao_conteudo import TraducaoConteudoRow
        from app.services.traducao_conteudo_service import traduzir_conteudo

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                return_value=_mock_urlopen("Already in English", "en"),
            ),
        ):
            traduzir_conteudo("Already in English", "en")

        linhas = db_session.query(TraducaoConteudoRow).all()
        assert linhas == []


class TestTraduzirConteudoFailOpen:
    def test_libretranslate_indisponivel_retorna_original(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        with (
            app_libretranslate.app_context(),
            patch("urllib.request.urlopen", side_effect=OSError("timeout")),
        ):
            resultado = traduzir_conteudo("Texto qualquer", "en")

        assert resultado == {"texto": "Texto qualquer", "traduzido": False, "original": None}

    def test_libretranslate_resposta_malformada_retorna_original(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            app_libretranslate.app_context(),
            patch("urllib.request.urlopen", return_value=mock_resp),
        ):
            resultado = traduzir_conteudo("Texto qualquer", "en")

        assert resultado == {"texto": "Texto qualquer", "traduzido": False, "original": None}

    def test_idioma_destino_nao_suportado_retorna_original_sem_chamar_http(
        self, app_libretranslate
    ):
        from app.services.traducao_conteudo_service import traduzir_conteudo

        with (
            app_libretranslate.app_context(),
            patch("urllib.request.urlopen", side_effect=AssertionError("não deveria chamar")),
        ):
            resultado = traduzir_conteudo("Texto qualquer", "de")

        assert resultado == {"texto": "Texto qualquer", "traduzido": False, "original": None}


class TestTraduzirVariosLote:
    def test_lote_misto_hit_e_miss_faz_uma_unica_chamada_http(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo, traduzir_varios

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                return_value=_mock_urlopen("Cached hit translated", "pt"),
            ),
        ):
            traduzir_conteudo("Já em cache", "en")

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                return_value=_mock_urlopen("Texto novo traduzido", "pt"),
            ) as mock_urlopen,
        ):
            resultado = traduzir_varios(["Já em cache", "Texto novo"], "en")

        mock_urlopen.assert_called_once()
        request_enviado = mock_urlopen.call_args[0][0]
        corpo_enviado = json.loads(request_enviado.data.decode())
        assert corpo_enviado["q"] == "Texto novo"

        assert resultado["Já em cache"]["texto"] == "Cached hit translated"
        assert resultado["Texto novo"]["texto"] == "Texto novo traduzido"

    def test_lote_totalmente_em_cache_nao_chama_http(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_conteudo, traduzir_varios

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                side_effect=[_mock_urlopen("A", "pt"), _mock_urlopen("B", "pt")],
            ),
        ):
            traduzir_varios(["Texto A", "Texto B"], "en")

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen", side_effect=AssertionError("cache deveria evitar isso")
            ),
        ):
            resultado = traduzir_conteudo("Texto A", "en")

        assert resultado["texto"] == "A"

    def test_lote_com_idiomas_misturados_detecta_cada_item_corretamente(self, app_libretranslate):
        """Regressão (achado em produção, chamado real, 2026-08-20): um texto
        já em inglês (ex.: descrição) e um texto em português (ex.: nota do
        histórico) no MESMO lote não podem "contaminar" a detecção um do
        outro. Antes (array batch com source=auto), o LibreTranslate detectava
        o idioma do lote inteiro de uma vez e o item em português voltava sem
        tradução nenhuma. Agora cada texto é uma chamada HTTP independente —
        o teste simula exatamente isso: duas respostas diferentes, uma por
        chamada, cada uma com seu próprio idioma detectado."""
        from app.services.traducao_conteudo_service import traduzir_varios

        with (
            app_libretranslate.app_context(),
            patch(
                "urllib.request.urlopen",
                side_effect=[
                    _mock_urlopen("Already in English", "en"),
                    _mock_urlopen("Missing ~26min to level 1", "pt"),
                ],
            ) as mock_urlopen,
        ):
            resultado = traduzir_varios(["Already in English", "Faltam ~26min pro nível 1"], "en")

        assert mock_urlopen.call_count == 2
        # Texto já em inglês: detectado == destino → não "traduzido" (mostra original)
        assert resultado["Already in English"]["traduzido"] is False
        # Texto em português: detectado != destino → traduzido de verdade
        assert resultado["Faltam ~26min pro nível 1"]["traduzido"] is True
        assert resultado["Faltam ~26min pro nível 1"]["texto"] == "Missing ~26min to level 1"

    def test_lote_vazio_retorna_dict_vazio(self, app_libretranslate):
        from app.services.traducao_conteudo_service import traduzir_varios

        with app_libretranslate.app_context():
            resultado = traduzir_varios([], "en")

        assert resultado == {}


def _historico_mock(
    acao="alteracao_status",
    campo_alterado=None,
    valor_anterior=None,
    valor_novo=None,
    detalhe=None,
):
    h = MagicMock()
    h.acao = acao
    h.campo_alterado = campo_alterado
    h.valor_anterior = valor_anterior
    h.valor_novo = valor_novo
    h.detalhe = detalhe
    return h


class TestMontarTraducoesChamado:
    """Monta o lote único de textos livres da tela de detalhe (chamado +
    histórico) — nunca traduz valor estruturado já coberto por
    translate_status/translate_category (mesma regra condicional do
    historico.html)."""

    def test_inclui_descricao_e_motivos_do_chamado(self, app_libretranslate):
        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        chamado = MagicMock()
        chamado.descricao = "Descrição do problema"
        chamado.motivo_cancelamento = "Motivo do cancelamento"
        chamado.motivo_previsao_atendimento = None
        chamado.motivo_ultima_escalacao = None

        with (
            app_libretranslate.app_context(),
            patch("app.services.traducao_conteudo_service.traduzir_varios") as mock_traduzir,
        ):
            mock_traduzir.return_value = {}
            montar_traducoes_chamado(chamado, [], "en")

        textos_enviados = mock_traduzir.call_args[0][0]
        assert "Descrição do problema" in textos_enviados
        assert "Motivo do cancelamento" in textos_enviados

    def test_status_estruturado_nao_entra_no_lote(self, app_libretranslate):
        """campo_alterado == 'status' já é traduzido por translate_status — não
        deve passar pelo LibreTranslate."""
        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        chamado = MagicMock(
            descricao=None,
            motivo_cancelamento=None,
            motivo_previsao_atendimento=None,
            motivo_ultima_escalacao=None,
        )
        h = _historico_mock(
            acao="alteracao_status",
            campo_alterado="status",
            valor_anterior="Aberto",
            valor_novo="Em Atendimento",
        )

        with (
            app_libretranslate.app_context(),
            patch("app.services.traducao_conteudo_service.traduzir_varios") as mock_traduzir,
        ):
            mock_traduzir.return_value = {}
            montar_traducoes_chamado(chamado, [h], "en")

        textos_enviados = mock_traduzir.call_args[0][0]
        assert "Aberto" not in textos_enviados
        assert "Em Atendimento" not in textos_enviados

    def test_nota_de_reabertura_texto_livre_entra_no_lote(self, app_libretranslate):
        """reabertura com campo_alterado != 'status' carrega nota livre (não
        estruturada) — precisa entrar no lote."""
        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        chamado = MagicMock(
            descricao=None,
            motivo_cancelamento=None,
            motivo_previsao_atendimento=None,
            motivo_ultima_escalacao=None,
        )
        h = _historico_mock(
            acao="reabertura",
            campo_alterado="motivo",
            valor_anterior=None,
            valor_novo="Reaberto porque o problema voltou",
        )

        with (
            app_libretranslate.app_context(),
            patch("app.services.traducao_conteudo_service.traduzir_varios") as mock_traduzir,
        ):
            mock_traduzir.return_value = {}
            montar_traducoes_chamado(chamado, [h], "en")

        textos_enviados = mock_traduzir.call_args[0][0]
        assert "Reaberto porque o problema voltou" in textos_enviados

    def test_conversa_entra_no_lote(self, app_libretranslate):
        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        chamado = MagicMock(
            descricao=None,
            motivo_cancelamento=None,
            motivo_previsao_atendimento=None,
            motivo_ultima_escalacao=None,
        )
        h = _historico_mock(acao="resposta_solicitante", valor_novo="Ainda não resolveu")

        with (
            app_libretranslate.app_context(),
            patch("app.services.traducao_conteudo_service.traduzir_varios") as mock_traduzir,
        ):
            mock_traduzir.return_value = {}
            montar_traducoes_chamado(chamado, [h], "en")

        textos_enviados = mock_traduzir.call_args[0][0]
        assert "Ainda não resolveu" in textos_enviados

    def test_anexo_nao_entra_no_lote(self, app_libretranslate):
        """detalhe de anexo (nome de arquivo) não deve ir pro LibreTranslate."""
        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        chamado = MagicMock(
            descricao=None,
            motivo_cancelamento=None,
            motivo_previsao_atendimento=None,
            motivo_ultima_escalacao=None,
        )
        h = _historico_mock(
            acao="alteracao_dados",
            campo_alterado="novo anexo",
            valor_novo="/anexos/laudo_tecnico.pdf",
            detalhe="laudo_tecnico.pdf",
        )

        with (
            app_libretranslate.app_context(),
            patch("app.services.traducao_conteudo_service.traduzir_varios") as mock_traduzir,
        ):
            mock_traduzir.return_value = {}
            montar_traducoes_chamado(chamado, [h], "en")

        textos_enviados = mock_traduzir.call_args[0][0]
        assert "laudo_tecnico.pdf" not in textos_enviados
        assert "/anexos/laudo_tecnico.pdf" not in textos_enviados

    def test_detalhe_de_transferencia_entra_no_lote(self, app_libretranslate):
        from app.services.traducao_conteudo_service import montar_traducoes_chamado

        chamado = MagicMock(
            descricao=None,
            motivo_cancelamento=None,
            motivo_previsao_atendimento=None,
            motivo_ultima_escalacao=None,
        )
        h = _historico_mock(
            acao="transferencia_area",
            campo_alterado="area",
            valor_anterior="Engenharia",
            valor_novo="Planejamento",
            detalhe="Transferido para Planejamento — falta peça, não é engenharia",
        )

        with (
            app_libretranslate.app_context(),
            patch("app.services.traducao_conteudo_service.traduzir_varios") as mock_traduzir,
        ):
            mock_traduzir.return_value = {}
            montar_traducoes_chamado(chamado, [h], "en")

        textos_enviados = mock_traduzir.call_args[0][0]
        assert "Transferido para Planejamento — falta peça, não é engenharia" in textos_enviados
        # valores estruturados de área não entram (já cobertos por outro mecanismo)
        assert "Engenharia" not in textos_enviados
