"""Helpers de resposta JSON pras rotas /api/*.

Centraliza o shape {"sucesso": bool, "erro"?: str, ...} que antes era
reimplementado à mão em ~95 pontos entre api_chamados.py, api_colaboracao.py
e api_solicitante.py (achado em auditoria, 2026-08-05) — mudar o contrato de
erro/sucesso exigia editar dezenas de lugares.
"""

from flask import jsonify


def erro_json(mensagem: str, codigo: int = 400):
    """jsonify({"sucesso": False, "erro": mensagem}), codigo"""
    return jsonify({"sucesso": False, "erro": mensagem}), codigo


def sucesso_json(codigo: int = 200, **campos):
    """jsonify({"sucesso": True, **campos}), codigo"""
    return jsonify({"sucesso": True, **campos}), codigo
