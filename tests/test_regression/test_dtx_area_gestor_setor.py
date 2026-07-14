"""
Testes de regressão — F-XX: seletor de Área/Setor visível para Gestor de Setor.

toggleArea() em usuario_form.html só mostrava o seletor de área quando
Perfil == 'supervisor', ignorando Nível de Gestão. Um usuário Admin com
Nível de Gestão = 'gestor_setor' não tinha como ver/definir qual setor
gerencia — e sla_escalacao_service.py usa exatamente esse campo (usuario.areas)
para mapear o gestor de cada setor no escalonamento de SLA.
"""

from pathlib import Path

USUARIO_FORM_HTML = Path(__file__).parent.parent.parent / "app" / "templates" / "usuario_form.html"


def _source() -> str:
    return USUARIO_FORM_HTML.read_text(encoding="utf-8")


def test_toggle_area_considera_nivel_gestao_gestor_setor():
    """toggleArea() deve mostrar o seletor de área quando perfil=supervisor
    OU nivel_gestao=gestor_setor — não só quando perfil=supervisor."""
    src = _source()
    idx_fn_start = src.index("function toggleArea()")
    idx_fn_end = src.index("\n    }", idx_fn_start)
    corpo_funcao = src[idx_fn_start:idx_fn_end]
    assert "nivel_gestao" in corpo_funcao, (
        "toggleArea() não considera nivel_gestao — Admin marcado como Gestor de "
        "Setor não consegue ver/definir a área que gerencia"
    )


def test_nivel_gestao_select_tem_listener_de_change():
    """O <select> de nível de gestão deve disparar toggleArea() ao mudar,
    assim como o de perfil já faz — senão marcar 'Gestor de Setor' não revela
    o seletor de área sem antes mexer no campo Perfil."""
    src = _source()
    assert "nivelGestaoSelect" in src or "getElementById('nivel_gestao').addEventListener" in src, (
        "select#nivel_gestao não tem listener de 'change' chamando toggleArea()"
    )
