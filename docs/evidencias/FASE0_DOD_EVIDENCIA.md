# FASE 0 — Documentação e ADR: Evidência DoD

| Campo | Valor |
|---|---|
| **Escopo** | Fase 0 — ADR-004, plano detalhado TDD, MATRIZ_ROTAS rascunhada, decisões fechadas |
| **Data de execução** | 2026-06-24 |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Status final** | **DoD 100% — APROVADO** |

---

## 1. Artefatos entregues

| Artefato | Localização | Descrição |
|---|---|---|
| ADR-004 | `docs/adr/004-escalonamento-sla-gerencial.md` | Decisão de arquitetura: supervisor_ids_com_acesso, business_time DTX, Escada A sem distinção de categoria, perfil gestor |
| Plano TDD | `docs/plans/2026-06-23-escalonamento-sla.md` | Spec detalhada, tasks bite-sized, critérios de aceite por fase |
| Plano Cursor | `.cursor/plans/escalonamento_e_sla_dtx_d3e9e5bb.plan.md` | Roadmap de fases + status |
| MATRIZ atualizada | `docs/MATRIZ_ROTAS_PERFIL.md` | Novas rotas de escalonamento incluídas |

---

## 2. Decisões fechadas no ADR

| # | Decisão | Consequência |
|---|---------|--------------|
| 1 | `supervisor_ids_com_acesso` (campo desnormalizado) | Permite `array_contains` no Firestore sem índice composto |
| 2 | Timezone BRT (`America/Sao_Paulo`) | Todos os cálculos de tempo útil usam `zoneinfo.ZoneInfo("America/Sao_Paulo")` |
| 3 | Escada A sem distinção de categoria | Mesmo timer (+1h/+2h/+3h/+4h úteis) para Projetos e demais |
| 4 | `GESTOR_EMAILS` em `config.py` | Nível → e-mail fixo; coleção Firestore fica como opção Fase 6+ |
| 5 | Janela útil DTX: 07:00–11:30 / 13:00–16:30, seg–sex | Almoço pausa o relógio; teto 16:30 evita e-mail após saída da produção |
| 6 | Sábados e domingos excluídos v1 | Flag `SLA_INCLUI_FIM_DE_SEMANA` reservada para exceções futuras |

---

## 3. Critérios de aceite — verificados

- [x] ADR-004 status `Accepted`
- [x] Plano TDD com critérios de aceite por fase (Fases 1–8)
- [x] Decisões de timezone, `array_contains`, `GESTOR_EMAILS`, Escada A documentadas
- [x] MATRIZ_ROTAS_PERFIL.md com novas rotas planejadas
