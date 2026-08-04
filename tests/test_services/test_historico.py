"""
Testes unitários do modelo Historico (Fase 2, Marco 8 — Postgres real).
Cobre: save, get_by_chamado_id, data_acao_formatada, __repr__.
"""

from datetime import datetime

import pytest
import pytz

from app.models_historico import Historico
from tests.factories import make_chamado

pytestmark = pytest.mark.usefixtures("db_session")


# ── save ───────────────────────────────────────────────────────────────────────


def test_save_persiste_e_retorna_true():
    """save persiste o registro e popula id/data_acao."""
    chamado = make_chamado()
    h = Historico(chamado_id=chamado.id, usuario_id="u1", usuario_nome="Admin", acao="criacao")

    result = h.save()

    assert result is True
    assert h.id is not None
    assert h.data_acao is not None


def test_save_retorna_false_quando_banco_falha(monkeypatch):
    """save captura exceção do banco e retorna False (ex.: conexão indisponível)."""
    from app import models_historico

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(models_historico.db_module, "SessionLocal", _explode)

    h = Historico(chamado_id=1, usuario_id="u1", usuario_nome="A", acao="criacao")
    result = h.save()

    assert result is False


def test_save_sem_detalhe_grava_none():
    """save sem detalhe grava NULL na coluna, sem levantar erro."""
    chamado = make_chamado()
    Historico(chamado_id=chamado.id, usuario_id="u1", usuario_nome="Admin", acao="criacao").save()

    historico = Historico.get_by_chamado_id(chamado.id)

    assert historico[0].detalhe is None


def test_save_com_detalhe_persiste_valor():
    """save com detalhe grava o valor informado."""
    chamado = make_chamado()
    Historico(
        chamado_id=chamado.id,
        usuario_id="u1",
        usuario_nome="Admin",
        acao="alteracao_dados",
        detalhe="arquivo.pdf",
    ).save()

    historico = Historico.get_by_chamado_id(chamado.id)

    assert historico[0].detalhe == "arquivo.pdf"


# ── get_by_chamado_id ──────────────────────────────────────────────────────────


def test_get_by_chamado_id_retorna_mais_recente_primeiro():
    """get_by_chamado_id ordena por data_acao decrescente."""
    chamado = make_chamado()
    Historico(chamado_id=chamado.id, usuario_id="u1", usuario_nome="A", acao="criacao").save()
    Historico(
        chamado_id=chamado.id, usuario_id="u1", usuario_nome="A", acao="alteracao_status"
    ).save()

    result = Historico.get_by_chamado_id(chamado.id)

    assert [h.acao for h in result] == ["alteracao_status", "criacao"]


def test_get_by_chamado_id_aceita_string_numerica():
    """get_by_chamado_id aceita chamado_id como string (ex.: vindo de rota Flask)."""
    chamado = make_chamado()
    Historico(chamado_id=chamado.id, usuario_id="u1", usuario_nome="A", acao="criacao").save()

    result = Historico.get_by_chamado_id(str(chamado.id))

    assert len(result) == 1


def test_get_by_chamado_id_retorna_vazio_para_id_invalido():
    """get_by_chamado_id retorna [] pra chamado_id não conversível a int, sem levantar erro."""
    assert Historico.get_by_chamado_id("nao-numerico") == []
    assert Historico.get_by_chamado_id(None) == []


def test_get_by_chamado_id_nao_mistura_chamados_diferentes():
    """get_by_chamado_id filtra estritamente pelo chamado pedido."""
    chamado1 = make_chamado()
    chamado2 = make_chamado()
    Historico(chamado_id=chamado1.id, usuario_id="u1", usuario_nome="A", acao="criacao").save()
    Historico(chamado_id=chamado2.id, usuario_id="u1", usuario_nome="A", acao="criacao").save()

    result = Historico.get_by_chamado_id(chamado1.id)

    assert len(result) == 1
    assert result[0].chamado_id == chamado1.id


def test_get_by_chamado_id_retorna_vazio_quando_banco_falha(monkeypatch):
    """get_by_chamado_id captura exceção do banco e retorna []."""
    from app import models_historico

    def _explode():
        raise RuntimeError("conexão perdida")

    monkeypatch.setattr(models_historico.db_module, "SessionLocal", _explode)

    assert Historico.get_by_chamado_id(1) == []


# ── valor_anterior/valor_novo (JSONB) ───────────────────────────────────────────


def test_valores_string_sao_preservados_no_round_trip():
    """valor_anterior/valor_novo (JSONB) preservam string após save + reload."""
    chamado = make_chamado()
    Historico(
        chamado_id=chamado.id,
        usuario_id="u1",
        usuario_nome="A",
        acao="alteracao_status",
        campo_alterado="status",
        valor_anterior="Aberto",
        valor_novo="Em Atendimento",
    ).save()

    result = Historico.get_by_chamado_id(chamado.id)[0]

    assert result.valor_anterior == "Aberto"
    assert result.valor_novo == "Em Atendimento"


def test_valores_none_sao_preservados():
    """valor_anterior/valor_novo ausentes continuam None após save + reload."""
    chamado = make_chamado()
    Historico(chamado_id=chamado.id, usuario_id="u1", usuario_nome="A", acao="criacao").save()

    result = Historico.get_by_chamado_id(chamado.id)[0]

    assert result.valor_anterior is None
    assert result.valor_novo is None


# ── data_acao_formatada ────────────────────────────────────────────────────────


def test_data_acao_formatada_com_datetime():
    """data_acao_formatada retorna string formatada quando data_acao é datetime."""
    dt = pytz.utc.localize(datetime(2026, 3, 20, 10, 30, 0))
    h = Historico(chamado_id=1, usuario_id="u1", usuario_nome="A", acao="criacao", data_acao=dt)

    result = h.data_acao_formatada()

    assert "2026" in result
    assert "/" in result


def test_data_acao_formatada_sem_data_retorna_traco():
    """data_acao_formatada retorna '-' quando data_acao é None."""
    h = Historico(chamado_id=1, usuario_id="u1", usuario_nome="A", acao="criacao")

    assert h.data_acao_formatada() == "-"


# ── __repr__ ───────────────────────────────────────────────────────────────────


def test_repr_contem_chamado_id_e_acao():
    """__repr__ de Historico contém chamado_id e acao."""
    h = Historico(chamado_id=99, usuario_id="u1", usuario_nome="A", acao="criacao")

    r = repr(h)

    assert "99" in r
    assert "criacao" in r
