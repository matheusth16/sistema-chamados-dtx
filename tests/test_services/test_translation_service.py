"""Testes do serviço de tradução (translation_service)."""

import json
from unittest.mock import MagicMock, patch

from app.services.translation_service import (
    TRANSLATION_MAP,
    _traduzir_via_mymemory,
    adicionar_traducao_customizada,
    traduzir_categoria,
    traduzir_texto,
)


def test_traduzir_texto_do_mapa_pt_para_en():
    """Traduz termos do mapa PT -> EN."""
    assert traduzir_texto("Manutencao", "en") == "Maintenance"
    assert traduzir_texto("Engenharia", "en") == "Engineering"
    assert traduzir_texto("Qualidade", "en") == "Quality"


def test_traduzir_texto_do_mapa_pt_para_es():
    """Traduz termos do mapa PT -> ES."""
    assert traduzir_texto("Manutencao", "es") == "Mantenimiento"
    assert traduzir_texto("Engenharia", "es") == "Ingeniería"


def test_traduzir_texto_nao_encontrado_retorna_original():
    """Quando API falha, retorna o texto original como fallback."""
    with patch("app.services.translation_service._traduzir_via_mymemory", return_value=None):
        assert traduzir_texto("TermoQualquerSemAPI", "en") == "TermoQualquerSemAPI"


def test_traduzir_categoria_retorna_dict_pt_en_es():
    """traduzir_categoria retorna dicionário com chaves pt, en, es."""
    result = traduzir_categoria("Manutencao")
    assert "pt" in result and "en" in result and "es" in result
    assert result["en"] == "Maintenance"
    assert isinstance(result, dict)


def test_adicionar_traducao_customizada():
    """adicionar_traducao_customizada adiciona entrada ao TRANSLATION_MAP (texto_pt, en, es)."""
    adicionar_traducao_customizada("SetorTeste", "TestSector", "SectorPrueba")
    assert "SetorTeste" in TRANSLATION_MAP["pt_BR"]
    assert TRANSLATION_MAP["pt_BR"]["SetorTeste"]["en"] == "TestSector"
    assert TRANSLATION_MAP["pt_BR"]["SetorTeste"]["es"] == "SectorPrueba"


# ── PPCP renomeado para Planejamento de Produção ──────────────────────────────


def test_planejamento_producao_traduz_en():
    """Nome canônico 'Planejamento de Produção' traduz para inglês."""
    assert traduzir_texto("Planejamento de Produção", "en") == "Production Planning"


def test_planejamento_producao_traduz_es():
    """Nome canônico 'Planejamento de Produção' traduz para espanhol."""
    assert traduzir_texto("Planejamento de Produção", "es") == "Planificación de Producción"


def test_ppcp_alias_legado_traduz_en():
    """Alias legado 'PPCP' ainda traduz corretamente (histórico de chamados)."""
    result = traduzir_texto("PPCP", "en")
    assert result == "Production Planning"


def test_ppcp_alias_legado_traduz_es():
    """Alias legado 'PPCP' traduz para espanhol."""
    result = traduzir_texto("PPCP", "es")
    assert result == "Planificación de Producción"


def test_traduzir_categoria_planejamento_producao():
    """traduzir_categoria retorna dict correto para novo nome canônico."""
    result = traduzir_categoria("Planejamento de Produção")
    assert result["pt"] == "Planejamento de Produção"
    assert result["en"] == "Production Planning"
    assert result["es"] == "Planificación de Producción"


# ── Compras (unificação de Procurement) ───────────────────────────────────────


def test_compras_traduz_en():
    """Nome canônico 'Compras' traduz para inglês."""
    assert traduzir_texto("Compras", "en") == "Procurement"


def test_compras_traduz_es():
    """Nome canônico 'Compras' traduz para espanhol."""
    assert traduzir_texto("Compras", "es") == "Aprovisionamiento"


def test_procurement_alias_legado_traduz_en():
    """Alias legado 'Procurement' ainda traduz corretamente (histórico)."""
    assert traduzir_texto("Procurement", "en") == "Procurement"


def test_procurement_alias_legado_traduz_es():
    """Alias legado 'Procurement' traduz para espanhol."""
    assert traduzir_texto("Procurement", "es") == "Aprovisionamiento"


# ── Setores de Produção (desativados no catálogo, mas histórico legível) ──────


def test_producao_usinagem_traduz_no_historico():
    """'Produção - Usinagem' ainda é traduzível para histórico (setor desativado)."""
    assert traduzir_texto("Produção - Usinagem", "en") == "Production - Machining"


def test_producao_montagem_traduz_no_historico():
    """'Produção - Montagem' ainda é traduzível para histórico."""
    assert traduzir_texto("Produção - Montagem", "en") == "Production - Assembly"


def test_producao_inspecoes_traduz_no_historico():
    """'Produção - Inspeções' ainda é traduzível para histórico."""
    assert traduzir_texto("Produção - Inspeções", "en") == "Production - Inspections"


def test_producao_processos_especiais_traduz_no_historico():
    """'Produção - Processos Especiais' ainda é traduzível para histórico."""
    assert (
        traduzir_texto("Produção - Processos Especiais", "en") == "Production - Special Processes"
    )


# ── MyMemory API ──────────────────────────────────────────────────────────────


def _mock_urlopen(texto_traduzido: str):
    """Cria mock de urlopen retornando resposta MyMemory válida."""
    payload = json.dumps(
        {"responseStatus": 200, "responseData": {"translatedText": texto_traduzido}}
    ).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_traduzir_via_mymemory_retorna_traducao_da_api():
    """_traduzir_via_mymemory retorna texto da API quando responseStatus == 200."""
    with patch("urllib.request.urlopen", return_value=_mock_urlopen("Deadline")):
        resultado = _traduzir_via_mymemory("Prazo", "en")
    assert resultado == "Deadline"


def test_traduzir_via_mymemory_retorna_none_quando_api_falha():
    """_traduzir_via_mymemory retorna None quando urlopen lança exceção."""
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        resultado = _traduzir_via_mymemory("Prazo", "en")
    assert resultado is None


def test_traduzir_via_mymemory_retorna_none_quando_limite_excedido():
    """_traduzir_via_mymemory retorna None quando MyMemory retorna mensagem de limite."""
    with patch("urllib.request.urlopen", return_value=_mock_urlopen("QUERY LENGTH LIMIT EXCEEDED")):
        resultado = _traduzir_via_mymemory("Prazo", "en")
    assert resultado is None


def test_traduzir_via_mymemory_rejeita_resposta_sem_letras():
    """_traduzir_via_mymemory descarta 'tradução' sem nenhuma letra (ex.: '&&', '...', '123').

    Regressão: reproduzido em produção-like — MyMemory devolveu '&&' para o termo
    'Planejamento' (fora do mapa estático) e o sistema aceitou e cacheou isso
    permanentemente como o nome em inglês do setor.
    """
    with patch("urllib.request.urlopen", return_value=_mock_urlopen("&&")):
        resultado = _traduzir_via_mymemory("Planejamento", "en")
    assert resultado is None


def test_traduzir_texto_nao_cacheia_garbage_da_api():
    """traduzir_texto não cacheia/retorna lixo da API — cai no fallback (texto original)."""
    chave = "TermoGarbageTest"
    TRANSLATION_MAP["pt_BR"].pop(chave, None)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen("&&")):
        resultado = traduzir_texto(chave, "en")
    assert resultado == chave
    assert chave not in TRANSLATION_MAP["pt_BR"]


def test_traduzir_texto_usa_api_quando_nao_no_mapa():
    """traduzir_texto chama API para termos não presentes no mapa estático."""
    with patch(
        "app.services.translation_service._traduzir_via_mymemory", return_value="Deadline"
    ) as mock_api:
        resultado = traduzir_texto("PalavraNovaSemMapa", "en")
    mock_api.assert_called_once_with("PalavraNovaSemMapa", "en")
    assert resultado == "Deadline"


def test_traduzir_texto_cacheia_resultado_da_api():
    """Após chamada à API, resultado é cacheado em TRANSLATION_MAP."""
    chave = "TermoCacheTest"
    TRANSLATION_MAP["pt_BR"].pop(chave, None)
    with patch(
        "app.services.translation_service._traduzir_via_mymemory", return_value="CachedResult"
    ):
        traduzir_texto(chave, "en")
    assert TRANSLATION_MAP["pt_BR"].get(chave, {}).get("en") == "CachedResult"
    TRANSLATION_MAP["pt_BR"].pop(chave, None)  # cleanup


def test_traduzir_texto_nao_chama_api_para_termos_do_mapa():
    """traduzir_texto NÃO chama API quando o termo já existe no mapa estático."""
    with patch("app.services.translation_service._traduzir_via_mymemory") as mock_api:
        traduzir_texto("Qualidade", "en")
    mock_api.assert_not_called()


def test_translation_map_concorrencia_50_threads():
    """50 threads lendo/escrevendo TRANSLATION_MAP não geram RuntimeError."""
    import threading

    erros = []
    chaves = [f"TermoConcorrencia{i}" for i in range(50)]

    def worker(indice):
        try:
            chave = chaves[indice]
            with patch(
                "app.services.translation_service._traduzir_via_mymemory",
                return_value=f"Result{indice}",
            ):
                traduzir_texto(chave, "en")
            adicionar_traducao_customizada(chave, f"En{indice}", f"Es{indice}")
            traduzir_texto("Manutencao", "en")
        except Exception as exc:
            erros.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not erros, f"Erros de concorrência: {erros}"
    for chave in chaves:
        TRANSLATION_MAP["pt_BR"].pop(chave, None)
