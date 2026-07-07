"""Testes do serviço de MFA (TOTP + códigos de backup)."""

import pyotp

from app.services import mfa_service


def test_gerar_secret_retorna_base32_valido():
    """gerar_secret() retorna string base32 válida para pyotp."""
    secret = mfa_service.gerar_secret()
    assert isinstance(secret, str)
    assert len(secret) >= 16
    # Deve ser utilizável por pyotp sem erro
    pyotp.TOTP(secret).now()


def test_gerar_secret_e_unico_a_cada_chamada():
    """Duas chamadas geram secrets diferentes (aleatoriedade)."""
    assert mfa_service.gerar_secret() != mfa_service.gerar_secret()


def test_gerar_qr_code_data_uri_retorna_png_base64():
    """gerar_qr_code_data_uri retorna data URI PNG válido."""
    secret = mfa_service.gerar_secret()
    data_uri = mfa_service.gerar_qr_code_data_uri("user@dtx.aero", secret)
    assert data_uri.startswith("data:image/png;base64,")
    assert len(data_uri) > 100


def test_verificar_codigo_totp_aceita_codigo_correto():
    """Código TOTP gerado a partir do secret é aceito."""
    secret = mfa_service.gerar_secret()
    codigo = pyotp.TOTP(secret).now()
    assert mfa_service.verificar_codigo_totp(secret, codigo) is True


def test_verificar_codigo_totp_rejeita_codigo_incorreto():
    """Código TOTP incorreto é rejeitado."""
    secret = mfa_service.gerar_secret()
    assert mfa_service.verificar_codigo_totp(secret, "000000") is False


def test_verificar_codigo_totp_rejeita_secret_ou_codigo_vazio():
    """Secret ou código vazios retornam False sem levantar exceção."""
    assert mfa_service.verificar_codigo_totp("", "123456") is False
    assert mfa_service.verificar_codigo_totp("SECRET", "") is False
    assert mfa_service.verificar_codigo_totp("", "") is False


def test_verificar_codigo_totp_ignora_espacos():
    """Código com espaços (ex: '123 456') é normalizado antes de validar."""
    secret = mfa_service.gerar_secret()
    codigo = pyotp.TOTP(secret).now()
    codigo_com_espaco = f"{codigo[:3]} {codigo[3:]}"
    assert mfa_service.verificar_codigo_totp(secret, codigo_com_espaco) is True


def test_verificar_codigo_totp_codigo_malformado_nao_levanta_excecao():
    """Código não numérico não deve levantar exceção, apenas retornar False."""
    secret = mfa_service.gerar_secret()
    assert mfa_service.verificar_codigo_totp(secret, "abcdef") is False


def test_gerar_codigos_backup_gera_quantidade_esperada():
    """Gera 10 códigos de backup únicos por padrão."""
    codigos = mfa_service.gerar_codigos_backup()
    assert len(codigos) == mfa_service.BACKUP_CODES_COUNT
    assert len(set(codigos)) == len(codigos)


def test_hash_codigos_backup_produz_hashes_verificaveis():
    """Códigos hasheados não são iguais ao texto plano, mas validam via check."""
    codigos = mfa_service.gerar_codigos_backup(3)
    hashes = mfa_service.hash_codigos_backup(codigos)
    assert len(hashes) == 3
    assert all(h != c for h, c in zip(hashes, codigos, strict=True))


def test_verificar_e_consumir_codigo_backup_aceita_e_remove():
    """Código de backup válido é aceito e removido da lista (uso único)."""
    codigos = mfa_service.gerar_codigos_backup(3)
    hashes = mfa_service.hash_codigos_backup(codigos)

    valido, restantes = mfa_service.verificar_e_consumir_codigo_backup(hashes, codigos[0])

    assert valido is True
    assert len(restantes) == 2
    # O código usado não deve mais validar
    valido2, _ = mfa_service.verificar_e_consumir_codigo_backup(restantes, codigos[0])
    assert valido2 is False


def test_verificar_e_consumir_codigo_backup_rejeita_codigo_invalido():
    """Código de backup inexistente é rejeitado sem alterar a lista."""
    codigos = mfa_service.gerar_codigos_backup(3)
    hashes = mfa_service.hash_codigos_backup(codigos)

    valido, restantes = mfa_service.verificar_e_consumir_codigo_backup(hashes, "codigo-invalido")

    assert valido is False
    assert restantes == hashes


def test_verificar_e_consumir_codigo_backup_lista_vazia():
    """Lista de hashes vazia/None não levanta exceção."""
    valido, restantes = mfa_service.verificar_e_consumir_codigo_backup([], "qualquer")
    assert valido is False
    assert restantes == []

    valido2, restantes2 = mfa_service.verificar_e_consumir_codigo_backup(None, "qualquer")
    assert valido2 is False
    assert restantes2 == []
