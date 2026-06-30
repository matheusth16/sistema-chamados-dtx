"""
Validação de dados de chamados e formulários.

Centraliza regras de negócio para criação/edição de chamados:
- Campos obrigatórios (descrição, tipo, categoria)
- Regra DTX: Projetos exigem código RL (letras, números e caracteres; 1 a 100 caracteres)
- Extensões e validação de anexos (extensão + magic bytes para evitar upload malicioso)
"""

import csv
import io
import logging
import re
from typing import Any
from urllib.parse import urlparse

from flask import current_app

logger = logging.getLogger(__name__)


# Fallback se config não estiver disponível (ex.: testes)
def _get_extensoes_permitidas() -> set[str]:
    try:
        return current_app.config.get("EXTENSOES_UPLOAD_PERMITIDAS", set())
    except RuntimeError:
        return {
            "png",
            "jpg",
            "jpeg",
            "pdf",
            "xls",
            "xlsx",
            "xlsm",
            "xlsb",
            "xltx",
            "xltm",
            "csv",
            "doc",
            "docx",
            "docm",
            "dotx",
            "dotm",
        }


def get_extensoes_permitidas() -> set[str]:
    """Retorna o conjunto de extensões permitidas (para exibição em templates)."""
    return _get_extensoes_permitidas()


# Magic bytes (início do arquivo) por extensão - validação por conteúdo real
# Office Open XML (xlsx, docx, xlsm, docm, xltx, xltm, dotx, dotm) = ZIP
# OLE (xls, xlsb, doc) = formato binário antigo
# CSV: sem assinatura única; validação apenas por extensão
_MAGIC_BYTES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "pdf": (b"%PDF",),
    "xlsx": (b"PK",),
    "xlsm": (b"PK",),
    "xltx": (b"PK",),
    "xltm": (b"PK",),
    "xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "xlsb": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "docx": (b"PK",),
    "docm": (b"PK",),
    "dotx": (b"PK",),
    "dotm": (b"PK",),
}


def _arquivo_permitido(filename: str) -> bool:
    """Verifica se a extensão do arquivo é permitida."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in _get_extensoes_permitidas()


def _validar_csv(arquivo: Any) -> tuple[bool, str]:
    """
    Verifica se o arquivo é um CSV estruturalmente válido tentando fazer o parse.
    Detecta arquivos corrompidos, binários renomeados como .csv ou CSV vazios.
    """
    try:
        stream = getattr(arquivo, "stream", None)
        if not stream:
            return False, "Arquivo CSV sem stream para leitura."
        if hasattr(stream, "seek"):
            stream.seek(0)
        content = stream.read(65536)  # 64 KB é suficiente para validar estrutura
        if hasattr(stream, "seek"):
            stream.seek(0)
        if not content:
            return False, "Arquivo CSV vazio."
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        next(reader)  # Lê pelo menos a primeira linha; lança StopIteration se vazio
        return True, ""
    except StopIteration:
        return False, "Arquivo CSV vazio ou sem linhas válidas."
    except csv.Error:
        return False, "Arquivo CSV inválido ou corrompido."
    except Exception:
        return False, "Erro ao validar arquivo CSV."


def _arquivo_conteudo_permitido(arquivo: Any) -> tuple[bool, str]:
    """
    Valida o conteúdo do arquivo pelos magic bytes (tipo real).
    Retorna (True, '') se válido; (False, mensagem_erro) se inválido.
    Garante que a extensão declarada corresponda ao conteúdo (evita .pdf com conteúdo executável).
    """
    if not arquivo or not getattr(arquivo, "filename", None) or not arquivo.filename.strip():
        return True, ""
    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    # CSV: sem magic bytes, mas valida estrutura via parse
    if ext == "csv":
        return _validar_csv(arquivo)
    # Outros formatos sem magic bytes conhecidos: aceitar por extensão
    if ext not in _MAGIC_BYTES:
        return True, ""
    expected_sigs = _MAGIC_BYTES[ext]
    try:
        stream = getattr(arquivo, "stream", None)
        if not stream:
            return False, "Arquivo não possui stream para leitura."
        if hasattr(stream, "seek"):
            stream.seek(0)
        header = stream.read(max(len(sig) for sig in expected_sigs))
        if hasattr(stream, "seek"):
            stream.seek(0)
        if not header:
            return False, "Arquivo vazio ou não legível."
        if not any(header.startswith(sig) for sig in expected_sigs):
            return (
                False,
                f"O conteúdo do arquivo não corresponde à extensão .{ext}. Envie um arquivo válido.",
            )
        return True, ""
    except Exception as e:
        return False, f"Erro ao validar arquivo: {e}"


def _get_max_anexo_bytes() -> int:
    try:
        return current_app.config.get("MAX_ANEXO_BYTES", 10 * 1024 * 1024)
    except RuntimeError:
        return 10 * 1024 * 1024


def _validar_tamanho(arquivo: Any) -> tuple[bool, str]:
    """Verifica se o arquivo excede MAX_ANEXO_BYTES (10 MB por padrão).

    Usa content_length quando disponível; caso contrário lê o stream e faz seek(0).
    """
    limite = _get_max_anexo_bytes()
    tamanho = getattr(arquivo, "content_length", None)
    if isinstance(tamanho, int) and tamanho > 0:
        if tamanho > limite:
            mb = limite // (1024 * 1024)
            return False, f"{arquivo.filename}: excede {mb} MB por arquivo."
        return True, ""
    # Fallback: lê o stream para medir
    try:
        stream = getattr(arquivo, "stream", None)
        if stream and hasattr(stream, "read"):
            if hasattr(stream, "seek"):
                stream.seek(0)
            dados = stream.read()
            if hasattr(stream, "seek"):
                stream.seek(0)
            if len(dados) > limite:
                mb = limite // (1024 * 1024)
                return False, f"{arquivo.filename}: excede {mb} MB por arquivo."
    except Exception:
        pass
    return True, ""


ALLOWED_EXTERNAL_LINK_DOMAINS: frozenset[str] = frozenset(
    {
        "sharepoint.com",
        "onedrive.live.com",
        "1drv.ms",
    }
)


def validar_links_externos(links: list[str]) -> list[str]:
    """Valida links OneDrive/SharePoint submetidos como alternativa a upload >10 MB.

    Retorna lista de mensagens de erro; lista vazia indica que todos os links são válidos.
    """
    erros: list[str] = []
    for link in links:
        link = link.strip()
        if not link:
            continue
        if not link.startswith("https://"):
            erros.append("Link externo deve começar com https://.")
            continue
        try:
            netloc = urlparse(link).netloc.lower()
        except Exception:
            erros.append("Link externo com formato inválido.")
            continue
        if not any(netloc == d or netloc.endswith("." + d) for d in ALLOWED_EXTERNAL_LINK_DOMAINS):
            erros.append(
                "Link inválido. Use uma URL do SharePoint ou OneDrive "
                "(sharepoint.com, onedrive.live.com ou 1drv.ms)."
            )
    return erros


def _log_ab_descricao_insuficiente(form: Any) -> None:
    """Registra evento AB-001 quando a descrição é rejeitada pelo validador.

    Threshold alinhado ao validador atual (3 chars), não à hipótese original (30 chars).
    Ver docs/AB_TEST_PLAN.md seção 2 para justificativa.
    """
    ab_variante = (form.get("ab_variante") or "A") if hasattr(form, "get") else "A"
    uid = ""
    try:
        from flask_login import current_user

        uid = getattr(current_user, "id", "")
    except Exception:
        pass
    logger.info(
        "ab_event",
        extra={
            "experimento": "AB-001",
            "variante": ab_variante,
            "evento": "descricao_insuficiente",
            "uid": uid,
        },
    )


def validar_novo_chamado(
    form: Any,
    arquivos: list | None = None,
    links_externos: list | None = None,
) -> list[str]:
    """
    Valida dados do formulário de novo chamado. Blindagem antes de persistir no Firestore.

    Args:
        form: Dict-like com campos do formulário (descricao, tipo, categoria, rl_codigo, etc.)
        arquivos: Lista de FileStorage opcional (request.files.getlist('anexo')).

    Returns:
        Lista de mensagens de erro. Lista vazia indica que os dados são válidos.

    Regras:
        - Descrição obrigatória, mínimo 3 caracteres.
        - Atribuição ao setor obrigatória.
        - Gate e impacto obrigatórios.
        - Categoria Projetos exige rl_codigo preenchido (letras, números e caracteres; 1 a 100 caracteres).
        - Cada anexo: extensão allowlist, magic bytes, máximo 10 MB.
    """
    erros = []

    # 1. Validação Básica de Campos Obrigatórios
    descricao = form.get("descricao", "").strip()
    tipo = form.get("tipo")
    categoria = (form.get("categoria") or "").strip()
    gate = (form.get("gate") or "").strip()
    impacto = (form.get("impacto") or "").strip()

    if not descricao:
        _log_ab_descricao_insuficiente(form)
        erros.append("A descrição do chamado é obrigatória.")
    elif len(descricao) < 3:
        _log_ab_descricao_insuficiente(form)
        erros.append("A descrição deve ter no mínimo 3 caracteres.")

    if not tipo:
        erros.append("É necessário atribuir um setor.")

    if not categoria:
        erros.append("A categoria do chamado é obrigatória.")

    if not gate:
        erros.append("É necessário atribuir um gate.")
    else:
        from app.services.gates_service import is_gate_valido

        if not is_gate_valido(gate):
            erros.append(
                "Gate inválido. Selecione N/A ou um gate com sub-etapa (ex: Gate 1 - Desmontagem)."
            )

    if not impacto:
        erros.append("O impacto do chamado é obrigatório.")

    # 2. Validação Específica da DTX (Regra do RL)
    # Para Projetos: código RL obrigatório — letras, números e caracteres (1 a 100)
    if categoria == "Projetos":
        rl_codigo = (form.get("rl_codigo") or "").strip()
        if not rl_codigo:
            erros.append("Para Projetos, o código RL é obrigatório.")
        elif len(rl_codigo) > 100:
            erros.append("O código RL deve ter no máximo 100 caracteres.")
        # Caracteres permitidos: letras, números, espaços e símbolos comuns (evita controle/injeção)
        elif not re.match(r"^[\w\s\-./(),]+$", rl_codigo, re.UNICODE):
            erros.append(
                "O código RL permite letras, números e os caracteres: espaço, - _ . / ( ) ,"
            )

    # 3. Validação de Arquivos (se houver uploads): extensão + magic bytes + tamanho
    lista_efetiva = [a for a in (arquivos or []) if a and getattr(a, "filename", "")]
    for arquivo in lista_efetiva:
        if not _arquivo_permitido(arquivo.filename):
            erros.append(
                f"{arquivo.filename}: Formato de arquivo inválido. "
                f"Permitidos: {', '.join(sorted(_get_extensoes_permitidas()))}"
            )
            continue
        ok_tam, msg_tam = _validar_tamanho(arquivo)
        if not ok_tam:
            erros.append(msg_tam)
            continue
        ok_cont, msg_cont = _arquivo_conteudo_permitido(arquivo)
        if not ok_cont:
            erros.append(msg_cont or "Conteúdo do arquivo não corresponde ao formato declarado.")

    # 4. Validação de links externos OneDrive/SharePoint
    if links_externos:
        erros.extend(validar_links_externos(links_externos))

    return erros


MAX_OBSERVADORES = 5


def validar_observadores(
    observadores: list,
    solicitante_id: str,
) -> list[str]:
    """Valida lista de observadores (em cópia) antes de persistir.

    Regras:
    - Máximo MAX_OBSERVADORES (5) observadores por chamado.
    - Solicitante não pode ser observador do próprio chamado.
    - Cada observador deve ter usuario_id presente.
    - Duplicatas são ignoradas silenciosamente (sem erro).

    Returns:
        Lista de mensagens de erro; vazia se tudo OK.
    """
    erros: list[str] = []
    if not observadores:
        return erros

    vistos: set[str] = set()
    ids_validos: list[str] = []

    for obs in observadores:
        uid = (obs.get("usuario_id") if isinstance(obs, dict) else None) or ""
        if not uid:
            erros.append("Observador sem usuario_id informado.")
            continue
        if uid in vistos:
            continue  # deduplicação silenciosa
        vistos.add(uid)
        ids_validos.append(uid)

    if solicitante_id in vistos:
        erros.append("O solicitante não pode ser observador do próprio chamado.")

    if len(vistos) > MAX_OBSERVADORES:
        erros.append(f"Máximo de {MAX_OBSERVADORES} observadores por chamado.")

    return erros
