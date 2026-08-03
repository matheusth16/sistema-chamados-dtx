"""Tabelas de categorias (Setor/Gate/Impacto) — Fase 2, Marco 3."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CategoriaSetorRow(Base):
    __tablename__ = "categorias_setores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome_pt: Mapped[str] = mapped_column(Text, nullable=False)
    nome_en: Mapped[str | None] = mapped_column(Text)
    nome_es: Mapped[str | None] = mapped_column(Text)
    descricao_pt: Mapped[str | None] = mapped_column(Text)
    descricao_en: Mapped[str | None] = mapped_column(Text)
    descricao_es: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_criacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CategoriaGateRow(Base):
    __tablename__ = "categorias_gates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome_pt: Mapped[str] = mapped_column(Text, nullable=False)
    nome_en: Mapped[str | None] = mapped_column(Text)
    nome_es: Mapped[str | None] = mapped_column(Text)
    descricao_pt: Mapped[str | None] = mapped_column(Text)
    descricao_en: Mapped[str | None] = mapped_column(Text)
    descricao_es: Mapped[str | None] = mapped_column(Text)
    gate_pai: Mapped[str | None] = mapped_column(Text)
    etapa: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_criacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CategoriaImpactoRow(Base):
    __tablename__ = "categorias_impactos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome_pt: Mapped[str] = mapped_column(Text, nullable=False)
    nome_en: Mapped[str | None] = mapped_column(Text)
    nome_es: Mapped[str | None] = mapped_column(Text)
    descricao_pt: Mapped[str | None] = mapped_column(Text)
    descricao_en: Mapped[str | None] = mapped_column(Text)
    descricao_es: Mapped[str | None] = mapped_column(Text)
    nivel: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cor: Mapped[str] = mapped_column(String(32), nullable=False, default="gray")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_criacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
