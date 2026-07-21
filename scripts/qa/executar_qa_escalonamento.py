#!/usr/bin/env python3
"""Playbook QA Onda 6 — Escalonamento e SLA (10 cenários ESC-*).

Uso:
    python scripts/qa/executar_qa_escalonamento.py
    python scripts/qa/executar_qa_escalonamento.py --json > docs/evidencias/qa_escalonamento_resultado.json

Cenários implementados via test client + mocks (sem Firestore real).
ESC-07 e ESC-08 testam business_time diretamente com datetimes fixos.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("FLASK_ENV", "testing")

Status = Literal["PASS", "FAIL", "SKIP"]

_BRT = ZoneInfo("America/Sao_Paulo")


@dataclass
class Resultado:
    id_esc: str
    descricao: str
    status: Status
    detalhe: str


def _usuario_mock(
    uid,
    email,
    nome,
    perfil,
    area="Geral",
    areas=None,
    is_gestor=False,
    is_gestor_only=False,
):
    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = nome
    u.perfil = perfil
    u.area = area
    u.areas = areas if areas is not None else [area]
    u.is_authenticated = True
    u.check_password = MagicMock(return_value=True)
    u.get_id = lambda: str(uid)
    u.must_change_password = False
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.onboarding_completo = True
    u.onboarding_passo = 0
    u.ativo = True
    u.nivel_gestao = "gestor_setor" if is_gestor else None
    u.is_gestor = is_gestor
    u.is_gestor_only = is_gestor_only
    u.mfa_enabled = True
    return u


def _criar_app_testing():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "qa-esc-secret"
    app.config["APP_BASE_URL"] = ""
    return app


def _chamado_dict(
    status="Aberto",
    area="TI",
    responsavel_id=None,
    solicitante_id="sol_1",
    participantes=None,
    supervisor_ids=None,
    data_em_atendimento=None,
    categoria="Suporte",
    descricao="Descrição do chamado",
):
    return {
        "titulo": "Chamado QA ESC",
        "descricao": descricao,
        "status": status,
        "area": area,
        "responsavel_id": responsavel_id,
        "responsavel": "Sup" if responsavel_id else None,
        "solicitante_id": solicitante_id,
        "participantes": participantes or [],
        "supervisor_ids_com_acesso": (
            supervisor_ids
            if supervisor_ids is not None
            else ([responsavel_id] if responsavel_id else [])
        ),
        "data_abertura": datetime.now(_BRT),
        "data_em_atendimento": data_em_atendimento,
        "categoria": categoria,
        "prioridade": "Normal",
        "gate": None,
        "rl_codigo": None,
        "escalacao_resposta_nivel": 0,
        "escalacao_resolucao_nivel": 0,
        "alerta_supervisor_50_enviado": False,
        "alerta_supervisor_80_enviado": False,
        "confirmacao_solicitante": None,
        "grupo_rl_id": None,
        "motivo_ultima_escalacao": None,
        "setores_adicionais": [],
        "sla_dias": None,
        "numero_chamado": "QA-001",
        "tipo_solicitacao": "Suporte",
        "solicitante_nome": "Solicitante Teste",
    }


# ─── ESC-01: Isolamento supervisor ──────────────────────────────────────────


def check_esc_01() -> Resultado:
    """ESC-01: sup_a não vê chamado onde responsavel_id=sup_b."""
    try:
        from app.models import Chamado
        from app.services.permissions import usuario_pode_ver_chamado

        sup_a = _usuario_mock("sup_a", "a@test.com", "Sup A", "supervisor", "TI", areas=["TI"])
        dados = _chamado_dict(responsavel_id="sup_b", area="TI", supervisor_ids=["sup_b"])
        chamado = Chamado.from_dict(dados, "ch_esc01")
        pode = usuario_pode_ver_chamado(sup_a, chamado)
        if not pode:
            return Resultado(
                "ESC-01",
                "Isolamento supervisor: sup_a nao ve chamado de sup_b",
                "PASS",
                "usuario_pode_ver_chamado(sup_a, chamado_sup_b) = False [OK]",
            )
        return Resultado(
            "ESC-01",
            "Isolamento supervisor",
            "FAIL",
            "sup_a conseguiu ver chamado de sup_b — isolamento quebrado",
        )
    except Exception as e:
        return Resultado("ESC-01", "Isolamento supervisor", "FAIL", f"Exceção: {e}")


# ─── ESC-02: Fila da área ───────────────────────────────────────────────────


def check_esc_02() -> Resultado:
    """ESC-02: supervisor vê chamado sem owner na sua área (fila)."""
    try:
        from app.models import Chamado
        from app.services.permissions import usuario_pode_ver_chamado

        sup_a = _usuario_mock("sup_a", "a@test.com", "Sup A", "supervisor", "TI", areas=["TI"])
        dados = _chamado_dict(
            status="Aberto",
            area="TI",
            responsavel_id=None,
            supervisor_ids=["sup_a"],
        )
        chamado = Chamado.from_dict(dados, "ch_esc02")
        with patch("app.models_usuario.Usuario.get_supervisores_por_area", return_value=[sup_a]):
            pode = usuario_pode_ver_chamado(sup_a, chamado)
        if pode:
            return Resultado(
                "ESC-02",
                "Fila da área: supervisor vê chamado sem owner",
                "PASS",
                "usuario_pode_ver_chamado(sup_a, fila_TI) = True [OK]",
            )
        return Resultado(
            "ESC-02",
            "Fila da área",
            "FAIL",
            "supervisor não consegue ver chamado da sua área sem owner",
        )
    except Exception as e:
        return Resultado("ESC-02", "Fila da área", "FAIL", f"Exceção: {e}")


# ─── ESC-03: Claim ──────────────────────────────────────────────────────────


def check_esc_03() -> Resultado:
    """ESC-03: Claim — Em Atendimento sem owner seta responsavel_id = current_user.id."""
    try:
        from app.services.status_service import atualizar_status_chamado

        dados = _chamado_dict(status="Aberto", responsavel_id=None)
        update_payload: dict = {}

        with (
            patch("app.services.status_service.db"),
            patch(
                "app.services.status_service.execute_with_retry",
                side_effect=lambda fn, payload, **kw: update_payload.update(payload),
            ),
            patch("app.services.status_service.Historico"),
            patch("app.services.status_service.GamificationService"),
            patch("app.services.status_service.notificar_solicitante_status"),
            patch("app.services.status_service.notificar_solicitante_confirmacao_pendente"),
        ):
            result = atualizar_status_chamado(
                "ch_esc03",
                "Em Atendimento",
                "sup_a",
                "Supervisor A",
                data_chamado=dados,
            )

        if result.get("sucesso") and update_payload.get("responsavel_id") == "sup_a":
            return Resultado(
                "ESC-03",
                "Claim: responsavel_id = current_user.id",
                "PASS",
                f"responsavel_id={update_payload['responsavel_id']!r} + data_em_atendimento setado [OK]",
            )
        return Resultado(
            "ESC-03",
            "Claim",
            "FAIL",
            f"sucesso={result.get('sucesso')}, responsavel_id={update_payload.get('responsavel_id')!r}, erro={result.get('erro')!r}",
        )
    except Exception as e:
        return Resultado("ESC-03", "Claim", "FAIL", f"Exceção: {e}")


# ─── ESC-04: Transferir área ────────────────────────────────────────────────


def check_esc_04() -> Resultado:
    """ESC-04: transferir_area — ex-owner perde visão; novo owner ganha."""
    try:
        from app.services.escalonamento_service import transferir_area

        sup_orig = _usuario_mock(
            "sup_orig", "orig@test.com", "Sup Origem", "supervisor", "TI", areas=["TI"]
        )
        sup_dest = _usuario_mock(
            "sup_dest",
            "dest@test.com",
            "Sup Destino",
            "supervisor",
            "Manutencao",
            areas=["Manutencao"],
        )

        dados = _chamado_dict(
            area="TI",
            responsavel_id="sup_orig",
            supervisor_ids=["sup_orig"],
        )
        update_payload: dict = {}
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = dados

        with (
            patch("app.services.escalonamento_service.db") as mock_db,
            patch(
                "app.services.escalonamento_service.execute_with_retry",
                side_effect=lambda fn, payload, **kw: update_payload.update(payload),
            ),
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.Usuario.get_supervisores_por_area",
                return_value=[sup_dest],
            ),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = transferir_area(
                "ch_esc04", "Manutencao", "sup_dest", "Motivo de transferência válido", sup_orig
            )

        if not result.get("sucesso"):
            return Resultado(
                "ESC-04", "Transferir área", "FAIL", f"transferir_area falhou: {result.get('erro')}"
            )

        novos_ids = update_payload.get("supervisor_ids_com_acesso", [])
        ex_owner_perde = "sup_orig" not in novos_ids
        novo_owner_ganha = "sup_dest" in novos_ids

        if ex_owner_perde and novo_owner_ganha:
            return Resultado(
                "ESC-04",
                "Transferir área: ex-owner perde visão; novo owner ganha",
                "PASS",
                f"supervisor_ids_com_acesso={novos_ids} (sem sup_orig [OK], com sup_dest [OK])",
            )
        return Resultado(
            "ESC-04",
            "Transferir área",
            "FAIL",
            f"ex_owner_perde={ex_owner_perde}, novo_owner_ganha={novo_owner_ganha}, ids={novos_ids}",
        )
    except Exception as e:
        return Resultado("ESC-04", "Transferir área", "FAIL", f"Exceção: {e}")


# ─── ESC-05: Escalonar colega ───────────────────────────────────────────────


def check_esc_05() -> Resultado:
    """ESC-05: escalonar_colega — motivo obrigatório; troca responsavel_id na mesma área."""
    try:
        from app.services.escalonamento_service import escalonar_colega

        sup_a = _usuario_mock("sup_a", "a@test.com", "Sup A", "supervisor", "TI", areas=["TI"])
        sup_b = _usuario_mock("sup_b", "b@test.com", "Sup B", "supervisor", "TI", areas=["TI"])

        dados = _chamado_dict(area="TI", responsavel_id="sup_a", supervisor_ids=["sup_a"])
        update_payload: dict = {}
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = dados

        # Sub-check A: motivo vazio deve lançar ValueError
        with patch("app.services.escalonamento_service.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            try:
                escalonar_colega("ch_esc05", "sup_b", "   ", sup_a)
                motivo_ok = False
            except ValueError:
                motivo_ok = True

        # Sub-check B: motivo preenchido deve suceder e trocar responsavel_id
        with (
            patch("app.services.escalonamento_service.db") as mock_db2,
            patch(
                "app.services.escalonamento_service.execute_with_retry",
                side_effect=lambda fn, payload, **kw: update_payload.update(payload),
            ),
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.Usuario.get_supervisores_por_area",
                return_value=[sup_b],
            ),
        ):
            mock_db2.collection.return_value.document.return_value.get.return_value = mock_doc
            result = escalonar_colega("ch_esc05", "sup_b", "Colega mais disponível", sup_a)

        novo_resp = update_payload.get("responsavel_id") == "sup_b"
        if motivo_ok and result.get("sucesso") and novo_resp:
            return Resultado(
                "ESC-05",
                "Escalonar colega: motivo obrigatório + troca responsavel_id",
                "PASS",
                f"motivo_vazio_rejeita=True [OK], responsavel_id={update_payload.get('responsavel_id')!r} [OK]",
            )
        return Resultado(
            "ESC-05",
            "Escalonar colega",
            "FAIL",
            f"motivo_ok={motivo_ok}, sucesso={result.get('sucesso')}, novo_resp={novo_resp}",
        )
    except Exception as e:
        return Resultado("ESC-05", "Escalonar colega", "FAIL", f"Exceção: {e}")


# ─── ESC-06: Multi-setor travado ────────────────────────────────────────────


def check_esc_06() -> Resultado:
    """ESC-06: participante pendente bloqueia conclusão global; todos concluídos libera."""
    try:
        from app.models import Chamado
        from app.services.escalonamento_service import pode_concluir_global

        dados_pend = _chamado_dict(
            participantes=[
                {"supervisor_id": "sup_b", "area": "TI", "status": "pendente", "concluido_em": None}
            ]
        )
        chamado_pend = Chamado.from_dict(dados_pend, "ch_esc06a")
        bloqueado = not pode_concluir_global(chamado_pend)

        dados_ok = _chamado_dict(
            participantes=[
                {
                    "supervisor_id": "sup_b",
                    "area": "TI",
                    "status": "concluido",
                    "concluido_em": datetime.now(_BRT),
                }
            ]
        )
        chamado_ok = Chamado.from_dict(dados_ok, "ch_esc06b")
        liberado = pode_concluir_global(chamado_ok)

        if bloqueado and liberado:
            return Resultado(
                "ESC-06",
                "Multi-setor: pendente bloqueia; todos concluídos libera",
                "PASS",
                "pendente->pode_concluir_global=False [OK], todos_concluidos->True [OK]",
            )
        return Resultado(
            "ESC-06",
            "Multi-setor travado",
            "FAIL",
            f"bloqueado={bloqueado}, liberado={liberado}",
        )
    except Exception as e:
        return Resultado("ESC-06", "Multi-setor travado", "FAIL", f"Exceção: {e}")


# ─── ESC-07: Tempo útil +1h (pula almoço) ───────────────────────────────────


def check_esc_07() -> Resultado:
    """ESC-07: abertura 11:00 -> threshold 60 min úteis atingido às 13:30, não 12:30."""
    try:
        from app.services.business_time import minutos_uteis_entre

        # Segunda-feira 2026-06-22
        abertura = datetime(2026, 6, 22, 11, 0, 0, tzinfo=_BRT)
        antes_thresh = datetime(2026, 6, 22, 12, 30, 0, tzinfo=_BRT)  # em pleno almoço
        no_thresh = datetime(2026, 6, 22, 13, 30, 0, tzinfo=_BRT)  # +30 úteis pós-almoço

        min_12h30 = minutos_uteis_entre(abertura, antes_thresh)
        min_13h30 = minutos_uteis_entre(abertura, no_thresh)

        # 11:00–11:30 = 30 min úteis; almoço 11:30–13:00; 13:00–13:30 = +30 -> total 60
        if min_12h30 < 60 and min_13h30 >= 60:
            return Resultado(
                "ESC-07",
                "Tempo útil: 60 min atingidos às 13:30 (não 12:30 — pula almoço)",
                "PASS",
                f"min(11h->12h30)={min_12h30} (<60 [OK]), min(11h->13h30)={min_13h30} (>=60 [OK])",
            )
        return Resultado(
            "ESC-07",
            "Tempo útil +1h pula almoço",
            "FAIL",
            f"min_12h30={min_12h30} (esperado <60), min_13h30={min_13h30} (esperado >=60)",
        )
    except Exception as e:
        return Resultado("ESC-07", "Tempo útil", "FAIL", f"Exceção: {e}")


# ─── ESC-08: Fora da janela útil ────────────────────────────────────────────


def check_esc_08() -> Resultado:
    """ESC-08: sexta 16:45 e sábado -> pode_enviar_notificacao_agora() = False."""
    try:
        from app.services.business_time import pode_enviar_notificacao_agora

        # Sexta-feira 2026-06-26
        fora_16h45 = datetime(2026, 6, 26, 16, 45, 0, tzinfo=_BRT)  # após cutoff 16:30
        dentro_14h = datetime(2026, 6, 26, 14, 0, 0, tzinfo=_BRT)  # dentro da tarde
        sabado = datetime(2026, 6, 27, 10, 0, 0, tzinfo=_BRT)  # fim de semana

        fora_1 = not pode_enviar_notificacao_agora(fora_16h45)
        dentro = pode_enviar_notificacao_agora(dentro_14h)
        fora_2 = not pode_enviar_notificacao_agora(sabado)

        if fora_1 and dentro and fora_2:
            return Resultado(
                "ESC-08",
                "Fora da janela: 16:45 e sábado bloqueados; 14:00 liberado",
                "PASS",
                "16h45=False [OK], 14h00=True [OK], sábado=False [OK]",
            )
        return Resultado(
            "ESC-08",
            "Fora da janela",
            "FAIL",
            f"16h45_bloq={fora_1}, 14h_perm={dentro}, sab_bloq={fora_2}",
        )
    except Exception as e:
        return Resultado("ESC-08", "Fora da janela", "FAIL", f"Exceção: {e}")


# ─── ESC-09: Deadline imutável ──────────────────────────────────────────────


def check_esc_09() -> Resultado:
    """ESC-09: editar descrição não inclui data_em_atendimento no payload de update."""
    try:
        from app.services.edicao_chamado_service import processar_edicao_chamado

        data_em_original = datetime(2026, 6, 20, 10, 0, 0, tzinfo=_BRT)
        dados = _chamado_dict(
            status="Em Atendimento",
            responsavel_id="sup_a",
            data_em_atendimento=data_em_original,
            descricao="Descrição original",
        )

        sup_a = _usuario_mock("sup_a", "a@test.com", "Sup A", "supervisor", "TI", areas=["TI"])

        update_payload: dict = {}
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = dados

        with (
            patch("app.services.edicao_chamado_service.db") as mock_db,
            patch(
                "app.services.edicao_chamado_service.execute_with_retry",
                side_effect=lambda fn, payload, **kw: update_payload.update(payload),
            ),
            patch("app.services.edicao_chamado_service.Historico"),
            patch(
                "app.services.edicao_chamado_service.atualizar_status_chamado",
                return_value={"sucesso": True, "mensagem": "ok"},
            ),
            patch("app.services.edicao_chamado_service.Usuario.get_by_id", return_value=sup_a),
            patch("app.services.edicao_chamado_service.notificar_setores_adicionais_chamado"),
            patch(
                "app.services.permissions.usuario_pode_ver_chamado",
                return_value=True,
            ),
        ):
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            mock_db.batch.return_value = MagicMock()
            processar_edicao_chamado(
                usuario_atual=sup_a,
                chamado_id="ch_esc09",
                novo_status="Em Atendimento",
                motivo_cancelamento="",
                nova_descricao="Nova descrição editada",
                novo_responsavel_id="sup_a",
                novo_sla_str="",
                arquivos_novos=[],
                setores_adicionais_lista=[],
            )

        if "data_em_atendimento" not in update_payload:
            return Resultado(
                "ESC-09",
                "Deadline imutável: edição de descrição não altera data_em_atendimento",
                "PASS",
                f"data_em_atendimento ausente no payload [OK] (update_payload.keys={list(update_payload.keys())})",
            )
        return Resultado(
            "ESC-09",
            "Deadline imutável",
            "FAIL",
            f"data_em_atendimento presente no payload: {update_payload.get('data_em_atendimento')!r}",
        )
    except Exception as e:
        return Resultado("ESC-09", "Deadline imutável", "FAIL", f"Exceção: {e}")


# ─── ESC-10: Gestor read-only ────────────────────────────────────────────────


def check_esc_10(app) -> Resultado:
    """ESC-10: GET /gestor/dashboard -> 200; mudança status -> False/403."""
    try:
        gestor = _usuario_mock(
            "gest_1",
            "gestor@test.com",
            "Gestor Teste",
            "supervisor",
            "Geral",
            is_gestor=True,
            is_gestor_only=True,
        )

        # Sub-check A: GET /gestor/dashboard -> 200
        contexto_mock = {
            "contadores": {
                "total": 0,
                "atrasados": 0,
                "aberto_sem_resposta": 0,
                "multi_setor_travado": 0,
            },
            "insights": {
                "area_critica": None,
                "tempo_medio_sem_resposta_min": 0,
                "saude_percentual": 100,
            },
            "chamados": [],
            "grupos": [],
            "filtro_ativo": "todos",
        }
        with (
            patch("app.routes.auth.Usuario.get_by_email", return_value=gestor),
            patch("app.models_usuario.Usuario.get_by_id", return_value=gestor),
            patch("app.routes.auth._dispositivo_confiavel", return_value=True),
            patch(
                "app.routes.dashboard.obter_contexto_gestor_dashboard",
                return_value=contexto_mock,
            ),
        ):
            c = app.test_client()
            c.post(
                "/login",
                data={"email": "gestor@test.com", "senha": "ok"},
                follow_redirects=False,
            )
            r = c.get("/gestor/dashboard")

        dash_ok = r.status_code == 200

        # Sub-check B: verificar_permissao_mudanca_status -> False para gestor
        from app.models import Chamado
        from app.services.permission_validation import verificar_permissao_mudanca_status

        dados = _chamado_dict(status="Em Atendimento", responsavel_id="sup_a")
        chamado = Chamado.from_dict(dados, "ch_esc10")
        permitido, _ = verificar_permissao_mudanca_status(gestor, chamado, "Concluído")
        perm_negada = not permitido

        if dash_ok and perm_negada:
            return Resultado(
                "ESC-10",
                "Gestor read-only: dashboard 200 + mudança status negada",
                "PASS",
                f"GET /gestor/dashboard={r.status_code} [OK], verificar_permissao_mudanca_status=False [OK]",
            )
        return Resultado(
            "ESC-10",
            "Gestor read-only",
            "FAIL",
            f"dash_ok={dash_ok} (status={r.status_code}), perm_negada={perm_negada}",
        )
    except Exception as e:
        return Resultado("ESC-10", "Gestor read-only", "FAIL", f"Exceção: {e}")


# ─── Orquestrador ────────────────────────────────────────────────────────────


def executar_checks() -> list[Resultado]:
    app = _criar_app_testing()
    return [
        check_esc_01(),
        check_esc_02(),
        check_esc_03(),
        check_esc_04(),
        check_esc_05(),
        check_esc_06(),
        check_esc_07(),
        check_esc_08(),
        check_esc_09(),
        check_esc_10(app),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QA Onda 6 — Escalonamento/SLA (10 cenários ESC-*)"
    )
    parser.add_argument("--json", action="store_true", help="Saída JSON em vez de tabela")
    args = parser.parse_args()

    resultados = executar_checks()
    passed = sum(1 for r in resultados if r.status == "PASS")
    failed = sum(1 for r in resultados if r.status == "FAIL")
    skipped = sum(1 for r in resultados if r.status == "SKIP")
    total = len(resultados)

    if args.json:
        print(
            json.dumps(
                {
                    "executado_em": datetime.now(UTC).isoformat(),
                    "resumo": {"pass": passed, "fail": failed, "skip": skipped, "total": total},
                    "resultados": [asdict(r) for r in resultados],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("=" * 65)
        print("QA ONDA 6 — Escalonamento e SLA (playbook local)")
        print(f"Executado em: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 65)
        for r in resultados:
            icon = {"PASS": "OK  ", "FAIL": "FALHA", "SKIP": "SKIP "}[r.status]
            print(f"[{icon}] {r.id_esc} — {r.descricao}")
            print(f"         {r.detalhe}")
        print("-" * 65)
        print(f"Resumo: {passed} PASS | {failed} FAIL | {skipped} SKIP | {total} checks")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
