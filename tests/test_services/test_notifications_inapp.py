"""
Testes do serviço de notificações in-app (notifications_inapp.py), Fase 2 —
Marco 8: persistência roda contra Postgres real (db_session), não mock de
Firestore. Cobre: criar_notificacao, listar_para_usuario, contar_nao_lidas,
marcar_como_lida, marcar_todas_como_lidas, localizar_notificacao e os
helpers de texto (funções puras, sem I/O).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.db.models.notificacao import NotificacaoRow
from tests.factories import make_chamado

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_notificacao_row(db_session, *, chamado=None, data_criacao=None, **overrides):
    """Insere uma NotificacaoRow diretamente (sem passar pelo serviço), pra
    controlar timestamp/estado inicial nos testes de ordenação e filtro."""
    if chamado is None:
        chamado = make_chamado()
    defaults = {
        "usuario_id": "u1",
        "chamado_id": chamado.id,
        "numero_chamado": chamado.numero_chamado,
        "titulo": "Título",
        "mensagem": "Mensagem",
        "tipo": "novo_chamado",
        "lida": False,
    }
    defaults.update(overrides)
    row = NotificacaoRow(**defaults)
    if data_criacao is not None:
        row.data_criacao = data_criacao
    db_session.add(row)
    db_session.commit()
    return row


# ── criar_notificacao ──────────────────────────────────────────────────────────


def test_criar_notificacao_persiste_e_retorna_id():
    """criar_notificacao insere a linha e retorna o id gerado."""
    from app.services.notifications_inapp import criar_notificacao

    chamado = make_chamado()
    result = criar_notificacao(
        "user1", chamado.id, chamado.numero_chamado, "Novo chamado", "Descrição", "novo_chamado"
    )

    assert isinstance(result, int)


def test_criar_notificacao_retorna_none_sem_chamado_id():
    """criar_notificacao retorna None quando chamado_id é vazio."""
    from app.services.notifications_inapp import criar_notificacao

    result = criar_notificacao("user1", "", "CHM-001", "Título", "Msg")
    assert result is None


def test_criar_notificacao_retorna_none_com_chamado_id_nao_numerico():
    """criar_notificacao retorna None quando chamado_id não é conversível a int."""
    from app.services.notifications_inapp import criar_notificacao

    result = criar_notificacao("user1", "nao-numerico", "CHM-001", "Título", "Msg")
    assert result is None


def test_criar_notificacao_retorna_none_quando_chamado_nao_existe():
    """criar_notificacao retorna None quando chamado_id referencia um chamado inexistente (FK)."""
    from app.services.notifications_inapp import criar_notificacao

    result = criar_notificacao("user1", 999999999, "CHM-001", "Título", "Msg")
    assert result is None


def test_criar_notificacao_retorna_none_quando_banco_falha(monkeypatch):
    """criar_notificacao captura exceção do banco e retorna None."""
    from app.services import notifications_inapp

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(notifications_inapp.db_module, "SessionLocal", _explode)

    chamado_id_qualquer = 1
    result = notifications_inapp.criar_notificacao(
        "user1", chamado_id_qualquer, "CHM-001", "Título", "Msg"
    )
    assert result is None


def test_criar_notificacao_inclui_categoria_e_solicitante_nome():
    """categoria/solicitante_nome informados são persistidos no registro."""
    from app.services.notifications_inapp import criar_notificacao, db_module

    chamado = make_chamado()
    notificacao_id = criar_notificacao(
        usuario_id="u1",
        chamado_id=chamado.id,
        numero_chamado="CHM-0300",
        titulo="Título",
        mensagem="Mensagem",
        categoria="TI",
        solicitante_nome="Fulano",
    )

    row = db_module.SessionLocal().get(NotificacaoRow, notificacao_id)
    assert row.categoria == "TI"
    assert row.solicitante_nome == "Fulano"


def test_criar_notificacao_sem_categoria_grava_none():
    """categoria/solicitante_nome não informados gravam NULL, não string vazia."""
    from app.services.notifications_inapp import criar_notificacao, db_module

    chamado = make_chamado()
    notificacao_id = criar_notificacao(
        usuario_id="u1",
        chamado_id=chamado.id,
        numero_chamado="CHM-0301",
        titulo="Título",
        mensagem="Mensagem",
    )

    row = db_module.SessionLocal().get(NotificacaoRow, notificacao_id)
    assert row.categoria is None
    assert row.solicitante_nome is None


# ── listar_para_usuario ────────────────────────────────────────────────────────


def test_listar_para_usuario_retorna_mais_recente_primeiro(db_session):
    """listar_para_usuario ordena por data_criacao decrescente."""
    from app.services.notifications_inapp import listar_para_usuario

    chamado = make_chamado()
    agora = datetime.now(UTC)
    mais_antiga = _criar_notificacao_row(
        db_session, chamado=chamado, titulo="Notif 1", data_criacao=agora - timedelta(minutes=5)
    )
    mais_recente = _criar_notificacao_row(
        db_session, chamado=chamado, titulo="Notif 2", data_criacao=agora
    )

    result = listar_para_usuario("u1")

    assert [n["id"] for n in result] == [mais_recente.id, mais_antiga.id]


def test_listar_para_usuario_apenas_nao_lidas(db_session):
    """apenas_nao_lidas=True filtra as já lidas."""
    from app.services.notifications_inapp import listar_para_usuario

    chamado = make_chamado()
    _criar_notificacao_row(db_session, chamado=chamado, lida=True)
    nao_lida = _criar_notificacao_row(db_session, chamado=chamado, lida=False)

    result = listar_para_usuario("u1", apenas_nao_lidas=True)

    assert len(result) == 1
    assert result[0]["id"] == nao_lida.id


def test_listar_para_usuario_respeita_limite(db_session):
    """limite corta a quantidade de resultados."""
    from app.services.notifications_inapp import listar_para_usuario

    chamado = make_chamado()
    for _ in range(3):
        _criar_notificacao_row(db_session, chamado=chamado)

    result = listar_para_usuario("u1", limite=2)

    assert len(result) == 2


def test_listar_para_usuario_nao_mistura_outros_usuarios(db_session):
    """listar_para_usuario só retorna notificações do usuario_id pedido."""
    from app.services.notifications_inapp import listar_para_usuario

    chamado = make_chamado()
    _criar_notificacao_row(db_session, chamado=chamado, usuario_id="outro_usuario")
    minha = _criar_notificacao_row(db_session, chamado=chamado, usuario_id="u1")

    result = listar_para_usuario("u1")

    assert len(result) == 1
    assert result[0]["id"] == minha.id


def test_listar_para_usuario_serializa_data_isoformat(db_session):
    """listar_para_usuario serializa data_criacao datetime para string ISO."""
    from app.services.notifications_inapp import listar_para_usuario

    _criar_notificacao_row(db_session)

    result = listar_para_usuario("u1")

    assert isinstance(result[0]["data_criacao"], str)
    assert "T" in result[0]["data_criacao"]


def test_listar_para_usuario_retorna_vazio_quando_banco_falha(monkeypatch):
    """listar_para_usuario captura exceção do banco e retorna []."""
    from app.services import notifications_inapp

    def _explode():
        raise RuntimeError("timeout")

    monkeypatch.setattr(notifications_inapp.db_module, "SessionLocal", _explode)

    assert notifications_inapp.listar_para_usuario("u1") == []


def test_listar_para_usuario_sem_usuario_id_retorna_vazio():
    from app.services.notifications_inapp import listar_para_usuario

    assert listar_para_usuario("") == []


def test_listar_para_usuario_com_language_localiza_resultado(db_session):
    """language informado aplica localizar_notificacao em cada item retornado."""
    from app.services.notifications_inapp import listar_para_usuario

    chamado = make_chamado()
    _criar_notificacao_row(
        db_session,
        chamado=chamado,
        tipo="status_em_atendimento",
        numero_chamado="CHM-0400",
        categoria="TI",
        titulo="título original",
        mensagem="mensagem original",
    )

    result = listar_para_usuario("u1", language="en")

    assert len(result) == 1
    assert result[0]["titulo"] != "título original"


# ── contar_nao_lidas ───────────────────────────────────────────────────────────


def test_contar_nao_lidas_conta_apenas_do_usuario(db_session):
    """contar_nao_lidas soma só as não lidas do usuário pedido."""
    from app.services.notifications_inapp import contar_nao_lidas

    chamado = make_chamado()
    _criar_notificacao_row(db_session, chamado=chamado, lida=False)
    _criar_notificacao_row(db_session, chamado=chamado, lida=False)
    _criar_notificacao_row(db_session, chamado=chamado, lida=True)
    _criar_notificacao_row(db_session, chamado=chamado, usuario_id="outro", lida=False)

    assert contar_nao_lidas("u1") == 2


def test_contar_nao_lidas_retorna_zero_quando_banco_falha(monkeypatch):
    """contar_nao_lidas captura exceção do banco e retorna 0."""
    from app.services import notifications_inapp

    def _explode():
        raise RuntimeError("err")

    monkeypatch.setattr(notifications_inapp.db_module, "SessionLocal", _explode)

    assert notifications_inapp.contar_nao_lidas("u1") == 0


def test_contar_nao_lidas_sem_usuario_id_retorna_zero():
    from app.services.notifications_inapp import contar_nao_lidas

    assert contar_nao_lidas("") == 0


# ── marcar_como_lida ───────────────────────────────────────────────────────────


def test_marcar_como_lida_retorna_true_quando_pertence_ao_usuario(db_session):
    """marcar_como_lida marca lida=True e retorna True quando a notificação é do usuário."""
    from app.services.notifications_inapp import marcar_como_lida

    notif = _criar_notificacao_row(db_session, usuario_id="u1", lida=False)

    result = marcar_como_lida(notif.id, "u1")

    assert result is True
    assert db_session.get(NotificacaoRow, notif.id).lida is True


def test_marcar_como_lida_retorna_false_quando_nao_existe():
    """marcar_como_lida retorna False quando o id não existe."""
    from app.services.notifications_inapp import marcar_como_lida

    assert marcar_como_lida(999999999, "u1") is False


def test_marcar_como_lida_retorna_false_quando_pertence_a_outro_usuario(db_session):
    """marcar_como_lida retorna False (e não altera) quando a notificação é de outro usuário."""
    from app.services.notifications_inapp import marcar_como_lida

    notif = _criar_notificacao_row(db_session, usuario_id="outro_usuario", lida=False)

    result = marcar_como_lida(notif.id, "u1")

    assert result is False
    assert db_session.get(NotificacaoRow, notif.id).lida is False


def test_marcar_como_lida_retorna_false_com_id_nao_numerico():
    """marcar_como_lida retorna False quando notificacao_id não é conversível a int."""
    from app.services.notifications_inapp import marcar_como_lida

    assert marcar_como_lida("nao-numerico", "u1") is False


def test_marcar_como_lida_retorna_false_quando_banco_falha(monkeypatch):
    """marcar_como_lida captura exceção do banco e retorna False."""
    from app.services import notifications_inapp

    def _explode():
        raise RuntimeError("err")

    monkeypatch.setattr(notifications_inapp.db_module, "SessionLocal", _explode)

    assert notifications_inapp.marcar_como_lida(1, "u1") is False


def test_marcar_como_lida_sem_ids_retorna_false():
    from app.services.notifications_inapp import marcar_como_lida

    assert marcar_como_lida("", "u1") is False
    assert marcar_como_lida("n1", "") is False


# ── marcar_todas_como_lidas ────────────────────────────────────────────────────


def test_marcar_todas_como_lidas_retorna_contagem_e_atualiza(db_session):
    """marcar_todas_como_lidas marca todas as não lidas do usuário e retorna a contagem."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    chamado = make_chamado()
    n1 = _criar_notificacao_row(db_session, chamado=chamado, lida=False)
    n2 = _criar_notificacao_row(db_session, chamado=chamado, lida=False)
    _criar_notificacao_row(db_session, chamado=chamado, usuario_id="outro", lida=False)

    result = marcar_todas_como_lidas("u1")

    assert result == 2
    assert db_session.get(NotificacaoRow, n1.id).lida is True
    assert db_session.get(NotificacaoRow, n2.id).lida is True


def test_marcar_todas_como_lidas_retorna_zero_sem_notificacoes():
    from app.services.notifications_inapp import marcar_todas_como_lidas

    assert marcar_todas_como_lidas("u1") == 0


def test_marcar_todas_como_lidas_retorna_zero_quando_banco_falha(monkeypatch):
    """marcar_todas_como_lidas captura exceção do banco e retorna 0."""
    from app.services import notifications_inapp

    def _explode():
        raise RuntimeError("err")

    monkeypatch.setattr(notifications_inapp.db_module, "SessionLocal", _explode)

    assert notifications_inapp.marcar_todas_como_lidas("u1") == 0


def test_marcar_todas_sem_usuario_id_retorna_zero():
    from app.services.notifications_inapp import marcar_todas_como_lidas

    assert marcar_todas_como_lidas("") == 0


# ── localizar_notificacao ──────────────────────────────────────────────────────


def test_localizar_notificacao_novo_chamado_em_ingles():
    """Notificação com metadados completos deve ser traduzida para EN."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "novo_chamado",
        "numero_chamado": "CHM-0006",
        "categoria": "Nao Aplicavel",
        "solicitante_nome": "Matheus Costa",
        "titulo": "Novo chamado: CHM-0006",
        "mensagem": "Nao Aplicavel · Solicitante: Matheus Costa",
    }
    out = localizar_notificacao(doc, "en")
    assert out["titulo"] == "New ticket: CHM-0006"
    assert out["mensagem"] == "Routine · Requester: Matheus Costa"


def test_localizar_notificacao_novo_chamado_em_pt():
    """Notificação com metadados completos em PT deve manter strings PT."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "novo_chamado",
        "numero_chamado": "CHM-0006",
        "categoria": "Nao Aplicavel",
        "solicitante_nome": "Matheus Costa",
        "titulo": "Novo chamado: CHM-0006",
        "mensagem": "Nao Aplicavel · Solicitante: Matheus Costa",
    }
    out = localizar_notificacao(doc, "pt_BR")
    assert out["titulo"] == "Novo chamado: CHM-0006"
    assert "Solicitante: Matheus Costa" in out["mensagem"]


def test_localizar_notificacao_legacy_sem_metadados():
    """Notificações antigas sem campos categoria/solicitante_nome devem usar fallback parser."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "novo_chamado",
        "numero_chamado": "CHM-0005",
        "titulo": "Novo chamado: CHM-0005",
        "mensagem": "Nao Aplicavel · Solicitante: Matheus Costa",
    }
    out = localizar_notificacao(doc, "en")
    assert "New ticket" in out["titulo"]
    assert "Requester" in out["mensagem"]
    assert "Routine" in out["mensagem"]


def test_localizar_notificacao_tipo_desconhecido_nao_altera():
    """Tipos que não sejam novo_chamado devem retornar doc sem modificações."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "outro_tipo",
        "titulo": "Algum título",
        "mensagem": "Alguma mensagem",
    }
    out = localizar_notificacao(doc, "en")
    assert out["titulo"] == "Algum título"
    assert out["mensagem"] == "Alguma mensagem"


# ── Novos tipos — solicitante ──────────────────────────────────────────────────


def test_localizar_status_em_atendimento_en():
    """localizar_notificacao traduz tipo status_em_atendimento para EN."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "status_em_atendimento",
        "numero_chamado": "CHM-010",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "CHM-010" in out["titulo"]
    assert "in progress" in out["titulo"].lower()
    assert "being handled" in out["mensagem"].lower()


def test_localizar_status_em_atendimento_pt():
    """localizar_notificacao traduz tipo status_em_atendimento para pt_BR."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "status_em_atendimento",
        "numero_chamado": "CHM-010",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "pt_BR")
    assert "CHM-010" in out["titulo"]
    assert "atendimento" in out["titulo"].lower()


def test_localizar_status_concluido_confirmar_en():
    """localizar_notificacao traduz tipo status_concluido_confirmar para EN."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "status_concluido_confirmar",
        "numero_chamado": "CHM-020",
        "categoria": "Manutencao",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "CHM-020" in out["titulo"]
    assert "completed" in out["titulo"].lower()
    assert "confirm" in out["mensagem"].lower()


def test_localizar_lembrete_confirmacao_1_en():
    """localizar_notificacao traduz tipo lembrete_confirmacao_1 para EN com n=1."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "lembrete_confirmacao_1",
        "numero_chamado": "CHM-030",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "1" in out["titulo"]
    assert "reminder" in out["titulo"].lower()
    assert "CHM-030" in out["titulo"]
    assert "confirmation" in out["mensagem"].lower()


def test_localizar_lembrete_confirmacao_2_en():
    """localizar_notificacao traduz tipo lembrete_confirmacao_2 para EN com n=2."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "lembrete_confirmacao_2",
        "numero_chamado": "CHM-031",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "2" in out["titulo"]
    assert "reminder" in out["titulo"].lower()


def test_localizar_lembrete_confirmacao_1_pt():
    """localizar_notificacao traduz tipo lembrete_confirmacao_1 para pt_BR."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "lembrete_confirmacao_1",
        "numero_chamado": "CHM-032",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "pt_BR")
    assert "Lembrete" in out["titulo"]
    assert "1" in out["titulo"]


# ── texto_notificacao_status_solicitante ───────────────────────────────────────


def test_texto_status_solicitante_em_atendimento_en():
    """texto_notificacao_status_solicitante retorna título e msg EN para em_atendimento."""
    from app.services.notifications_inapp import texto_notificacao_status_solicitante

    titulo, mensagem = texto_notificacao_status_solicitante(
        numero="CHM-099", categoria="TI", tipo_evento="status_em_atendimento", language="en"
    )
    assert "CHM-099" in titulo
    assert "in progress" in titulo.lower()
    assert "being handled" in mensagem.lower()


def test_texto_status_solicitante_concluido_confirmar_pt():
    """texto_notificacao_status_solicitante retorna título e msg pt_BR para concluido_confirmar."""
    from app.services.notifications_inapp import texto_notificacao_status_solicitante

    titulo, mensagem = texto_notificacao_status_solicitante(
        numero="CHM-099",
        categoria="TI",
        tipo_evento="status_concluido_confirmar",
        language="pt_BR",
    )
    assert "concluído" in titulo.lower()
    assert "confirme" in titulo.lower() or "confirmação" in mensagem.lower()


def test_texto_status_solicitante_lembrete_en():
    """texto_notificacao_status_solicitante retorna texto correto para lembrete #2."""
    from app.services.notifications_inapp import texto_notificacao_status_solicitante

    titulo, mensagem = texto_notificacao_status_solicitante(
        numero="CHM-099",
        categoria="TI",
        tipo_evento="lembrete_confirmacao",
        language="en",
        numero_lembrete=2,
    )
    assert "2" in titulo
    assert "reminder" in titulo.lower()
    assert "confirmation" in mensagem.lower()


# ── criar_notificacao_solicitante ──────────────────────────────────────────────


def test_criar_notificacao_solicitante_chama_criar_notificacao():
    """criar_notificacao_solicitante delega para criar_notificacao com dados corretos."""
    from app.services.notifications_inapp import criar_notificacao_solicitante

    with patch("app.services.notifications_inapp.criar_notificacao") as mock_criar:
        mock_criar.return_value = 42
        result = criar_notificacao_solicitante(
            solicitante_id="sol1",
            chamado_id="ch1",
            numero_chamado="CHM-001",
            categoria="TI",
            tipo="status_em_atendimento",
            language="en",
        )

    assert result == 42
    mock_criar.assert_called_once()
    call_kwargs = mock_criar.call_args
    assert call_kwargs.kwargs["tipo"] == "status_em_atendimento"
    assert call_kwargs.kwargs["usuario_id"] == "sol1"


def test_criar_notificacao_solicitante_lembrete_1_usa_tipo_correto():
    """criar_notificacao_solicitante usa tipo 'lembrete_confirmacao_1'."""
    from app.services.notifications_inapp import criar_notificacao_solicitante

    with patch("app.services.notifications_inapp.criar_notificacao") as mock_criar:
        mock_criar.return_value = 43
        criar_notificacao_solicitante(
            solicitante_id="sol1",
            chamado_id="ch1",
            numero_chamado="CHM-001",
            categoria="TI",
            tipo="lembrete_confirmacao_1",
            language="en",
        )

    call_kwargs = mock_criar.call_args
    assert call_kwargs.kwargs["tipo"] == "lembrete_confirmacao_1"


def test_criar_notificacao_solicitante_retorna_none_sem_ids():
    """criar_notificacao_solicitante retorna None quando solicitante_id vazio."""
    from app.services.notifications_inapp import criar_notificacao_solicitante

    result = criar_notificacao_solicitante(
        solicitante_id="",
        chamado_id="ch1",
        numero_chamado="CHM-001",
        categoria="TI",
        tipo="status_em_atendimento",
    )
    assert result is None


# ── localizar_notificacao — tipos observador ─────────────────────────────────


def _doc_observador(tipo: str) -> dict:
    return {
        "tipo": tipo,
        "numero_chamado": "CHM-0100",
        "categoria": "TI",
        "titulo": "título original",
        "mensagem": "mensagem original",
    }


def test_localizar_observador_edicao_descricao_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    out = localizar_notificacao(_doc_observador("observador_edicao_descricao"), "en")
    assert "CHM-0100" in out["titulo"]
    assert out["titulo"] != "título original"
    assert out["mensagem"] != "mensagem original"


def test_localizar_observador_anexo_tardio_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    out = localizar_notificacao(_doc_observador("observador_anexo_tardio"), "en")
    assert "CHM-0100" in out["titulo"]
    assert out["mensagem"] != "mensagem original"


def test_localizar_observador_cancelamento_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    out = localizar_notificacao(_doc_observador("observador_cancelamento"), "en")
    assert "CHM-0100" in out["titulo"]
    assert out["mensagem"] != "mensagem original"


def test_localizar_observador_status_em_atendimento_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    out = localizar_notificacao(_doc_observador("observador_status_em_atendimento"), "en")
    assert "CHM-0100" in out["titulo"]
    assert out["mensagem"] != "mensagem original"


def test_localizar_observador_status_concluido_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    out = localizar_notificacao(_doc_observador("observador_status_concluido"), "en")
    assert "CHM-0100" in out["titulo"]
    assert out["mensagem"] != "mensagem original"


def test_localizar_observador_incluido_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    out = localizar_notificacao(_doc_observador("observador_incluido"), "en")
    assert "CHM-0100" in out["titulo"]
    assert out["mensagem"] != "mensagem original"


# ── localizar_notificacao — tipos participante ───────────────────────────────


def test_localizar_participante_incluido_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "participante_incluido",
        "numero_chamado": "CHM-0200",
        "categoria": "Qualidade",
        "titulo": "título original",
        "mensagem": "mensagem original",
    }
    out = localizar_notificacao(doc, "en")
    assert "CHM-0200" in out["titulo"]
    assert out["mensagem"] != "mensagem original"


def test_localizar_todos_participantes_concluidos_traduz():
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "todos_participantes_concluidos",
        "numero_chamado": "CHM-0201",
        "categoria": "Qualidade",
        "titulo": "título original",
        "mensagem": "mensagem original",
    }
    out = localizar_notificacao(doc, "en")
    assert "CHM-0201" in out["titulo"]
    assert out["mensagem"] != "mensagem original"


# ── texto_notificacao_novo_chamado ───────────────────────────────────────────


def test_texto_notificacao_novo_chamado_en():
    from app.services.notifications_inapp import texto_notificacao_novo_chamado

    titulo, mensagem = texto_notificacao_novo_chamado(
        numero="CHM-0500", categoria_raw="Nao Aplicavel", solicitante_nome="Fulano", language="en"
    )
    assert "CHM-0500" in titulo
    assert "Fulano" in mensagem
