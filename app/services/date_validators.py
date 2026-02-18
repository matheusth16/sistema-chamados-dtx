"""
Utilitários de validação para o sistema de chamados.

Inclui validações de data, formatação e lógica de negócio.
"""

from datetime import datetime
from typing import Tuple
import re


def validar_data_formato(data_str: str, formato: str = '%d/%m/%Y') -> Tuple[bool, str]:
    """
    Valida se uma string segue um determinado formato de data.
    
    Args:
        data_str: String com a data
        formato: Formato esperado (padrão: %d/%m/%Y)
        
    Returns:
        Tupla (sucesso, mensagem_erro)
        
    Exemplos:
        >>> validar_data_formato('18/02/2026')
        (True, '')
        
        >>> validar_data_formato('2026-02-18')
        (False, 'Formato de data esperado: DD/MM/YYYY')
    """
    try:
        datetime.strptime(data_str.strip(), formato)
        return True, ""
    except ValueError:
        return False, f"Formato de data esperado: {formato}"


def validar_intervalo_datas(
    data_inicio_str: str,
    data_fim_str: str,
    formato: str = '%d/%m/%Y'
) -> Tuple[bool, str]:
    """
    Valida se data_inicio é menor ou igual a data_fim.
    
    Args:
        data_inicio_str: String da data inicial
        data_fim_str: String da data final
        formato: Formato esperado (padrão: %d/%m/%Y)
        
    Returns:
        Tupla (sucesso, mensagem_erro)
        
    Exemplos:
        >>> validar_intervalo_datas('01/02/2026', '28/02/2026')
        (True, '')
        
        >>> validar_intervalo_datas('28/02/2026', '01/02/2026')
        (False, 'Data inicial deve ser menor que data final')
    """
    # Valida ambas as datas primeiro
    sucesso_inicio, erro_inicio = validar_data_formato(data_inicio_str, formato)
    if not sucesso_inicio:
        return False, f"Data inicial: {erro_inicio}"
    
    sucesso_fim, erro_fim = validar_data_formato(data_fim_str, formato)
    if not sucesso_fim:
        return False, f"Data final: {erro_fim}"
    
    # Compara as datas
    d_inicio = datetime.strptime(data_inicio_str.strip(), formato)
    d_fim = datetime.strptime(data_fim_str.strip(), formato)
    
    if d_inicio > d_fim:
        return False, "Data inicial deve ser menor ou igual à data final"
    
    return True, ""


def validar_email(email: str) -> Tuple[bool, str]:
    """
    Valida formato básico de email.
    
    Args:
        email: String com email
        
    Returns:
        Tupla (sucesso, mensagem_erro)
        
    Exemplos:
        >>> validar_email('user@example.com')
        (True, '')
        
        >>> validar_email('email-invalido')
        (False, 'Formato de email inválido')
    """
    # Regex básica para email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if re.match(pattern, email.strip()):
        return True, ""
    return False, "Formato de email inválido"


def validar_telefone_br(telefone: str) -> Tuple[bool, str]:
    """
    Valida telefone brasileiro (com ou sem formatação).
    
    Args:
        telefone: String com telefone
        
    Returns:
        Tupla (sucesso, mensagem_erro)
        
    Exemplos:
        >>> validar_telefone_br('(11) 98765-4321')
        (True, '')
        
        >>> validar_telefone_br('11987654321')
        (True, '')
    """
    # Remove caracteres não numéricos
    apenas_numeros = re.sub(r'\D', '', telefone)
    
    # Deve ter 10 ou 11 dígitos
    if len(apenas_numeros) not in (10, 11):
        return False, "Telefone deve ter 10 ou 11 dígitos"
    
    return True, ""


def normalizar_telefone_br(telefone: str) -> str:
    """
    Normaliza telefone brasileiro para formato padrão.
    
    Args:
        telefone: String com telefone (com ou sem formatação)
        
    Returns:
        Telefone formatado como (XX) XXXXX-XXXX ou (XX) XXXX-XXXX
        
    Exemplos:
        >>> normalizar_telefone_br('11987654321')
        '(11) 98765-4321'
        
        >>> normalizar_telefone_br('1133334444')
        '(11) 3333-4444'
    """
    apenas_numeros = re.sub(r'\D', '', telefone)
    
    if len(apenas_numeros) == 11:
        # Celular: (XX) XXXXX-XXXX
        return f"({apenas_numeros[:2]}) {apenas_numeros[2:7]}-{apenas_numeros[7:]}"
    elif len(apenas_numeros) == 10:
        # Fixo: (XX) XXXX-XXXX
        return f"({apenas_numeros[:2]}) {apenas_numeros[2:6]}-{apenas_numeros[6:]}"
    
    return telefone  # Retorna original se não conseguir normalizar


def validar_descricao(descricao: str, min_chars: int = 3) -> Tuple[bool, str]:
    """
    Valida descrição de chamado.
    
    Args:
        descricao: String com descrição
        min_chars: Número mínimo de caracteres (padrão: 3)
        
    Returns:
        Tupla (sucesso, mensagem_erro)
    """
    desc_limpa = descricao.strip()
    
    if not desc_limpa:
        return False, "Descrição é obrigatória"
    
    if len(desc_limpa) < min_chars:
        return False, f"Descrição deve ter no mínimo {min_chars} caracteres"
    
    if len(desc_limpa) > 5000:
        return False, "Descrição não pode exceder 5000 caracteres"
    
    return True, ""


def validar_codigo_rl(codigo_rl: str) -> Tuple[bool, str]:
    """
    Valida código RL (3 dígitos numéricos).
    
    Args:
        codigo_rl: String com código RL
        
    Returns:
        Tupla (sucesso, mensagem_erro)
        
    Exemplos:
        >>> validar_codigo_rl('045')
        (True, '')
        
        >>> validar_codigo_rl('12')
        (False, 'Código RL deve conter exatamente 3 dígitos')
    """
    codigo_limpo = codigo_rl.strip()
    
    if not re.match(r'^\d{3}$', codigo_limpo):
        return False, "Código RL deve conter exatamente 3 dígitos numéricos"
    
    return True, ""
