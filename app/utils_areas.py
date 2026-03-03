"""
Mapeamento entre nome do setor (formulário) e área usada no cadastro de usuários.
Garante que "Responsável Sugerido" e atribuição automática funcionem para todos os setores.
"""

# Setor (nome_pt no formulário) -> área (value no cadastro de supervisores)
SETOR_PARA_AREA = {
    "Material Indireto / Compras": "Material",
    "Manutenção": "Manutencao",
}


def setor_para_area(setor_nome: str) -> str:
    """
    Converte nome do setor (valor do formulário Tipo/Setor) para a área
    usada no cadastro de usuários (supervisores). Assim a busca por
    supervisores e o filtro do dashboard usam o mesmo identificador.
    """
    if not setor_nome or not isinstance(setor_nome, str):
        return setor_nome or ""
    return SETOR_PARA_AREA.get(setor_nome.strip(), setor_nome.strip())
