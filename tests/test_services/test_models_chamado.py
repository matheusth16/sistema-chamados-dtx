"""Testes para models.py — Chamado.to_dict, from_dict e helpers de data."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
import pytz


def _chamado(**kwargs):
    from app.models import Chamado

    defaults = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Descrição teste",
        "responsavel": "Ana",
    }
    defaults.update(kwargs)
    return Chamado(**defaults)


# ── __init__ valores padrão ───────────────────────────────────────────────────


def test_chamado_status_padrao_aberto():
    assert _chamado().status == "Aberto"


def test_chamado_prioridade_padrao_1():
    assert _chamado().prioridade == 1


def test_chamado_anexos_lista_vazia_por_padrao():
    assert _chamado().anexos == []


def test_chamado_setores_adicionais_lista_vazia():
    assert _chamado().setores_adicionais == []


def test_chamado_projetos_forcam_prioridade_zero():
    c = _chamado(categoria="Projetos", prioridade=3)
    assert c.prioridade == 0


def test_chamado_aog_forca_prioridade_menos_um():
    """AOG é prioridade máxima e fica acima de Projetos (0) na ordenação."""
    c = _chamado(categoria="AOG", prioridade=3)
    assert c.prioridade == -1


def test_chamado_prioridade_none_vira_1():
    c = _chamado(prioridade=None)
    assert c.prioridade == 1


# ── to_dict ───────────────────────────────────────────────────────────────────


def test_to_dict_contem_categoria():
    d = _chamado(categoria="Manutencao").to_dict()
    assert d["categoria"] == "Manutencao"


def test_to_dict_contem_status():
    d = _chamado(status="Em Atendimento").to_dict()
    assert d["status"] == "Em Atendimento"


def test_to_dict_contem_numero_chamado():
    d = _chamado(numero_chamado="CH-999").to_dict()
    assert d["numero_chamado"] == "CH-999"


def test_to_dict_contem_todos_campos_esperados():
    d = _chamado().to_dict()
    chaves_esperadas = [
        "categoria",
        "tipo_solicitacao",
        "descricao",
        "responsavel",
        "status",
        "data_abertura",
        "data_conclusao",
        "prioridade",
        "anexos",
        "setores_adicionais",
    ]
    for chave in chaves_esperadas:
        assert chave in d, f"Campo ausente em to_dict: {chave}"


def test_to_dict_previsao_atendimento_padrao_none():
    d = _chamado().to_dict()
    assert d["previsao_atendimento"] is None
    assert d["motivo_previsao_atendimento"] is None


def test_to_dict_previsao_atendimento_customizada():
    previsao = datetime(2026, 7, 15, 16, 0, tzinfo=pytz.timezone("America/Sao_Paulo"))
    d = _chamado(
        previsao_atendimento=previsao, motivo_previsao_atendimento="Combinado com o gestor"
    ).to_dict()
    assert d["previsao_atendimento"] == previsao
    assert d["motivo_previsao_atendimento"] == "Combinado com o gestor"


# ── from_dict ─────────────────────────────────────────────────────────────────


def test_from_dict_cria_objeto_com_campos():
    from app.models import Chamado

    data = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Teste",
        "responsavel": "Bob",
    }
    c = Chamado.from_dict(data)
    assert c.categoria == "TI"
    assert c.responsavel == "Bob"


def test_from_dict_status_padrao_aberto():
    from app.models import Chamado

    c = Chamado.from_dict(
        {"categoria": "X", "tipo_solicitacao": "Y", "descricao": "Z", "responsavel": "R"}
    )
    assert c.status == "Aberto"


def test_from_dict_status_customizado():
    from app.models import Chamado

    c = Chamado.from_dict(
        {
            "categoria": "X",
            "tipo_solicitacao": "Y",
            "descricao": "Z",
            "responsavel": "R",
            "status": "Concluído",
        }
    )
    assert c.status == "Concluído"


def test_from_dict_dados_vazios_levanta_validacao_error():
    from app.exceptions import ValidacaoChamadoError
    from app.models import Chamado

    with pytest.raises(ValidacaoChamadoError):
        Chamado.from_dict({})


def test_from_dict_none_levanta_validacao_error():
    from app.exceptions import ValidacaoChamadoError
    from app.models import Chamado

    with pytest.raises(ValidacaoChamadoError):
        Chamado.from_dict(None)


def test_from_dict_previsao_atendimento_padrao_none():
    from app.models import Chamado

    c = Chamado.from_dict(
        {"categoria": "TI", "tipo_solicitacao": "S", "descricao": "D", "responsavel": "R"}
    )
    assert c.previsao_atendimento is None
    assert c.motivo_previsao_atendimento is None


def test_from_dict_previsao_atendimento_customizada():
    from app.models import Chamado

    previsao = datetime(2026, 7, 15, 16, 0, tzinfo=pytz.timezone("America/Sao_Paulo"))
    c = Chamado.from_dict(
        {
            "categoria": "TI",
            "tipo_solicitacao": "S",
            "descricao": "D",
            "responsavel": "R",
            "previsao_atendimento": previsao,
            "motivo_previsao_atendimento": "Combinado com o gestor",
        }
    )
    assert c.previsao_atendimento == previsao
    assert c.motivo_previsao_atendimento == "Combinado com o gestor"


def test_from_dict_preserva_id():
    from app.models import Chamado

    c = Chamado.from_dict(
        {"categoria": "TI", "tipo_solicitacao": "S", "descricao": "D", "responsavel": "R"},
        id="ch_abc",
    )
    assert c.id == "ch_abc"


def test_from_dict_anexos_nao_lista_vira_lista_vazia():
    from app.models import Chamado

    c = Chamado.from_dict(
        {
            "categoria": "TI",
            "tipo_solicitacao": "S",
            "descricao": "D",
            "responsavel": "R",
            "anexos": "nao_e_lista",
        }
    )
    assert c.anexos == []


def test_from_dict_setores_adicionais_nao_lista_vira_lista_vazia():
    from app.models import Chamado

    c = Chamado.from_dict(
        {
            "categoria": "TI",
            "tipo_solicitacao": "S",
            "descricao": "D",
            "responsavel": "R",
            "setores_adicionais": "errado",
        }
    )
    assert c.setores_adicionais == []


def test_from_dict_none_campos_texto_vira_string_vazia():
    from app.models import Chamado

    c = Chamado.from_dict(
        {
            "categoria": None,
            "tipo_solicitacao": None,
            "descricao": None,
            "responsavel": None,
        }
    )
    assert c.categoria == ""
    assert c.descricao == ""


# ── _converter_timestamp ──────────────────────────────────────────────────────


def test_converter_timestamp_none_retorna_none():
    assert _chamado()._converter_timestamp(None) is None


def test_converter_timestamp_string_retorna_none():
    assert _chamado()._converter_timestamp("2024-01-01") is None


def test_converter_timestamp_datetime_utc_converte_para_brasilia():
    dt_utc = datetime(2024, 6, 15, 15, 0, tzinfo=pytz.utc)
    resultado = _chamado()._converter_timestamp(dt_utc)
    assert resultado is not None
    assert resultado.tzinfo is not None


def test_converter_timestamp_datetime_sem_tz_assume_utc():
    dt_naive = datetime(2024, 6, 15, 12, 0)
    resultado = _chamado()._converter_timestamp(dt_naive)
    assert resultado is not None


def test_converter_timestamp_objeto_com_to_pydatetime():
    mock_ts = MagicMock()
    mock_ts.to_pydatetime.return_value = datetime(2024, 6, 15, 10, 0, tzinfo=pytz.utc)
    resultado = _chamado()._converter_timestamp(mock_ts)
    assert resultado is not None


# ── formatação de datas ───────────────────────────────────────────────────────


def test_data_abertura_formatada_retorna_traco_quando_none():
    c = _chamado()
    c.data_abertura = None
    assert c.data_abertura_formatada() == "-"


def test_data_abertura_formatada_retorna_string_data():
    c = _chamado()
    c.data_abertura = datetime(2024, 6, 15, 10, 30, tzinfo=pytz.utc)
    resultado = c.data_abertura_formatada()
    assert "/" in resultado
    assert ":" in resultado


def test_data_conclusao_formatada_retorna_traco_quando_none():
    c = _chamado()
    c.data_conclusao = None
    assert c.data_conclusao_formatada() == "-"


def test_data_cancelamento_formatada_retorna_traco_quando_none():
    c = _chamado()
    c.data_cancelamento = None
    assert c.data_cancelamento_formatada() == "-"


def test_previsao_atendimento_formatada_retorna_traco_quando_none():
    c = _chamado()
    c.previsao_atendimento = None
    assert c.previsao_atendimento_formatada() == "-"


def test_previsao_atendimento_formatada_retorna_string_data():
    c = _chamado()
    c.previsao_atendimento = datetime(2024, 6, 15, 10, 30, tzinfo=pytz.utc)
    resultado = c.previsao_atendimento_formatada()
    assert "/" in resultado
    assert ":" in resultado


# ── __repr__ ─────────────────────────────────────────────────────────────────


def test_repr_contem_id_e_categoria():
    c = _chamado(categoria="Engenharia")
    c.id = "ch_repr"
    r = repr(c)
    assert "ch_repr" in r
    assert "Engenharia" in r


# ── participantes[] — Fase 4 ──────────────────────────────────────────────────


def test_chamado_from_dict_com_participantes():
    from app.models import Chamado

    data = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Teste",
        "responsavel": "Ana",
        "participantes": [
            {"supervisor_id": "id_julia", "area": "TI", "status": "pendente", "concluido_em": None}
        ],
    }
    c = Chamado.from_dict(data)
    assert len(c.participantes) == 1
    assert c.participantes[0]["supervisor_id"] == "id_julia"
    assert c.participantes[0]["status"] == "pendente"


def test_chamado_from_dict_sem_participantes_lista_vazia():
    from app.models import Chamado

    data = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Teste",
        "responsavel": "Ana",
    }
    c = Chamado.from_dict(data)
    assert c.participantes == []


def test_chamado_to_dict_inclui_participantes():
    from app.models import Chamado

    participantes = [
        {"supervisor_id": "x", "area": "TI", "status": "pendente", "concluido_em": None}
    ]
    c = Chamado(
        categoria="TI",
        tipo_solicitacao="Suporte",
        descricao="Teste",
        responsavel="Ana",
        participantes=participantes,
    )
    d = c.to_dict()
    assert "participantes" in d
    assert d["participantes"][0]["supervisor_id"] == "x"
    assert d["participantes"][0]["status"] == "pendente"


def test_chamado_from_dict_participantes_nao_lista_vira_lista_vazia():
    from app.models import Chamado

    data = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Teste",
        "responsavel": "Ana",
        "participantes": "invalido",
    }
    c = Chamado.from_dict(data)
    assert c.participantes == []


def test_chamado_participantes_default_lista_vazia():
    c = _chamado()
    assert c.participantes == []


# ── Escada B — Fase 7 ──────────────────────────────────────────────────────────


def test_chamado_campos_escada_b_defaults():
    """Campos da Escada B têm defaults corretos: nivel=0, alertas=False/False."""
    c = _chamado()
    assert c.escalacao_resolucao_nivel == 0
    assert c.alerta_supervisor_50_enviado is False
    assert c.alerta_supervisor_80_enviado is False


def test_chamado_to_dict_inclui_campos_escada_b():
    """to_dict inclui os 3 campos da Escada B."""
    d = _chamado().to_dict()
    assert "escalacao_resolucao_nivel" in d
    assert d["escalacao_resolucao_nivel"] == 0
    assert "alerta_supervisor_50_enviado" in d
    assert d["alerta_supervisor_50_enviado"] is False
    assert "alerta_supervisor_80_enviado" in d
    assert d["alerta_supervisor_80_enviado"] is False


def test_chamado_from_dict_campos_escada_b_ausentes_usa_defaults():
    """from_dict sem campos Escada B usa defaults seguros (retro-compatibilidade)."""
    from app.models import Chamado

    data = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Teste",
        "responsavel": "Ana",
    }
    c = Chamado.from_dict(data)
    assert c.escalacao_resolucao_nivel == 0
    assert c.alerta_supervisor_50_enviado is False
    assert c.alerta_supervisor_80_enviado is False
