"""Testes do gerador de senha aleatória (extraído de app/routes/usuarios.py
pra ser reaproveitado por app/services/mfa_lembrete_service.py)."""

from app.services.senha_service import gerar_senha_aleatoria


def test_gerar_senha_aleatoria_tamanho_minimo():
    """Senha gerada deve ter ao menos 12 chars."""
    for _ in range(20):
        senha = gerar_senha_aleatoria()
        assert len(senha) >= 12, f"Senha muito curta: {len(senha)} chars"


def test_gerar_senha_aleatoria_complexidade():
    """Senha gerada deve conter maiúscula, minúscula, dígito e símbolo especial."""
    especiais = set("!@#$%&*")
    for _ in range(50):
        senha = gerar_senha_aleatoria()
        assert any(c.isupper() for c in senha), "Falta maiúscula"
        assert any(c.islower() for c in senha), "Falta minúscula"
        assert any(c.isdigit() for c in senha), "Falta dígito"
        assert any(c in especiais for c in senha), "Falta símbolo especial"


def test_gerar_senha_aleatoria_nao_tem_chars_invalidos():
    """Senha não deve conter espaço nem barras (que causam problemas em logs/URLs)."""
    for _ in range(30):
        senha = gerar_senha_aleatoria()
        assert " " not in senha
        assert "/" not in senha
        assert "\\" not in senha
