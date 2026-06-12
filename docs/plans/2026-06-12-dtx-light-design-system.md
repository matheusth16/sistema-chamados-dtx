# DTX Light Enterprise — Design System (Fase 0)

Data: 2026-06-12
Plano: `.cursor/plans/redesign_visual_dtx_14388227.plan.md`

---

## Decisoes de design

### Acento unico: DTX Blue `#1e4a8c`

Derivado da identidade visual DTX Aerospace. Unico tom de acento permitido.
Variacoes (50-900) disponiveis como `dtx-{shade}` no Tailwind.

### Superficies (light-only)

| Token | Valor | Uso |
|-------|-------|-----|
| `surface-canvas` | `#FBFBFA` | Fundo de pagina (`body`) |
| `surface-base` | `#FFFFFF` | Cards, paineis, modais |
| `surface-raised` | `#F5F5F4` | Hover, zebra, inputs disabled |
| `surface-border` | `#EAEAEA` | Bordas default (1px) |
| `surface-muted` | `#D1D5DB` | Bordas mais fortes, inputs |

`color-scheme: light` declarado em `html` — sem suporte a dark mode.

### Status badges — pasteis semanticos

| Status | Bg | Texto | Borda |
|--------|----|-------|-------|
| Aberto | amber-50 `#FEF3C7` | `#92400E` | `#FDE68A` |
| Em Atendimento | blue-50 `#EFF6FF` | `#1D4ED8` | `#BFDBFE` |
| Concluido | emerald-50 `#ECFDF5` | `#065F46` | `#A7F3D0` |
| Cancelado | rose-50 `#FFF1F2` | `#9F1239` | `#FECDD3` |
| Pendente/default | slate-50 `#F8FAFC` | `#475569` | `#E2E8F0` |

Perfis: admin = dtx-blue, supervisor = violet, solicitante = gray.

### Z-index nomeada

| Nome | Valor | Onde usar |
|------|-------|-----------|
| `z-nav` | 10 | Navbar fixa |
| `z-dropdown` | 20 | Menus, selects |
| `z-modal` | 30 | Modais, dialogs |
| `z-toast` | 50 | Flash messages, toasts |

### Border radius

| Classe Tailwind | Valor | Uso |
|-----------------|-------|-----|
| `rounded-dtx-sm` | 6px | Badges, inputs, botoes sm |
| `rounded-dtx-md` | 8px | Cards, botoes md (padrao) |
| `rounded-dtx-lg` | 12px | Modais, paineis grandes |

### Sombras

Minimas por principio minimalist-ui:
- `shadow-dtx-sm`: `0 1px 2px 0 rgb(0 0 0 / 0.05)` — cards em repouso
- `shadow-dtx`: `0 1px 3px 0 rgb(0 0 0 / 0.08)` — elementos elevados

Sem `shadow-lg`, `backdrop-blur` ou glassmorphism.

---

## Macros Jinja (app/templates/components/)

| Arquivo | Macro | Parametros principais |
|---------|-------|-----------------------|
| `_page_header.html` | `page_header(title, subtitle)` | `{% call %}` para acoes |
| `_stat_card.html` | `stat_card(label, value, sublabel, variant)` | variant: default/open/active/done/cancelled |
| `_status_badge.html` | `status_badge(status, size)` | status: string PT + perfil |
| `_filter_panel.html` | `filter_panel(title, collapsible, open)` | `{% call %}` para conteudo |
| `_empty_state.html` | `empty_state(title, description, action_label, action_url, icon)` | icon: inbox/chart/search/users/check |
| `_btn.html` | `btn(label, variant, type, href, icon_only, aria_label, extra_class, disabled, size)` | `{% call %}` para icones |

### Padrao de importacao

```jinja
{% from 'components/_status_badge.html' import status_badge %}
{% from 'components/_stat_card.html' import stat_card %}
{% from 'components/_page_header.html' import page_header %}
{% from 'components/_btn.html' import btn %}
{% from 'components/_empty_state.html' import empty_state %}
```

### Exemplos de uso

```jinja
{# Page header simples #}
{{ page_header("Gerenciamento", subtitle="Chamados em aberto") }}

{# Page header com acao #}
{% call page_header("Usuarios") %}
  {{ btn("Novo usuario", href=url_for('main.novo_usuario')) }}
{% endcall %}

{# Stat cards #}
<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
  {{ stat_card("Total", total) }}
  {{ stat_card("Abertos", abertos, variant="open") }}
  {{ stat_card("Em Atendimento", em_atendimento, variant="active") }}
  {{ stat_card("Concluidos", concluidos, variant="done") }}
</div>

{# Status badge #}
{{ status_badge(chamado.status) }}
{{ status_badge(usuario.perfil) }}

{# Filter panel #}
{% call filter_panel("Filtros", collapsible=true) %}
  <div class="grid grid-cols-2 gap-3">
    <div>
      <label class="dtx-label">Status</label>
      <select name="status" class="dtx-select">...</select>
    </div>
  </div>
{% endcall %}

{# Empty state #}
{{ empty_state(
     "Nenhum chamado",
     description="Crie um novo chamado para comecar.",
     action_label="Novo chamado",
     action_url=url_for('main.formulario')
   ) }}

{# Botoes #}
{{ btn("Salvar", type="submit") }}
{{ btn("Cancelar", variant="secondary", href=url_for('main.dashboard')) }}
{% call btn(variant="secondary", icon_only=true, aria_label="Fechar") %}
  <svg class="h-4 w-4" .../>
{% endcall %}
```

---

## Restricoes (nao negociaveis)

- Sem emojis em templates ou JS
- Sem `dark:` classes ou variaveis de tema escuro
- Sem navbar com fundo escuro (`#0b1b3d` banido)
- Sombras maximas: `shadow-dtx` (sem `shadow-xl` ou maiores)
- Animacoes: max 200ms, apenas `transform`/`opacity`, respeitar `prefers-reduced-motion`
- Touch targets: minimo 44px (h-9 = 36px + padding vertical garante 44px de area)

---

## Proximos passos

**Fase 1:** `base.html` + `navbar.html` — navbar light, nav por perfil, flash toasts.
