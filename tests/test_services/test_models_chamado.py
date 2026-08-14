"""Testes para models.py — Chamado.to_dict, from_dict e helpers de data.

Fase 2 (Marco 7) — salvar/get_by_id/atualizar_campos/deletar rodam contra
Postgres real (db_session)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
import pytz

pytestmark = pytest.mark.usefixtures("db_session")


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


# ── Motor de escalonamento unificado ────────────────────────────────────────


def test_chamado_campos_escalonamento_defaults():
    """Campos do motor de escalonamento têm defaults corretos."""
    c = _chamado()
    assert c.escalacao_nivel == 0
    assert c.escalacao_proximo_tick_em is None
    assert c.escalacao_pre_aviso_nivel_enviado is None
    assert c.alerta_supervisor_50_enviado is False
    assert c.alerta_supervisor_80_enviado is False


def test_chamado_to_dict_inclui_campos_escalonamento():
    """to_dict inclui os campos do motor de escalonamento."""
    d = _chamado().to_dict()
    assert "escalacao_nivel" in d
    assert d["escalacao_nivel"] == 0
    assert "escalacao_proximo_tick_em" in d
    assert "escalacao_pre_aviso_nivel_enviado" in d
    assert "alerta_supervisor_50_enviado" in d
    assert d["alerta_supervisor_50_enviado"] is False
    assert "alerta_supervisor_80_enviado" in d
    assert d["alerta_supervisor_80_enviado"] is False


def test_chamado_from_dict_campos_escalonamento_ausentes_usa_defaults():
    """from_dict sem campos de escalonamento usa defaults seguros (retro-compatibilidade)."""
    from app.models import Chamado

    data = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Teste",
        "responsavel": "Ana",
    }
    c = Chamado.from_dict(data)
    assert c.escalacao_nivel == 0
    assert c.escalacao_proximo_tick_em is None
    assert c.escalacao_pre_aviso_nivel_enviado is None
    assert c.alerta_supervisor_50_enviado is False
    assert c.alerta_supervisor_80_enviado is False


# ── Persistência (Fase 2 — Postgres real) ────────────────────────────────────


def test_salvar_novo_persiste_e_retorna_id(app):
    c = _chamado(numero_chamado="CHM-0001")
    novo_id = c.salvar()

    assert novo_id is not None
    assert c.id == novo_id


def test_get_by_id_recupera_chamado_salvo(app):
    c = _chamado(numero_chamado="CHM-0002", descricao="Descrição original")
    c.salvar()

    recarregado = _chamado_get_by_id(c.id)

    assert recarregado is not None
    assert recarregado.descricao == "Descrição original"
    assert recarregado.categoria == "TI"


def test_get_by_id_nao_encontrado_retorna_none(app):
    assert _chamado_get_by_id(999999) is None


def test_get_by_id_id_invalido_retorna_none(app):
    assert _chamado_get_by_id("nao-e-um-numero") is None


def test_salvar_existente_atualiza_campos(app):
    c = _chamado(numero_chamado="CHM-0003", status="Aberto")
    c.salvar()

    c.status = "Em Atendimento"
    c.salvar()

    recarregado = _chamado_get_by_id(c.id)
    assert recarregado.status == "Em Atendimento"


def test_atualizar_campos_persiste_subset(app):
    c = _chamado(numero_chamado="CHM-0004", status="Aberto")
    c.salvar()

    resultado = c.atualizar_campos(status="Concluído", motivo_cancelamento=None)

    assert resultado is True
    recarregado = _chamado_get_by_id(c.id)
    assert recarregado.status == "Concluído"


def test_atualizar_campos_sem_id_retorna_false(app):
    c = _chamado()
    assert c.atualizar_campos(status="Concluído") is False


def test_atualizar_campos_ignora_chaves_invalidas(app):
    c = _chamado(numero_chamado="CHM-0005")
    c.salvar()

    assert c.atualizar_campos(campo_que_nao_existe="x") is False


def test_atualizar_campos_cas_aplica_quando_precondicoes_conferem(app):
    c = _chamado(numero_chamado="CHM-CAS-1", status="Aberto", responsavel_id=None)
    c.salvar()

    resultado = c.atualizar_campos_cas(
        precondicoes={"status": "Aberto", "responsavel_id": None},
        status="Em Atendimento",
        responsavel_id="sup-1",
    )

    assert resultado is True
    recarregado = _chamado_get_by_id(c.id)
    assert recarregado.status == "Em Atendimento"
    assert recarregado.responsavel_id == "sup-1"


def test_atualizar_campos_cas_rejeita_snapshot_obsoleto(app):
    c = _chamado(numero_chamado="CHM-CAS-2", status="Aberto")
    c.salvar()
    assert c.atualizar_campos(status="Em Atendimento")

    resultado = c.atualizar_campos_cas(
        precondicoes={"status": "Aberto"},
        status="Cancelado",
    )

    assert resultado is False
    assert _chamado_get_by_id(c.id).status == "Em Atendimento"


def test_atualizar_campos_cas_incrementa_contador_no_banco(app):
    c = _chamado(
        numero_chamado="CHM-CAS-3",
        status="Concluído",
        confirmacao_solicitante="pendente",
        reaberturas_solicitante_count=1,
    )
    c.salvar()

    resultado = c.atualizar_campos_cas(
        precondicoes={
            "status": "Concluído",
            "confirmacao_solicitante": "pendente",
        },
        incrementos={"reaberturas_solicitante_count": 1},
        status="Aberto",
        confirmacao_solicitante="reaberto",
    )

    assert resultado is True
    recarregado = _chamado_get_by_id(c.id)
    assert recarregado.reaberturas_solicitante_count == 2
    assert recarregado.status == "Aberto"


def test_deletar_remove_chamado(app):
    c = _chamado(numero_chamado="CHM-0006")
    c.salvar()
    chamado_id = c.id

    assert c.deletar() is True
    assert _chamado_get_by_id(chamado_id) is None


# ── Participantes / Observadores (tabela-junção) ─────────────────────────────


def test_salvar_persiste_participantes(app):
    c = _chamado(
        numero_chamado="CHM-0007",
        participantes=[{"supervisor_id": "sup1", "area": "TI", "status": "pendente"}],
    )
    c.salvar()

    recarregado = _chamado_get_by_id(c.id)
    assert len(recarregado.participantes) == 1
    assert recarregado.participantes[0]["supervisor_id"] == "sup1"
    assert recarregado.participantes[0]["area"] == "TI"
    assert recarregado.participantes[0]["status"] == "pendente"
    assert recarregado.participantes[0]["concluido_em"] is None


def test_salvar_persiste_participante_concluido_com_timestamp(app):
    agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
    c = _chamado(
        numero_chamado="CHM-0008",
        participantes=[
            {"supervisor_id": "sup1", "area": "TI", "status": "concluido", "concluido_em": agora}
        ],
    )
    c.salvar()

    recarregado = _chamado_get_by_id(c.id)
    assert recarregado.participantes[0]["status"] == "concluido"
    assert recarregado.participantes[0]["concluido_em"] is not None


def test_salvar_substitui_participantes_ao_resalvar(app):
    """participantes é sempre o estado completo desejado — resalvar com lista
    menor remove os que saíram."""
    c = _chamado(
        numero_chamado="CHM-0009",
        participantes=[{"supervisor_id": "sup1", "area": "TI"}],
    )
    c.salvar()

    c.participantes = [
        {"supervisor_id": "sup1", "area": "TI"},
        {"supervisor_id": "sup2", "area": "RH"},
    ]
    c.salvar()

    recarregado = _chamado_get_by_id(c.id)
    ids = {p["supervisor_id"] for p in recarregado.participantes}
    assert ids == {"sup1", "sup2"}


def test_salvar_persiste_observadores(app):
    c = _chamado(
        numero_chamado="CHM-0010",
        observadores=[{"usuario_id": "u1", "nome": "Fulano", "email": "f@b.com"}],
    )
    c.salvar()

    recarregado = _chamado_get_by_id(c.id)
    assert len(recarregado.observadores) == 1
    assert recarregado.observadores[0]["usuario_id"] == "u1"
    assert recarregado.observadores[0]["nome"] == "Fulano"
    assert recarregado.observadores[0]["email"] == "f@b.com"


def test_deletar_remove_participantes_e_observadores_via_cascade(app):
    from app.db.models.chamado import ChamadoObservadorRow, ChamadoParticipanteRow
    from app.models import db_module as models_db_module

    c = _chamado(
        numero_chamado="CHM-0011",
        participantes=[{"supervisor_id": "sup1", "area": "TI"}],
        observadores=[{"usuario_id": "u1", "nome": "F", "email": "f@b.com"}],
    )
    c.salvar()
    chamado_id = c.id

    c.deletar()

    with models_db_module.SessionLocal() as session:
        participantes_restantes = (
            session.query(ChamadoParticipanteRow).filter_by(chamado_id=chamado_id).all()
        )
        observadores_restantes = (
            session.query(ChamadoObservadorRow).filter_by(chamado_id=chamado_id).all()
        )
    assert participantes_restantes == []
    assert observadores_restantes == []


def _chamado_get_by_id(chamado_id):
    from app.models import Chamado

    return Chamado.get_by_id(chamado_id)
