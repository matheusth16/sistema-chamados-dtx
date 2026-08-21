"""
Testes do endpoint GET /api/supervisores/lista.
Cobre filtragem do usuário logado da lista (anti-self-assignment) e de
usuários com nivel_gestao (gestores não devem aparecer como responsável
sugerido no formulário de abertura).
"""

from unittest.mock import MagicMock, patch


def _sup_mock(uid, nome, email, nivel_gestao=None):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    u.email = email
    u.nivel_gestao = nivel_gestao
    return u


def test_supervisores_lista_exclui_usuario_logado(client_logado_supervisor):
    """
    RED: /api/supervisores/lista não deve incluir o próprio usuário logado
    na lista de supervisores disponíveis para atribuição.
    """
    sup_logado = _sup_mock("sup_1", "Supervisor Teste", "sup@test.com")
    sup_outro = _sup_mock("sup_2", "Outro Supervisor", "outro@test.com")

    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area",
        return_value=[sup_logado, sup_outro],
    ):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao")

    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True

    ids_retornados = [s["id"] for s in data["supervisores"]]
    assert "sup_1" not in ids_retornados, (
        "O usuário logado (sup_1) não deve aparecer na lista de supervisores disponíveis"
    )
    assert "sup_2" in ids_retornados


def test_supervisores_lista_area_sem_supervisores_retorna_lista_vazia(client_logado_supervisor):
    """Área sem supervisores → lista vazia, sem erro."""
    with patch("app.routes.api_chamados.Usuario.get_supervisores_por_area", return_value=[]):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao")

    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True
    assert data["supervisores"] == []


def test_supervisores_lista_quando_unico_supervisor_e_o_proprio_logado_retorna_vazio(
    client_logado_supervisor,
):
    """
    Se o único supervisor da área for o próprio usuário logado,
    a lista retornada deve ser vazia (não self-assign).
    """
    sup_logado = _sup_mock("sup_1", "Supervisor Teste", "sup@test.com")

    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area", return_value=[sup_logado]
    ):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao")

    assert r.status_code == 200
    data = r.get_json()
    assert data["supervisores"] == []


def test_supervisores_lista_sem_login_retorna_json_401(client):
    """Sem autenticação → contrato JSON 401."""
    r = client.get("/api/supervisores/lista?area=Manutencao")
    assert r.status_code == 401
    assert r.is_json


def test_supervisores_lista_inclui_gestor_setor_mas_exclui_niveis_company_wide(
    client_logado_supervisor,
):
    """
    gestor_setor (escopo por área, Nível 3) aparece por padrão como responsável
    sugerido no formulário de abertura — pode virar dono de verdade do chamado
    (ver usuario_pode_operar_chamado). gerente_producao/assistente_gm/gm
    (company-wide, sem vínculo de área) continuam de fora: são só contato de
    escalonamento (decisão original de ca68b05), não atendimento direto.
    """
    sup_comum = _sup_mock("sup_2", "Supervisor Comum", "comum@test.com")
    gestor_setor = _sup_mock(
        "sup_3", "Gestor Setor", "gsetor@test.com", nivel_gestao="gestor_setor"
    )
    gerente_prod = _sup_mock(
        "sup_4", "Gerente Producao", "gprod@test.com", nivel_gestao="gerente_producao"
    )

    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area",
        return_value=[sup_comum, gestor_setor, gerente_prod],
    ):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao")

    assert r.status_code == 200
    data = r.get_json()
    por_id = {s["id"]: s for s in data["supervisores"]}
    assert set(por_id) == {"sup_2", "sup_3"}
    assert por_id["sup_2"]["gestor"] is False
    assert por_id["sup_3"]["gestor"] is True


def test_supervisores_lista_incluir_gestor_traz_gestores_marcados(client_logado_supervisor):
    """incluir_gestor=1 (usado só por "Transferir para Colega") inclui gestores
    da área na lista, com o flag `gestor` marcado — sem esse parâmetro, o
    comportamento padrão (exclui gestores) continua intacto para os outros
    dois formulários que usam o mesmo endpoint (Transferir Área, Incluir
    Supervisores)."""
    sup_comum = _sup_mock("sup_2", "Supervisor Comum", "comum@test.com")
    gestor_setor = _sup_mock(
        "sup_3", "Gestor Setor", "gsetor@test.com", nivel_gestao="gestor_setor"
    )

    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area",
        return_value=[sup_comum, gestor_setor],
    ):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao&incluir_gestor=1")

    assert r.status_code == 200
    data = r.get_json()
    por_id = {s["id"]: s for s in data["supervisores"]}
    assert set(por_id) == {"sup_2", "sup_3"}
    assert por_id["sup_2"]["gestor"] is False
    assert por_id["sup_3"]["gestor"] is True


def test_supervisor_pode_consultar_area_fora_das_proprias_para_rotear_chamado(
    client_logado_supervisor,
):
    """Sem incluir_gestor, qualquer área é consultável — abrir/transferir um
    chamado para outro setor é um fluxo legítimo e comum, não uma tentativa
    de enumeração (bug real: solicitante/supervisor ficava sem ninguém pra
    escolher como responsável ao rotear pra um setor fora da própria área)."""
    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area", return_value=[]
    ) as mock_buscar:
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Financeiro")

    assert r.status_code == 200
    mock_buscar.assert_called_once_with("Financeiro")


def test_supervisor_nao_enumera_gestores_fora_das_areas_permitidas(client_logado_supervisor):
    """incluir_gestor=1 (usado só por "Transferir para Colega", sempre com a
    área do próprio chamado que o usuário já atende) continua restrito à(s)
    própria(s) área(s) — essa é a única variante que expõe identidade de
    gestores, então segue com a checagem anti-enumeração."""
    with patch("app.routes.api_chamados.Usuario.get_supervisores_por_area") as mock_buscar:
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Financeiro&incluir_gestor=1")

    assert r.status_code == 403
    assert r.get_json()["sucesso"] is False
    mock_buscar.assert_not_called()


def test_solicitante_pode_consultar_qualquer_area_para_abrir_chamado(client_logado_solicitante):
    """Abertura de chamado deixa o solicitante escolher qualquer setor de
    destino — a pré-visualização de responsável precisa funcionar pra
    qualquer área, não só a própria."""
    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area", return_value=[]
    ) as mock_buscar:
        propria = client_logado_solicitante.get("/api/supervisores/lista?area=Planejamento")
        outra = client_logado_solicitante.get("/api/supervisores/lista?area=Financeiro")

    assert propria.status_code == 200
    assert outra.status_code == 200
    assert mock_buscar.call_count == 2


def test_solicitante_ve_gestor_setor_de_area_que_nao_e_sua_ao_abrir_chamado(
    client_logado_solicitante,
):
    """gestor_setor aparece pro solicitante mesmo numa área que não é a dele —
    sem incluir_gestor=1, a checagem anti-enumeração (restrita à própria área)
    não se aplica, igual já valia pra supervisor comum."""
    gestor_setor = _sup_mock(
        "sup_3", "Gestor Setor", "gsetor@test.com", nivel_gestao="gestor_setor"
    )

    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area",
        return_value=[gestor_setor],
    ):
        r = client_logado_solicitante.get("/api/supervisores/lista?area=Financeiro")

    assert r.status_code == 200
    data = r.get_json()
    assert [s["id"] for s in data["supervisores"]] == ["sup_3"]


def test_solicitante_com_incluir_gestor_ainda_bloqueado_fora_da_propria_area(
    client_logado_solicitante,
):
    """incluir_gestor=1 continua exigindo área própria mesmo pro solicitante
    (na prática o solicitante nunca manda esse parâmetro — é usado só pela
    tela de escalonamento do supervisor — mas a checagem de servidor não deve
    depender de quem está pedindo)."""
    with patch("app.routes.api_chamados.Usuario.get_supervisores_por_area") as mock_buscar:
        r = client_logado_solicitante.get(
            "/api/supervisores/lista?area=Financeiro&incluir_gestor=1"
        )

    assert r.status_code == 403
    mock_buscar.assert_not_called()


def test_admin_pode_consultar_area_arbitraria(client_logado_admin):
    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area", return_value=[]
    ) as mock_buscar:
        r = client_logado_admin.get("/api/supervisores/lista?area=Financeiro")

    assert r.status_code == 200
    mock_buscar.assert_called_once_with("Financeiro")


def test_admin_global_pode_consultar_area_arbitraria(client_logado_admin_global):
    with patch("app.routes.api_chamados.Usuario.get_supervisores_por_area", return_value=[]):
        r = client_logado_admin_global.get("/api/supervisores/lista?area=Financeiro")

    assert r.status_code == 200


def test_supervisores_lista_erro_interno_retorna_500(client_logado_supervisor):
    with patch(
        "app.routes.api_chamados.Usuario.get_supervisores_por_area",
        side_effect=RuntimeError("db interno"),
    ):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao")

    assert r.status_code == 500
    assert r.get_json()["sucesso"] is False
    assert "db interno" not in r.get_data(as_text=True)
