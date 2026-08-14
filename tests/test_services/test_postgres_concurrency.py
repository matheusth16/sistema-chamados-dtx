"""Regressões de concorrência com transações PostgreSQL reais.

Cada worker usa uma sessão/conexão física própria. Os seeds são commitados
fora do savepoint de ``db_session`` e removidos explicitamente ao final.
"""

import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import select, text
from sqlalchemy.orm import scoped_session, sessionmaker

from app.db.models.chamado import ChamadoPrevisaoSolicitacaoRow, ChamadoRow


def _factory_real(db_engine):
    return scoped_session(sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False))


def _seed_chamado(factory, marcador: str, **overrides) -> int:
    dados = {
        "numero_chamado": marcador,
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Teste concorrente",
        "responsavel": None,
        "responsavel_id": None,
        "solicitante_id": "sol-concorrente",
        "solicitante_nome": "Solicitante",
        "area": "Engenharia",
        "status": "Aberto",
        "impacto": [],
        "anexos": [],
        "setores_adicionais": [],
        "supervisor_ids_com_acesso": [],
    }
    dados.update(overrides)
    with factory() as session, session.begin():
        row = ChamadoRow(**dados)
        session.add(row)
        session.flush()
        chamado_id = row.id
    factory.remove()
    return chamado_id


def _cleanup_chamado(db_engine, chamado_id: int) -> None:
    with db_engine.connect() as conn:
        conn.execute(text("DELETE FROM chamados WHERE id = :id"), {"id": chamado_id})
        conn.commit()


def test_claim_concorrente_apenas_um_supervisor_vence(db_engine, monkeypatch, app):
    from app.models import Chamado
    from app.services import status_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    chamado_id = _seed_chamado(factory, "CONC-CLAIM-1")

    barreira = threading.Barrier(2)
    original_get = Chamado.get_by_id

    def _get_sincronizado(cid):
        chamado = original_get(cid)
        barreira.wait(timeout=5)
        return chamado

    resultados = []
    lock = threading.Lock()

    def _claim(uid, nome):
        try:
            with app.app_context():
                resultado = status_service.atualizar_status_chamado(
                    chamado_id=chamado_id,
                    novo_status="Em Atendimento",
                    usuario_id=uid,
                    usuario_nome=nome,
                )
            with lock:
                resultados.append(resultado)
        finally:
            factory.remove()

    try:
        with (
            patch.object(Chamado, "get_by_id", side_effect=_get_sincronizado),
            patch.object(status_service, "Historico"),
            patch.object(status_service, "_notificar_solicitante"),
            patch.object(status_service, "_notificar_observadores_status"),
            patch.object(status_service, "GamificationService"),
        ):
            threads = [
                threading.Thread(target=_claim, args=("sup-a", "Supervisor A")),
                threading.Thread(target=_claim, args=("sup-b", "Supervisor B")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(resultados) == 2
        assert sum(r["sucesso"] is True for r in resultados) == 1
        conflito = next(r for r in resultados if not r["sucesso"])
        assert conflito["codigo"] == 409

        with factory() as session:
            owner = session.execute(
                select(ChamadoRow.responsavel_id).where(ChamadoRow.id == chamado_id)
            ).scalar_one()
        factory.remove()
        assert owner in {"sup-a", "sup-b"}
    finally:
        _cleanup_chamado(db_engine, chamado_id)


def test_transferencias_concorrentes_revalidam_owner(db_engine, monkeypatch, app):
    from app.models import Chamado
    from app.services import escalonamento_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    chamado_id = _seed_chamado(
        factory,
        "CONC-TRANSFER-1",
        responsavel_id="sup-origem",
        responsavel="Supervisor Origem",
        status="Em Atendimento",
    )

    owner = MagicMock(
        id="sup-origem",
        nome="Supervisor Origem",
        is_admin_or_above=False,
    )
    destinos = {
        "Area A": MagicMock(id="sup-a", nome="Supervisor A"),
        "Area B": MagicMock(id="sup-b", nome="Supervisor B"),
    }
    barreira_inicio = threading.Barrier(2)
    barreira_update = threading.Barrier(2)
    original_update = Chamado.atualizar_campos
    resultados = []
    lock = threading.Lock()

    def _update_sincronizado(self, **kwargs):
        barreira_update.wait(timeout=5)
        return original_update(self, **kwargs)

    def _transferir(area, supervisor_id):
        try:
            barreira_inicio.wait(timeout=5)
            with app.app_context():
                resultado = escalonamento_service.transferir_area(
                    chamado_id,
                    area,
                    supervisor_id,
                    "Transferência concorrente",
                    owner,
                )
            with lock:
                resultados.append(resultado)
        finally:
            factory.remove()

    try:
        with (
            patch.object(Chamado, "atualizar_campos", _update_sincronizado),
            patch.object(
                escalonamento_service.Usuario,
                "get_supervisores_por_area",
                side_effect=lambda area: [destinos[area]],
            ),
            patch.object(escalonamento_service, "Historico"),
        ):
            threads = [
                threading.Thread(target=_transferir, args=("Area A", "sup-a")),
                threading.Thread(target=_transferir, args=("Area B", "sup-b")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(resultados) == 2
        assert sum(r["sucesso"] is True for r in resultados) == 1
        assert sum(r["sucesso"] is False for r in resultados) == 1
    finally:
        _cleanup_chamado(db_engine, chamado_id)


def test_anexos_concorrentes_preservam_todos_os_arquivos(db_engine, monkeypatch, app):
    from app.models import Chamado
    from app.services import solicitante_edicao_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    chamado_id = _seed_chamado(factory, "CONC-ANEXO-1")
    usuario = MagicMock(id="sol-concorrente", nome="Solicitante")

    barreira = threading.Barrier(2)
    original_get = Chamado.get_by_id
    resultados = []
    lock = threading.Lock()

    def _get_sincronizado(cid):
        chamado = original_get(cid)
        barreira.wait(timeout=5)
        return chamado

    def _adicionar(caminho):
        try:
            with app.app_context():
                resultado = solicitante_edicao_service.adicionar_anexo_tardio(
                    chamado_id,
                    caminho,
                    "Documento adicional concorrente",
                    usuario,
                )
            with lock:
                resultados.append(resultado)
        finally:
            factory.remove()

    try:
        with (
            patch.object(Chamado, "get_by_id", side_effect=_get_sincronizado),
            patch.object(solicitante_edicao_service, "Historico"),
            patch.object(solicitante_edicao_service, "_notificar_anexo_tardio"),
        ):
            threads = [
                threading.Thread(target=_adicionar, args=("anexos/a.pdf",)),
                threading.Thread(target=_adicionar, args=("anexos/b.pdf",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(resultados) == 2
        assert all(r["sucesso"] for r in resultados)
        with factory() as session:
            anexos = session.execute(
                select(ChamadoRow.anexos).where(ChamadoRow.id == chamado_id)
            ).scalar_one()
        factory.remove()
        assert set(anexos) == {"anexos/a.pdf", "anexos/b.pdf"}
    finally:
        _cleanup_chamado(db_engine, chamado_id)


def test_cancelamento_concorrente_apenas_um_request_vence(db_engine, monkeypatch, app):
    from app.models import Chamado
    from app.services import cancelamento_solicitante_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    chamado_id = _seed_chamado(factory, "CONC-CANCEL-1")
    usuario = MagicMock(id="sol-concorrente", nome="Solicitante")

    barreira = threading.Barrier(2)
    original_get = Chamado.get_by_id
    resultados = []
    lock = threading.Lock()

    def _get_sincronizado(cid):
        chamado = original_get(cid)
        barreira.wait(timeout=5)
        return chamado

    def _cancelar():
        try:
            with app.app_context():
                resultado = cancelamento_solicitante_service.cancelar_chamado_solicitante(
                    chamado_id,
                    "Cancelamento concorrente válido",
                    usuario,
                )
            with lock:
                resultados.append(resultado)
        finally:
            factory.remove()

    try:
        with (
            patch.object(Chamado, "get_by_id", side_effect=_get_sincronizado),
            patch.object(cancelamento_solicitante_service, "Historico"),
            patch.object(cancelamento_solicitante_service, "_notificar_cancelamento"),
        ):
            threads = [threading.Thread(target=_cancelar) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(resultados) == 2
        assert sum(r["sucesso"] is True for r in resultados) == 1
        assert next(r for r in resultados if not r["sucesso"])["codigo"] == 409
    finally:
        _cleanup_chamado(db_engine, chamado_id)


def test_confirmacao_concorrente_nao_duplica_decisao(db_engine, monkeypatch, app):
    from app.models import Chamado
    from app.services import confirmacao_solicitante_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    chamado_id = _seed_chamado(
        factory,
        "CONC-CONFIRMA-1",
        status="Concluído",
        confirmacao_solicitante="pendente",
    )
    usuario = MagicMock(id="sol-concorrente", nome="Solicitante")

    barreira = threading.Barrier(2)
    original_get = Chamado.get_by_id
    resultados = []
    lock = threading.Lock()

    def _get_sincronizado(cid):
        chamado = original_get(cid)
        barreira.wait(timeout=5)
        return chamado

    def _confirmar():
        try:
            with app.app_context():
                resultado = confirmacao_solicitante_service.processar_confirmacao_solicitante(
                    chamado_id,
                    acao="confirmar",
                    motivo="",
                    usuario=usuario,
                    limite_reaberturas=3,
                )
            with lock:
                resultados.append(resultado)
        finally:
            factory.remove()

    try:
        with (
            patch.object(Chamado, "get_by_id", side_effect=_get_sincronizado),
            patch.object(confirmacao_solicitante_service, "Historico") as historico,
        ):
            threads = [threading.Thread(target=_confirmar) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(resultados) == 2
        assert sum(r["sucesso"] is True for r in resultados) == 1
        assert next(r for r in resultados if not r["sucesso"])["codigo"] == 409
        assert historico.call_count == 1
    finally:
        _cleanup_chamado(db_engine, chamado_id)


def test_sla_concorrente_notifica_apenas_winner(db_engine, monkeypatch, app):
    from app.services import sla_escalacao_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    chamado_id = _seed_chamado(
        factory,
        "CONC-SLA-1",
        categoria="AOG",
        data_abertura=datetime.now(UTC) - timedelta(hours=3),
        escalacao_nivel=0,
    )
    barreira = threading.Barrier(2)
    notificacoes = []
    lock = threading.Lock()

    def _processar():
        try:
            with factory() as session:
                row = session.get(ChamadoRow, chamado_id)
                session.expunge(row)
            factory.remove()
            barreira.wait(timeout=5)
            stats = {
                "escalados": 0,
                "emails": 0,
                "pre_avisos": 0,
                "adiados": 0,
                "pulados_fora_janela": 0,
            }
            with app.app_context():
                sla_escalacao_service._processar_chamado_escalonamento(
                    row,
                    datetime.now(UTC),
                    stats,
                    {"AOG": "gestor@test.com"},
                    {},
                )
        finally:
            factory.remove()

    def _notificar(**kwargs):
        with lock:
            notificacoes.append(kwargs)

    try:
        with (
            patch.object(
                sla_escalacao_service,
                "_resolver_email_gestor",
                return_value="gestor@test.com",
            ),
            patch.object(
                sla_escalacao_service,
                "notificar_escalada_gerencial",
                side_effect=_notificar,
            ),
            patch.object(sla_escalacao_service, "Historico"),
        ):
            threads = [threading.Thread(target=_processar) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(notificacoes) == 1
        with factory() as session:
            nivel = session.execute(
                select(ChamadoRow.escalacao_nivel).where(ChamadoRow.id == chamado_id)
            ).scalar_one()
        factory.remove()
        assert nivel == 1
    finally:
        _cleanup_chamado(db_engine, chamado_id)


def test_lembrete_concorrente_envia_um_email(db_engine, monkeypatch, app):
    from app.services import lembrete_confirmacao_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    agora = datetime.now(UTC)
    chamado_id = _seed_chamado(
        factory,
        "CONC-LEMBRETE-1",
        status="Concluído",
        confirmacao_solicitante="pendente",
        data_conclusao=agora - timedelta(hours=30),
        lembrete_confirmacao_1_enviado=False,
    )
    barreira = threading.Barrier(2)
    envios = []
    lock = threading.Lock()

    def _processar():
        try:
            with factory() as session:
                row = session.get(ChamadoRow, chamado_id)
                session.expunge(row)
            factory.remove()
            barreira.wait(timeout=5)
            stats = {"lembrete_1": 0, "lembrete_2": 0}
            with app.app_context():
                lembrete_confirmacao_service._processar_chamado(row, agora, stats)
        finally:
            factory.remove()

    def _enviar(**kwargs):
        with lock:
            envios.append(kwargs)
        return True

    try:
        with (
            patch.object(
                lembrete_confirmacao_service,
                "notificar_solicitante_lembrete_confirmacao",
                side_effect=_enviar,
            ),
            patch.object(
                lembrete_confirmacao_service.Usuario, "get_by_id", return_value=MagicMock()
            ),
            patch.object(lembrete_confirmacao_service, "Historico"),
            patch.object(lembrete_confirmacao_service, "_criar_inapp_lembrete"),
        ):
            threads = [threading.Thread(target=_processar) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(envios) == 1
    finally:
        _cleanup_chamado(db_engine, chamado_id)


def test_previsao_concorrente_tem_decisao_unica(db_engine, monkeypatch, app):
    from app.services import previsao_atendimento_service

    factory = _factory_real(db_engine)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    chamado_id = _seed_chamado(factory, "CONC-PREVISAO-1")
    with factory() as session, session.begin():
        pedido = ChamadoPrevisaoSolicitacaoRow(
            chamado_id=chamado_id,
            solicitante_id="sup-origem",
            solicitante_nome="Supervisor",
            previsao_solicitada=datetime.now(UTC) + timedelta(days=5),
            motivo="Previsão concorrente",
            status="pendente",
        )
        session.add(pedido)
        session.flush()
        solicitacao_id = pedido.id
    factory.remove()

    gestor = MagicMock(
        id="admin-previsao",
        nome="Admin",
        ativo=True,
        is_admin_or_above=True,
    )
    barreira = threading.Barrier(2)
    resultados = []
    lock = threading.Lock()

    def _decidir(acao):
        try:
            barreira.wait(timeout=5)
            with app.app_context():
                resultado = previsao_atendimento_service.decidir_previsao_atendimento(
                    solicitacao_id,
                    acao,
                    gestor,
                )
            with lock:
                resultados.append(resultado)
        finally:
            factory.remove()

    try:
        with patch.object(previsao_atendimento_service, "Historico"):
            threads = [
                threading.Thread(target=_decidir, args=("aprovar",)),
                threading.Thread(target=_decidir, args=("rejeitar",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert len(resultados) == 2
        assert sum(r["sucesso"] is True for r in resultados) == 1
        assert next(r for r in resultados if not r["sucesso"])["codigo"] == 409
    finally:
        _cleanup_chamado(db_engine, chamado_id)
