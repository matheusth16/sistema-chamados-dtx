"""Testes dos validadores de data, email, telefone, descrição e código RL."""
import pytest
from app.services.date_validators import (
    validar_data_formato,
    validar_intervalo_datas,
    validar_email,
    validar_telefone_br,
    normalizar_telefone_br,
    validar_descricao,
    validar_codigo_rl,
)


def test_validar_data_formato_aceita_dd_mm_yyyy():
    ok, msg = validar_data_formato('18/02/2026')
    assert ok is True
    assert msg == ''


def test_validar_data_formato_rejeita_formato_errado():
    ok, msg = validar_data_formato('2026-02-18', '%d/%m/%Y')
    assert ok is False
    assert 'DD/MM/YYYY' in msg or 'formato' in msg.lower()


def test_validar_intervalo_datas_aceita_inicio_menor_igual_fim():
    ok, msg = validar_intervalo_datas('01/02/2026', '28/02/2026')
    assert ok is True
    assert msg == ''


def test_validar_intervalo_datas_rejeita_inicio_maior_fim():
    ok, msg = validar_intervalo_datas('28/02/2026', '01/02/2026')
    assert ok is False
    assert 'menor' in msg or 'igual' in msg


def test_validar_email_valido():
    ok, msg = validar_email('user@example.com')
    assert ok is True
    assert msg == ''


def test_validar_email_invalido():
    ok, msg = validar_email('email-invalido')
    assert ok is False
    assert 'email' in msg.lower()


def test_validar_telefone_br_10_digitos():
    ok, _ = validar_telefone_br('1133334444')
    assert ok is True


def test_validar_telefone_br_11_digitos():
    ok, _ = validar_telefone_br('11987654321')
    assert ok is True


def test_validar_telefone_br_formato_com_mascara():
    ok, _ = validar_telefone_br('(11) 98765-4321')
    assert ok is True


def test_validar_telefone_br_poucos_digitos_rejeita():
    ok, msg = validar_telefone_br('123456')
    assert ok is False
    assert '10' in msg or '11' in msg


def test_normalizar_telefone_br_celular():
    r = normalizar_telefone_br('11987654321')
    assert r == '(11) 98765-4321'


def test_normalizar_telefone_br_fixo():
    r = normalizar_telefone_br('1133334444')
    assert r == '(11) 3333-4444'


def test_validar_descricao_vazia():
    ok, msg = validar_descricao('')
    assert ok is False
    assert 'obrigatória' in msg.lower()


def test_validar_descricao_minimo_caracteres():
    ok, msg = validar_descricao('ab', min_chars=3)
    assert ok is False
    assert '3' in msg


def test_validar_descricao_ok():
    ok, msg = validar_descricao('Descrição válida com mais de 3 caracteres')
    assert ok is True
    assert msg == ''


def test_validar_codigo_rl_tres_digitos():
    ok, msg = validar_codigo_rl('045')
    assert ok is True
    assert msg == ''


def test_validar_codigo_rl_rejeita_dois_digitos():
    ok, msg = validar_codigo_rl('12')
    assert ok is False
    assert '3 dígitos' in msg


def test_validar_codigo_rl_rejeita_letras():
    ok, msg = validar_codigo_rl('04A')
    assert ok is False
