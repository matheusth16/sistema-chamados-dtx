"""Testes do serviço de validação de novo chamado."""
import pytest
from unittest.mock import MagicMock

from app.services.validators import validar_novo_chamado


def test_validar_novo_chamado_formulario_valido():
    """Formulário com descrição, tipo e categoria válidos retorna lista vazia."""
    form = {'descricao': 'Descrição com mais de 3 caracteres', 'tipo': 'Manutencao', 'categoria': 'Chamado'}
    erros = validar_novo_chamado(form)
    assert erros == []


def test_validar_novo_chamado_descricao_obrigatoria():
    """Sem descrição retorna erro."""
    form = {'descricao': '', 'tipo': 'Manutencao', 'categoria': 'Chamado'}
    erros = validar_novo_chamado(form)
    assert any('descrição' in e.lower() and 'obrigatória' in e.lower() for e in erros)


def test_validar_novo_chamado_descricao_minimo_caracteres():
    """Descrição com menos de 3 caracteres retorna erro."""
    form = {'descricao': 'ab', 'tipo': 'Manutencao', 'categoria': 'Chamado'}
    erros = validar_novo_chamado(form)
    assert any('mínimo 3' in e for e in erros)


def test_validar_novo_chamado_tipo_obrigatorio():
    """Sem setor/tipo retorna erro."""
    form = {'descricao': 'Descrição válida aqui', 'tipo': '', 'categoria': 'Chamado'}
    erros = validar_novo_chamado(form)
    assert any('Setor' in e or 'Tipo' in e for e in erros)


def test_validar_novo_chamado_projetos_exige_rl_preenchido():
    """Categoria Projetos exige código RL preenchido (letras, números e caracteres permitidos)."""
    form_vazio = {'descricao': 'Projeto X', 'tipo': 'Engenharia', 'categoria': 'Projetos', 'rl_codigo': ''}
    erros = validar_novo_chamado(form_vazio)
    assert any('RL' in e and 'obrigatório' in e for e in erros)

    form_ok = {'descricao': 'Projeto Y', 'tipo': 'Engenharia', 'categoria': 'Projetos', 'rl_codigo': '045'}
    assert validar_novo_chamado(form_ok) == []

    form_ok_alfanumerico = {'descricao': 'Projeto Z', 'tipo': 'Engenharia', 'categoria': 'Projetos', 'rl_codigo': 'ABC-01'}
    assert validar_novo_chamado(form_ok_alfanumerico) == []

    form_ok_com_caracteres = {'descricao': 'Projeto W', 'tipo': 'Engenharia', 'categoria': 'Projetos', 'rl_codigo': '123/2026 (rev.1)'}
    assert validar_novo_chamado(form_ok_com_caracteres) == []


def test_validar_novo_chamado_projetos_rl_caracteres_invalidos():
    """RL com caracteres não permitidos (ex.: @ # %) é rejeitado."""
    form = {'descricao': 'Projeto', 'tipo': 'Engenharia', 'categoria': 'Projetos', 'rl_codigo': '04@123'}
    erros = validar_novo_chamado(form)
    assert len(erros) >= 1 and any('RL' in e for e in erros)


def test_validar_novo_chamado_projetos_rl_maximo_100():
    """RL com mais de 100 caracteres retorna erro."""
    form = {'descricao': 'Projeto', 'tipo': 'Engenharia', 'categoria': 'Projetos', 'rl_codigo': 'A' * 101}
    erros = validar_novo_chamado(form)
    assert any('100' in e or 'máximo' in e for e in erros)


def test_validar_novo_chamado_arquivo_extensao_invalida():
    """Arquivo com extensão não permitida retorna erro."""
    form = {'descricao': 'Descrição ok', 'tipo': 'Manutencao', 'categoria': 'Chamado'}
    arquivo = MagicMock()
    arquivo.filename = 'documento.exe'
    erros = validar_novo_chamado(form, arquivo)
    assert any('Formato de arquivo' in e or 'inválido' in e.lower() for e in erros)


def test_validar_novo_chamado_arquivo_extensao_permitida():
    """Arquivo com extensão permitida (ex: pdf) não gera erro de arquivo."""
    form = {'descricao': 'Descrição ok', 'tipo': 'Manutencao', 'categoria': 'Chamado'}
    arquivo = MagicMock()
    arquivo.filename = 'anexo.pdf'
    erros = validar_novo_chamado(form, arquivo)
    assert not any('arquivo' in e.lower() or 'Formato' in e for e in erros)


def test_validar_novo_chamado_sem_arquivo_nao_valida_arquivo():
    """Sem arquivo (ou filename vazio), validação de arquivo é ignorada (descrição e tipo válidos)."""
    form = {'descricao': 'Descrição com mais de 3 caracteres', 'tipo': 'Manutencao', 'categoria': 'Chamado'}
    erros = validar_novo_chamado(form, None)
    assert erros == []
    arquivo_vazio = MagicMock()
    arquivo_vazio.filename = ''
    erros2 = validar_novo_chamado(form, arquivo_vazio)
    assert erros2 == []
