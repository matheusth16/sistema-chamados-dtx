"""
Helpers para construção de HTML de e-mails.

Objetivo:
- Garantir layout consistente entre diferentes tipos de notificação.
- Facilitar manutenção e reduzir duplicação em `app/services/notifications.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape


def _html(v: str | None) -> str:
    """Escapa conteúdo para inserir com segurança no HTML."""
    if v is None:
        return ""
    return escape(str(v), quote=True)


def build_detail_table(details: Iterable[tuple[str, str]]) -> str:
    """
    Constrói uma tabela simples (2 colunas) para exibir dados do chamado/usuário.
    """
    rows = []
    for k, v in details:
        key = _html(k)
        val = _html(v)
        rows.append(
            "<tr>"
            f'<td style="padding:12px 14px;background:#f9fafb;border-top:1px solid #e5e7eb;"><strong>{key}</strong></td>'
            f'<td style="padding:12px 14px;border-top:1px solid #e5e7eb;">{val}</td>'
            "</tr>"
        )
    if not rows:
        return ""

    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="margin:16px 0;border:1px solid #e5e7eb;border-radius:8px;border-collapse:separate;overflow:hidden;">'
        + "".join(rows)
        + "</table>"
    )


def build_cta_button(text: str, href: str, bg: str) -> str:
    """Constrói um CTA em formato de link (compatível com e-mail)."""
    return (
        f'<a href="{_html(href)}" '
        f'style="background: {_html(bg)}; color: white; padding: 10px 20px; '
        'text-decoration: none; border-radius: 6px; display: inline-block;">'
        f"{_html(text)}"
        "</a>"
    )


def build_email_shell(header_title: str, header_color: str, body_html: str) -> str:
    """Wrapper padrão para e-mails em HTML."""
    return (
        '<div style="font-family: Segoe UI,Arial,sans-serif;background:#f4f6f8;padding:24px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:10px;'
        'overflow:hidden;border:1px solid #e6e9ef;">'
        "<tr>"
        '<td style="background:'
        f"{_html(header_color)}"
        ';padding:18px 24px;color:#ffffff;">'
        f'<h2 style="margin:0;font-size:20px;">{_html(header_title)}</h2>'
        "</td>"
        "</tr>"
        "<tr>"
        f'<td style="padding:24px;color:#1f2937;">{body_html}</td>'
        "</tr>"
        "<tr>"
        '<td style="padding:14px 24px;background:#f9fafb;color:#6b7280;font-size:12px;">'
        "<em>Ticket System - DTX</em>"
        "</td>"
        "</tr>"
        "</table>"
        "</div>"
    )


def build_two_ctas(ctas: list[tuple[str, str, str]]) -> str:
    """
    Constrói dois CTAs lado a lado quando houver 2 itens.

    ctas: [(text, href, bg), ...]
    """
    if not ctas:
        return ""
    buttons = []
    for i, (text, href, bg) in enumerate(ctas):
        margin_right = "margin-right:8px;" if i == 0 and len(ctas) > 1 else ""
        buttons.append(
            f'<a href="{_html(href)}" '
            f'style="background: {_html(bg)}; color: white; padding: 10px 20px; '
            "text-decoration: none; border-radius: 6px; display: inline-block; "
            f'{margin_right}">'
            f"{_html(text)}"
            "</a>"
        )
    return '<p style="margin-top:20px;">' + "".join(buttons) + "</p>"
