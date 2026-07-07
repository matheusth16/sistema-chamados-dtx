---
name: DTX Service Portal
description: Sistema interno de chamados da DTX Aerospace — visibilidade em tempo real para escritório e chão de fábrica, tema único light
colors:
  dtx-900: "#070f1d"
  dtx-800: "#0c1931"
  dtx-700: "#13274b"
  dtx-600: "#1d3b72"
  dtx-500: "#284e95"
  dtx-400: "#3f70ca"
  dtx-300: "#81a0da"
  dtx-200: "#c1d0ec"
  dtx-100: "#e4eaf6"
  dtx-50: "#f4f6fb"
  status-open: "#78350F"
  status-open-bg: "#FEF3C7"
  status-active: "#1E3A8A"
  status-active-bg: "#EFF6FF"
  status-done: "#065F46"
  status-done-bg: "#ECFDF5"
  status-cancelled: "#9F1239"
  status-cancelled-bg: "#FFF1F2"
  status-pending: "#475569"
  status-pending-bg: "#F8FAFC"
  surface-canvas: "#F2F4F7"
  surface-base: "#FFFFFF"
  surface-raised: "#E8ECF2"
  surface-border: "#C4CDD9"
  surface-muted: "#8B9EC0"
typography:
  display:
    fontFamily: "Manrope, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Manrope, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Manrope, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 800
    letterSpacing: "0.08em"
  mono:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.75rem"
    fontWeight: 500
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "24px"
  badge: "4px"
  full: "9999px"
spacing:
  row: "1rem"
  card-padding: "1rem"
components:
  button-primary:
    backgroundColor: "{colors.dtx-600}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.dtx-700}"
  button-secondary:
    backgroundColor: "#FFFFFF"
    textColor: "#374151"
    rounded: "{rounded.md}"
    height: "36px"
  button-danger:
    backgroundColor: "#FFFFFF"
    textColor: "#E11D48"
    rounded: "{rounded.md}"
    height: "36px"
  badge-status:
    rounded: "{rounded.badge}"
    padding: "2px 8px"
    typography: "{typography.label}"
  card:
    backgroundColor: "{colors.surface-base}"
    rounded: "{rounded.md}"
---

# Design System: DTX Service Portal

## 1. Overview

**Norte Criativo: "A Torre de Controle DTX"**

O DTX Service Portal é o sistema de chamados internos da DTX Aerospace — uma operação aeroespacial, não uma startup de SaaS. O visual existe para transmitir **confiança, controle e eficiência**: cada chamado é um sinal que precisa ser visto, classificado e resolvido sem ambiguidade, por dois públicos com necessidades físicas opostas. No escritório (supervisores, admins, analistas) e no chão de fábrica (mecânicos, engenheiros), o sistema se comporta como um painel de controle Swiss-industrial: hierarquia densa, tipografia bold, grid rígido. Tema único, light — acessibilidade pro chão de fábrica vem de contraste alto e tipografia funcional dentro do próprio tema, não de um toggle de tema.

O sistema rejeita explicitamente a estética de SaaS genérico: nada de cards flutuantes sem propósito, paleta usada como decoração, ou flat design sem hierarquia. Cor é dado — o Azul DTX e as cores semânticas de status aparecem onde há ação ou significado, nunca como estilo gratuito.

**Key Characteristics:**
- Ancorado em uma única cor de marca (#13274b, "Azul DTX") expressa como uma escala completa de 9 tons.
- Tipografia unificada: Manrope para hierarquia de página e corpo/dados densos (peso é quem separa título de dado, não a família), JetBrains Mono reservado para identificadores técnicos.
- Elevação real (sombras + gradientes), não flat design — mas aplicada com critério: cards em repouso, gradiente reservado para a ação primária.
- Densidade alta nas tabelas de chamados (telemetria), respiro generoso nas páginas de navegação.
- Tema único light — tokens de cor em `:root`, sem variante dark, sem lógica condicional de tema nos componentes.

## 2. Colors

A paleta é Restrita por padrão: o Azul DTX domina apenas onde há ação ou marca estrutural (navbar, botão primário, foco); o resto da superfície é neutro frio. Cor de status é a única exceção deliberada — ali, cor É o dado.

### Primary
- **Azul DTX** (`#13274b` / dtx-700): a cor da marca. Reservada para elementos estruturais — fundo da navbar, divisórias de seção. 14.8:1 de contraste contra branco.
- **Azul DTX — Ação** (`#284e95` / dtx-500): botão primário. 8:1 de contraste, AA garantido.
- **Azul DTX — Hover** (`#1d3b72` / dtx-600): hover do botão primário e estado ativo de navegação. 10.9:1 de contraste.
- **Azul DTX — Acento** (`#3f70ca` / dtx-400): anéis de foco, hovers sutis, avatar/ícones — acento mais claro, não usado para texto de corpo.

### Secondary — Vocabulário Semântico de Status
A segunda camada de cor não é decorativa: é o vocabulário de estado dos chamados, idêntico em ambos os temas (apenas a luminância muda).
- **Âmbar Aberto** (`#78350F` texto / `#FEF3C7` fundo): chamado aguardando atendimento.
- **Azul Em Atendimento** (`#1E3A8A` texto / `#EFF6FF` fundo): chamado em andamento.
- **Verde Concluído** (`#065F46` texto / `#ECFDF5` fundo): chamado resolvido.
- **Rosa Cancelado** (`#9F1239` texto / `#FFF1F2` fundo): chamado cancelado.
- **Cinza Pendente** (`#475569` texto / `#F8FAFC` fundo): estado neutro/indefinido, fallback.

### Neutral
- **Canvas** (`#F2F4F7`): fundo geral da aplicação — cinza-azulado frio, "papel técnico aeroespacial".
- **Base** (`#FFFFFF`): cards, modais, formulários.
- **Raised** (`#E8ECF2`): cabeçalhos de tabela, seções elevadas.
- **Border** (`#C4CDD9`): divisórias estruturais.
- **Muted** (`#8B9EC0`): texto desativado, placeholders.

### Named Rules
**A Regra da Cor-Como-Dado.** O Azul DTX nunca decora — ele marca ação (botão primário), seleção (linha ativa, foco) ou estrutura de marca (navbar). Se uma cor não está comunicando estado ou hierarquia, ela é cinza neutro.

**A Regra do Token Único.** Todo token de cor vive em `:root` sob um nome de variável CSS semântico (`--color-dtx-*`, `--color-surface-*`, `--color-status-*`). Nenhum componente hardcoda hex; ele só referencia o token — isso mantém a paleta trocável num só lugar, mesmo sem variante de tema.

## 3. Typography

**Fonte de Destaque:** Manrope, peso 700/800 (com fallback sans-serif)
**Fonte de Corpo:** Manrope, peso 400/500 (com fallback sans-serif)
**Fonte de Identificadores Técnicos:** JetBrains Mono (com fallback monospace) — carregada, mas hoje subutilizada (ver Do's e Don'ts)

**Caráter:** fonte única (Manrope), geométrica e arredondada nos terminais — hierarquia vem de peso e tamanho, não da troca de família. Substituiu o par Plus Jakarta Sans + Inter a partir do redesign visual iniciado em 2026-07 (primeira página convertida: login). JetBrains Mono existe para dar precisão técnica a IDs e timestamps, mas a aplicação ainda é inconsistente no código atual.

### Hierarchy
- **Display** (font-semibold 600, `text-2xl`/24px, tracking-tight): título de página (`_page_header.html`). No hero do login, escala para `text-4xl`/`text-5xl` font-black — único lugar onde o sistema usa peso máximo, reservado para o momento de entrada.
- **Title** (font-bold, `text-base`–`text-xl`): títulos de card, cabeçalhos de seção.
- **Body** (font-normal/medium, `text-sm`/14px, line-height 1.5): texto corrido, células de tabela, formulários. Compatível com densidade alta — tabelas correm bem além de 75ch quando necessário.
- **Label** (font-black 900, `text-[10px]`–`text-xs`, tracking-widest, uppercase): badges de status, rótulo "DIGITAL ANDON" na navbar, cabeçalhos de coluna. A camada "micro-tipografia" do sistema — precisão, não decoração.
- **Mono** (font-medium, `text-xs`, JetBrains Mono): reservado para identificadores técnicos. Atualmente presente em 5 templates administrativos; **ainda não aplicado ao número do chamado na tabela do dashboard**, que hoje usa `font-black` em Manrope.

### Named Rules
**A Regra Macro/Micro.** Hierarquia de página usa peso (Manrope bold/black); hierarquia de dado usa tamanho + tracking (Manrope uppercase tracking-widest). As duas nunca se misturam no mesmo elemento.

## 4. Elevation

O sistema é **em camadas (layered)**, não flat. Sombras têm papel estrutural: cards descansam levemente acima do canvas, e o botão primário ganha profundidade tátil via gradiente + highlight interno — não para decoração, mas para sinalizar "isto é a ação principal desta tela".

### Shadow Vocabulary
- **dtx-sm** (`0 1px 2px 0 rgb(0 0 0 / 0.05)`): elevação mínima — inputs, elementos quase no plano do canvas.
- **dtx** (`0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.05)`): elevação padrão de `.dtx-card` — cards, dropdowns, toasts.
- **dtx-md** (`0 4px 12px 0 rgb(0 0 0 / 0.10), 0 2px 4px -1px rgb(0 0 0 / 0.06)`): elevação de destaque — `.dtx-card-raised`, modais.
- **Botão primário** (`linear-gradient(180deg, dtx-400→dtx-700) + box-shadow 0 1px 3px rgb(0 0 0 / 0.3) + inset 0 1px 0 rgb(255 255 255 / 0.1)`): a única superfície com gradiente real no sistema — reservada para a ação primária (submit de login, CTAs principais).

### Named Rules
**A Regra do Destaque Único.** Gradiente é reservado para no máximo uma ação por tela — o botão primário. Cards, badges e navegação secundária permanecem em cor sólida.

## 5. Components

### Buttons
- **Forma:** `rounded-dtx-md` (8px), altura 36px (`md`) ou 32px (`sm`).
- **Primário:** `bg-dtx-600` → hover `bg-dtx-700` → active `bg-dtx-800`. Texto branco, `font-medium`. No login, variante elevada com gradiente (ver Elevation).
- **Secundário:** fundo branco, borda `surface-muted`, texto `gray-700`; hover `surface-raised`.
- **Danger:** fundo branco, borda rosa-200, texto rosa-600; hover rosa-50.
- **Ghost:** sem fundo nem borda; hover `surface-raised`.
- **Foco:** todos os botões usam `focus-visible:outline-2 outline-offset-2 outline-dtx-600` — nunca `outline: none` sem substituto.

### Status Badges
- **Forma:** retângulo com `rounded` (4px) — não pílula. Borda 1px na cor do estado, fundo e texto pareados semanticamente (ver Colors → Secondary).
- **Tamanho:** `text-xs`, padding `px-2 py-0.5` (sm) ou `px-2.5 py-1` (md).
- **Estado pendente de implementação:** o plano original previa um indicador pulsante (`animate-ping`) no badge "Aberto" para chamar atenção visual; **não está implementado no código atual**.

### Cards / Containers
- **Canto:** `rounded-dtx-md` (8px) nas superfícies de densidade (tabelas, dashboards, formulários administrativos).
- **Canto — superfícies "bento" (redesign visual):** `rounded-dtx-xl` (24px), com sub-blocos internos em `rounded-dtx-lg` (12px). Introduzido em 2026-07, hoje em `login.html` e `formulario.html`; demais páginas migram pra esse padrão conforme o rollout avança (ver plano de redesign).
- **Fundo:** `surface-base` (branco).
- **Sombra:** `dtx` em repouso; `.dtx-card-raised` adiciona `border-top: 3px solid dtx-500` + sombra `dtx-md` para cards de destaque/métrica.
- **Borda:** 1px `surface-border`.
- **Padding interno:** `1rem` (16px) como base.

### Inputs / Fields
- **Estilo:** `.dtx-input` — borda 1px `surface-border`, fundo `surface-base`, `rounded-dtx-md`, altura `h-11` (44px, touch-friendly).
- **Foco:** borda muda para `dtx-500`, anel de 3px em `dtx-400` a 20% de opacidade via `color-mix`.
- **Placeholder:** cor `surface-muted`.

### Navigation
- **Navbar:** fundo sólido `nav-bg` (`#13274b`), sticky, `z-nav`. Links inativos em `nav-text` (azul-acinzentado), ativos em branco sobre `bg-white/15` com borda `white/20`.
- **Hover de link:** `bg-white/10`, sem mudança de cor abrupta.
- **Mobile/dropdown:** menu hambúrguer volta a um fundo claro (`surface-base`) para legibilidade, mesmo com a navbar escura — transição intencional de contexto (a navbar é estruturalmente escura por design, não é "dark mode").
- **Toque:** todo alvo interativo da navbar tem `min-w-[44px] min-h-[44px]`.

### Tabelas (componente de assinatura)
A tabela de chamados é o componente mais denso do sistema — funciona como telemetria, não como lista genérica. Cabeçalho `sticky` em `surface-raised`, linhas com hover em `dtx-accent-muted` (mix de 6% do azul sobre o fundo). Uma categoria (`Projetos`) recebe destaque visual via fundo rosa tintado (sem faixa lateral — ver Do's e Don'ts).

## 6. Do's and Don'ts

### Do:
- **Do** usar o token semântico em `:root` pra qualquer cor nova — nunca um hex hardcoded solto no template.
- **Do** reservar gradiente para uma única ação primária por tela (Regra do Destaque Único).
- **Do** usar `.dtx-card-raised` (borda superior de 3–4px na cor do destaque, cantos superiores retos via `rounded-t-none`/`rounded-b-*`) quando um card ou callout precisa de ênfase — esse é o padrão sancionado de "card importante", aplicado em `_stat_card.html`, `_filter_panel.html`, `historico.html`, `visualizar_chamado.html` e no flash toast.
- **Do** usar fundo tintado (sem borda) para sinalizar uma linha de tabela (`<tr>`) — é o padrão em `_ticket_row_dashboard.html`, `_ticket_row_meus_chamados.html` e `_rl_header.html` para a categoria "Projetos"/agrupamento RL.
- **Do** usar a escala semântica de z-index do `tailwind.config.js` (`z-sticky: 10`, `z-nav: 20`, `z-dropdown: 30`, `z-modal: 40`, `z-toast: 50`) para qualquer elemento novo com posicionamento fixo/sticky/absoluto — nunca um valor `z-[N]` arbitrário. O link de skip-to-content é a única exceção deliberada, em `z-[9999]`, pois deve renderizar acima de absolutamente tudo, inclusive toasts.
- **Do** manter alvos de toque ≥44×44px em qualquer elemento interativo da navbar e células de tabela com ação.
- **Do** testar toda decisão visual pros dois públicos — escritório e chão de fábrica — dentro do único tema light, verificando contraste em condições de luz industrial antes de considerar um componente pronto.

### Don't:
- **Don't** reintroduzir dark mode (`html.dark`, toggle, `prefers-color-scheme`). *(Removido em 2026-07-01 por decisão de produto: sistema é light-only; acessibilidade pro chão de fábrica vem de contraste alto dentro do próprio tema claro — ver PRODUCT.md.)*
- **Don't** usar `border-left`/`border-right` colorido como faixa de destaque — é a versão lateral do `.dtx-card-raised` e está banida pelo sistema. *(Resolvido em 2026-07-01: as 8 ocorrências foram migradas para borda-superior em boxes/cards ou fundo tintado em linhas de tabela — ver Do's acima.)*
- **Don't** deixar a paleta "conservadora demais" — o Azul DTX hoje só aparece em `dtx-600`/navbar na maior parte das telas; cor de status deve carregar mais peso informativo nas tabelas e dashboards, não só nos badges.
- **Don't** usar valores de z-index arbitrários (`z-[N]`) quando a escala semântica existe. *(Resolvido em 2026-07-01: navbar, dropdowns, toasts, banners, modais e cabeçalhos sticky de tabela foram migrados para `z-sticky`/`z-nav`/`z-dropdown`/`z-modal`/`z-toast`. Como parte do fix, os banners de web push — antes em `z-[190]`, abaixo dos dropdowns da navbar — foram promovidos para o mesmo nível `z-toast` das flash messages, corrigindo uma inconsistência real onde dois elementos igualmente "toast" tinham prioridades de empilhamento diferentes.)*
- **Don't** carregar JetBrains Mono sem aplicá-la de forma consistente — hoje a fonte está no `<link>` do `base.html` e usada em apenas 5 templates administrativos; ou ela vira o padrão para todo ID/timestamp técnico (incluindo o número do chamado na tabela do dashboard), ou o `<link>` deve ser removido para não pagar o custo de carregamento de uma fonte não utilizada.
- **Don't** referenciar o nome de produto "Digital Andon" em código novo — o nome foi descontinuado; o nome oficial atual é **DTX Service Portal**. *(Resolvido: a navbar (`components/navbar.html`) já exibe "Service Portal" como rótulo da marca.)*
- **Don't** parecer um SaaS genérico: nada de cards flutuantes sem propósito, paleta usada como decoração, ou flat design sem hierarquia (anti-referência direta do PRODUCT.md).
