# DESIGN.md — Plano de Redesign Visual: DTX Digital Andon

> Documento vivo. Atualizar quando tokens, componentes ou decisões mudarem.

---

## 1. Estado Atual — Diagnóstico

### O que funciona bem
- Design system com tokens CSS (`--color-dtx-*`, `--color-surface-*`) bem definidos
- Tipografia dupla: Inter (corpo) + Plus Jakarta Sans (headings) — boa escolha
- Status badges semânticos com cores bem diferenciadas
- Navbar sticky responsiva com dropdowns animados
- Focus rings consistentes com `dtx-600`

### Pontos de melhoria identificados
| Área | Problema |
|---|---|
| Navbar | Plana, fundo branco sem distinção visual do conteúdo |
| Login | Card simples sem identidade — página de entrada sem impacto |
| Dashboard header | Genérico, sem hierarquia visual clara |
| Cards / Tabelas | Contraste muito baixo — tudo "flutua" no branco |
| Cores | Paleta usada de forma muito conservadora: apenas `dtx-600` aparece |
| Botões | Flat, sem gradiente ou micro-elevação |
| Formulários | Inputs básicos sem personalidade |
| Espaçamento | Inconsistente entre páginas — algumas muito densas |
| Fundo | `#FBFBFA` (surface-canvas) quase indistinguível do branco |

---

## 2. Direção de Design

### Tema: "Industrial Precision"
Contexto: sistema interno de uma empresa aeroespacial. O visual deve transmitir
**confiança, controle e eficiência** — sem parecer um SaaS genérico.

**Referências de estilo:**
- Linear.app — hierarquia densa, dark sidebar contrastante
- Vercel Dashboard — superfícies sutilmente diferenciadas, tipografia bold
- Notion — cards com profundidade real, espaçamento generoso

**Princípios do redesign:**
1. **Contraste com propósito** — cada superfície deve ter uma razão para existir
2. **Cor como dado** — o azul DTX aparece onde há ação ou destaque, não decoração
3. **Tipografia dominante** — headings mais pesados, maior hierarquia
4. **Elevação explícita** — sombras mais pronunciadas em elementos interativos
5. **Densidade equilibrada** — mais breathing room nas páginas, mais compacto nas tabelas

---

## 3. Contexto Dual — Dois Públicos, Dois Ambientes

O skill `industrial-brutalist-ui` define dois arquétipos que mapeiam exatamente os dois grupos de usuários deste sistema:

| Arquétipo | Público | Ambiente | Modo preferencial |
|---|---|---|---|
| **Swiss Industrial Print** | Gerentes, supervisores, analistas, assistentes | Escritório, sala de reunião | Light mode |
| **Tactical Telemetry** | Mecânicos, engenheiros | Chão de fábrica, iluminação industrial | Dark mode |

O design deve atender os dois — sem sacrificar nenhum. O toggle light/dark não é um "nice to have": é a feature principal de acessibilidade deste sistema.

**Princípios retirados do skill para este projeto:**
- Alta densidade de dados com hierarquia clara (ticket list = telemetria)
- Contraste extremo — leitura a distância ou com luvas no dark mode
- Tipografia funcional, não decorativa — IDs de chamados em monospace
- Grade rígida e compartimentada — cada célula da tabela é um campo de dado

---

## 4. Paleta de Cores — DTX Blue #13274b como âncora

### Escala DTX Blue (gerada a partir de #13274b como dtx-700)

```
dtx-50:  #f4f6fb  ← fundo de seleção, hover bg
dtx-100: #e4eaf6  ← border em hover
dtx-200: #c1d0ec  ← border passivo
dtx-300: #81a0da  ← ícones secundários, desativado
dtx-400: #3f70ca  ← primary em dark mode (4.79:1 em fundo escuro)
dtx-500: #284e95  ← primary em light mode (8.03:1 com branco)
dtx-600: #1d3b72  ← hover do primary (10.93:1 com branco)
dtx-700: #13274b  ← MARCA DTX — navbar, headers estruturais (14.79:1)
dtx-800: #0c1931  ← active/pressed, texto em fundos claros
dtx-900: #070f1d  ← fundo máximo dark, texto sobre cores claras
```

> `dtx-500` (#284e95) é o botão primário no light mode — WCAG AA garantido (8:1).
> `dtx-400` (#3f70ca) é o botão primário no dark mode — legível em fundo escuro.
> `dtx-700` (#13274b) é reservado para elementos estruturais: navbar, cabeçalho de seção, bordas de separação.

---

### Tokens Light Mode — "Swiss Industrial Precision"
Derivado do arquétipo **Swiss Industrial Print** do skill, adaptado para manter a marca DTX.

```css
:root {
  /* Escala DTX Blue */
  --color-dtx-50:  #f4f6fb;
  --color-dtx-100: #e4eaf6;
  --color-dtx-200: #c1d0ec;
  --color-dtx-300: #81a0da;
  --color-dtx-400: #3f70ca;
  --color-dtx-500: #284e95;   /* primary action */
  --color-dtx-600: #1d3b72;   /* hover */
  --color-dtx-700: #13274b;   /* marca / estrutural */
  --color-dtx-800: #0c1931;
  --color-dtx-900: #070f1d;

  /* Superfícies — substrato "papel técnico aeroespacial" */
  --color-surface-canvas:  #F2F4F7;   /* fundo geral: cinza-azulado frio */
  --color-surface-base:    #FFFFFF;   /* cards, modais */
  --color-surface-raised:  #E8ECF2;   /* headers de tabela, seções elevadas */
  --color-surface-border:  #C4CDD9;   /* divisórias estruturais — mais visíveis */
  --color-surface-muted:   #8B9EC0;   /* texto desativado */

  /* Texto */
  --color-text-primary:   #1A1E2E;    /* quase-preto com tint navy */
  --color-text-secondary: #3D4A63;    /* corpo de texto, metadados */
  --color-text-muted:     #6B7FA0;    /* placeholders, labels opcionais */

  /* Navbar — DTX Navy sólido */
  --color-nav-bg:       #13274b;      /* marca como fundo */
  --color-nav-border:   #1d3b72;
  --color-nav-text:     #8BA8CC;      /* links inativos */
  --color-nav-active:   #FFFFFF;
  --color-nav-accent:   #3f70ca;      /* dtx-400 como highlight na navbar */

  /* Alerta / Crítico — Aviation Red (do skill) */
  --color-alert:        #C62828;
  --color-alert-bg:     #FFF0F0;
  --color-alert-border: #EF9A9A;

  /* Gradiente hero */
  --gradient-dtx: linear-gradient(135deg, #070f1d 0%, #13274b 55%, #284e95 100%);

  /* Status (mantidos, apenas ajustados para o novo canvas) */
  --color-status-open-bg:          #FEF3C7;
  --color-status-open-text:        #78350F;
  --color-status-open-border:      #FDE68A;
  --color-status-active-bg:        #EFF6FF;
  --color-status-active-text:      #1E3A8A;
  --color-status-active-border:    #BFDBFE;
  --color-status-done-bg:          #ECFDF5;
  --color-status-done-text:        #065F46;
  --color-status-done-border:      #A7F3D0;
  --color-status-cancelled-bg:     #FFF1F2;
  --color-status-cancelled-text:   #9F1239;
  --color-status-cancelled-border: #FECDD3;
  --color-status-pending-bg:       #F8FAFC;
  --color-status-pending-text:     #475569;
  --color-status-pending-border:   #E2E8F0;
}
```

---

### Tokens Dark Mode — "Field Operations / Tactical"
Derivado do arquétipo **Tactical Telemetry** do skill. Projetado para chão de fábrica:
alto contraste, mínimo brilho, dados legíveis a distância.

```css
html.dark {
  color-scheme: dark;

  /* Superfícies — CRT desativado, não preto puro */
  --color-surface-canvas:  #0D1117;   /* fundo geral: navy-black */
  --color-surface-base:    #131C27;   /* cards e painéis */
  --color-surface-raised:  #1E2D3F;   /* headers de seção, elevated */
  --color-surface-border:  #2A3A50;   /* divisórias */
  --color-surface-muted:   #3D5068;   /* elementos desativados */

  /* Texto — fósforo branco-frio */
  --color-text-primary:   #E8EDF5;    /* texto principal */
  --color-text-secondary: #8B9EC0;    /* metadados, secondary */
  --color-text-muted:     #4A5E78;    /* desativado */

  /* DTX Blue no dark — clarear para contrastar */
  --color-dtx-50:  #0D1F3C;
  --color-dtx-100: #162740;
  --color-dtx-200: #1E3554;
  --color-dtx-300: #2A4A72;
  --color-dtx-400: #3f70ca;   /* primary action no dark */
  --color-dtx-500: #4A80D9;   /* hover */
  --color-dtx-600: #60A5FA;   /* destaques, links */
  --color-dtx-700: #93C5FD;   /* texto azul claro */
  --color-dtx-800: #BFDBFE;
  --color-dtx-900: #DBEAFE;

  /* Navbar no dark — continua navy, mas levemente mais claro que o canvas */
  --color-nav-bg:       #0D1117;      /* se funde com o fundo — sem divisória dura */
  --color-nav-border:   #1E2D3F;
  --color-nav-text:     #6B8BAA;
  --color-nav-active:   #E8EDF5;
  --color-nav-accent:   #3f70ca;

  /* Alerta — vermelho aeronáutico, mais brilhante no dark */
  --color-alert:        #EF4444;
  --color-alert-bg:     #1A0808;
  --color-alert-border: #7F1D1D;

  /* Gradiente hero dark */
  --gradient-dtx: linear-gradient(135deg, #020810 0%, #0D1117 55%, #13274b 100%);

  /* Status no dark */
  --color-status-open-bg:          #2D1D00;
  --color-status-open-text:        #FDE68A;
  --color-status-open-border:      #78350F;
  --color-status-active-bg:        #0D1F3C;
  --color-status-active-text:      #93C5FD;
  --color-status-active-border:    #1E3A5F;
  --color-status-done-bg:          #052E16;
  --color-status-done-text:        #86EFAC;
  --color-status-done-border:      #14532D;
  --color-status-cancelled-bg:     #2D0A0F;
  --color-status-cancelled-text:   #FCA5A5;
  --color-status-cancelled-border: #7F1D1D;
  --color-status-pending-bg:       #1C2028;
  --color-status-pending-text:     #94A3B8;
  --color-status-pending-border:   #334155;
}

html.dark body {
  background-color: var(--color-surface-canvas);
  color: var(--color-text-primary);
}
```

---

## 5. Tipografia — Ajustes

O skill instrui: **dois níveis tipográficos distintos** para interfaces industriais.
1. **Macro-typography:** headers pesados, uppercase, tracking tight — visibilidade a distância
2. **Micro-typography:** monospace para IDs, status, metadados — precisão técnica

### Fontes

| Papel | Fonte | Justificativa |
|---|---|---|
| Display / Headings | `Plus Jakarta Sans` (já carregada) | Black/ExtraBold disponíveis, heavy grotesque |
| Corpo | `Inter` (já carregada) | Legível em pequenos tamanhos, alto x-height |
| IDs técnicos / Metadados | `JetBrains Mono` (ADICIONAR) | Monospace técnico — ID do chamado, timestamps |

Adicionar em `base.html`:
```html
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

### Escala

| Elemento | Atual | Proposto |
|---|---|---|
| Page title (h1) | `text-2xl font-extrabold` | `text-3xl font-black tracking-tight uppercase` |
| Section header (h2) | `text-xl font-bold` | `text-2xl font-extrabold tracking-tight` |
| Card title | `text-base font-semibold` | `text-base font-bold` |
| Navbar brand | logo apenas | logo + `"DIGITAL ANDON"` em `font-black text-xs tracking-widest uppercase` |
| Table header | `text-sm font-medium` | `text-[11px] font-black uppercase tracking-widest` (monospace opcional) |
| ID do chamado | `text-sm` plain | `font-mono text-xs font-bold tracking-wide` — ex: `#CHM-0042` |
| Badge / Tag | `text-xs font-bold` | `text-[10px] font-black uppercase tracking-wide` |
| Timestamps / Metadados | `text-xs text-gray-500` | `font-mono text-[11px] text-muted` |

---

## 5. Componentes — Plano de Mudanças

### 5.1 Navbar (`components/navbar.html`)

**Problema:** fundo branco se mistura com o conteúdo da página.

**Proposta — Opção A (Dark Navbar):**
```
bg: #0F1729 (nav-bg)
border-bottom: 1px solid #1E2D45
logo: versão clara (logo-white.png ou filtro CSS)
links: text-nav-text / hover: text-white bg-white/10
ativo: bg-dtx-500/20 text-dtx-400 border border-dtx-500/30
notificações/perfil: mesma paleta dark
```

**Proposta — Opção B (Light com accent bar):**
```
bg: white
border-top: 3px solid #1e4a8c (barra de acento no topo)
border-bottom: 1px solid surface-border
adicionar: backdrop-blur se quiser glassmorphism sutil
```

> **Recomendação: Opção A** — mais impacto, diferencia claramente nav do conteúdo.
> Opção B é mais segura se não quiser reescrever a navbar.

---

### 5.2 Login (`templates/login.html`)

**Problema:** card simples, sem impacto visual, parece qualquer CRUD genérico.

**Proposta:**
```
Layout: split 50/50 — lado esq: hero com gradient-dtx + logo grande + tagline
                       lado dir: formulário branco
Mobile: somente o formulário (hero some em sm:)

Hero (esquerdo):
  background: var(--gradient-dtx)
  Logo: grande (h-16), texto "DTX Digital Andon" em branco
  Tagline: "Controle e visibilidade em tempo real" (texto menor, opacidade 80%)
  Decoração: grid sutil em SVG ou círculos concêntricos low-opacity

Formulário (direito):
  Sem border/shadow no card em si — a divisão visual vem do split
  Inputs com altura h-12 (era h-11)
  Botão submit: gradiente dtx-600 → dtx-500, com sombra sutil
  Manter estrutura atual de campos
```

---

### 5.3 Cards / Containers

**Atual:** `bg-white border border-surface-border shadow-dtx-sm` — invisível no fundo branco.

**Proposta:**
```css
.dtx-card {
  background: #FFFFFF;
  border: 1px solid #D8DCE3;         /* mais visível */
  border-radius: 0.875rem;           /* ligeiramente maior */
  box-shadow: 0 2px 8px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04);
}

.dtx-card-raised {
  /* Cards de métricas, destaques */
  border-top: 3px solid var(--color-dtx-500);
  box-shadow: 0 4px 16px rgba(30,74,140,0.10);
}
```

---

### 5.4 Botões

**Atual:** `bg-dtx-600 text-white` — flat, sem profundidade.

**Proposta:**
```css
/* Primário */
.btn-primary {
  background: linear-gradient(180deg, #2E6ACC 0%, #1e4a8c 100%);
  box-shadow: 0 1px 3px rgba(30,74,140,0.4), inset 0 1px 0 rgba(255,255,255,0.1);
  border: 1px solid #163A70;
}
.btn-primary:hover {
  background: linear-gradient(180deg, #4A8AE8 0%, #2E6ACC 100%);
  box-shadow: 0 2px 6px rgba(30,74,140,0.5);
  transform: translateY(-1px);
}

/* Secundário (ghost) */
.btn-secondary {
  background: white;
  border: 1px solid #D8DCE3;
  color: #374151;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
```

---

### 5.5 Inputs / Formulários

**Proposta:**
```css
.dtx-input {
  border: 1.5px solid #D8DCE3;        /* mais grosso que 1px */
  background: #FAFBFC;                 /* ligeiro tom frio */
  height: 2.75rem;                     /* h-11 → h-11 mas com padding melhor */
  transition: border-color 0.15s, box-shadow 0.15s;
}
.dtx-input:focus {
  border-color: #4A8AE8;              /* azul mais claro que 600 */
  box-shadow: 0 0 0 3px rgba(74,138,232,0.15);  /* ring sutil */
  background: white;
}
```

---

### 5.6 Status Badges (`components/_status_badge.html`)

**Atual:** badges funcionam bem, apenas afinar.

**Proposta:** adicionar ícone de ponto pulsante para status "Aberto":
```html
<!-- "Aberto" -->
<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-black uppercase tracking-wide bg-amber-50 text-amber-700 border border-amber-200">
  <span class="relative flex h-2 w-2">
    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
    <span class="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
  </span>
  Aberto
</span>
```

---

### 5.7 Dashboard — KPI Cards

**Proposta:** adicionar seção de métricas rápidas no topo do dashboard (antes da tabela):
```
[  Total Abertos  ] [  Em Andamento  ] [  Concluídos  ] [  Urgentes  ]
    número grande       número grande     número grande    número grande
    +N essa semana      tempo médio       taxa fechamento  badge vermelho
```
Cada card com `border-top: 3px solid <cor-do-status>`.

---

### 5.8 Tabelas

**Proposta:**
```
Fundo do header: #0F1729 (dark) com texto branco — mais contraste
Ou: fundo dtx-50 com texto dtx-800 font-black uppercase tracking-widest
Row hover: background dtx-50/50 com border-left: 3px solid dtx-400
Row selecionada: background dtx-50 border-left: 3px solid dtx-600
Zebra stripes: leve bg-surface-raised nas linhas pares (opcional)
```

---

## 6. Páginas — Prioridade de Implementação

### Fase 1 — Impacto Máximo, Esforço Médio
1. **Navbar dark** — muda toda a percepção do sistema imediatamente
2. **Login split** — primeira impressão completamente nova
3. **Tokens de superfície** — atualizar `input.css` com novos tokens de cor

### Fase 2 — Consistência Visual
4. **Cards com sombra melhorada** — `.dtx-card` e `.dtx-card-raised`
5. **Botões com gradiente** — aplicar nos `.btn-primary` globalmente
6. **Inputs refinados** — borda 1.5px + focus ring azul claro

### Fase 3 — Detalhes e Polimento
7. **KPI cards no dashboard** — nova seção de métricas
8. **Status badges** — adicionar pulsante no "Aberto"
9. **Table headers** — dark ou dtx bold
10. **Formulário de chamado** — revisar espaçamento e hierarquia

### Fase 4 — Dark / Light Mode Toggle
11. **Tokens dark mode** — bloco `html.dark { }` em `input.css`
12. **Script anti-flash** — inline no `<head>` de `base.html`
13. **Botão toggle na navbar** — sol/lua com `localStorage`
14. **Ajustes de componentes** — status badges, tabelas, modais

---

## 7. Animações GSAP — O que manter / ampliar

**Manter:**
- `gsap-stagger-container` / `gsap-stagger` — entrada de itens em cascata
- `gsap-animate` — fade-in de conteúdo principal
- Flash toast fade out

**Ampliar:**
- Login: animar o hero lateral com `gsap.from` no texto (slide + fade)
- KPI cards: counter animation nos números (`gsap.to({ innerText: target })`)
- Navbar: ao scroll, adicionar `backdrop-blur` e leve `box-shadow` via ScrollTrigger

---

## 8. Acessibilidade — Guardrails do Redesign

Qualquer mudança deve manter:
- Contraste mínimo WCAG AA: 4.5:1 para texto normal, 3:1 para texto grande
- Focus ring visível em todos os elementos interativos (`focus-visible:ring-2`)
- Pulsante do badge "Aberto" deve ter `prefers-reduced-motion: no-preference` guard
- Navbar dark: verificar contraste de texto na cor `--color-nav-text` vs fundo

---

## 9. Dark / Light Mode Toggle — Estratégia Completa

### 9.1 Abordagem Técnica

**Estratégia escolhida: CSS Custom Properties + classe `html.dark`**

Razão: o projeto já usa CSS custom properties em toda parte (`--color-surface-*`, `--color-dtx-*`).
Trocar os valores das propriedades sob `html.dark {}` é suficiente — os templates não precisam
de `dark:` Tailwind em cada elemento. Isso mantém o HTML limpo.

**O que NÃO usar:** `darkMode: 'media'` no Tailwind (ignora a preferência do usuário).
Usar `darkMode: 'class'` no `tailwind.config.js` para ativar `dark:` variants quando necessário
em casos pontuais (ex: imagens, SVGs hardcoded).

---

### 9.2 Tokens Dark Mode — `input.css`

Os tokens completos do modo dark estão definidos na **Seção 4** deste documento
(bloco `html.dark {}`). Não duplicar aqui — fonte única de verdade.

---

### 9.3 Script Anti-Flash — `base.html` `<head>`

O maior problema de dark mode é o flash branco ao carregar (FOUC).
O script deve rodar **antes** de qualquer CSS ser aplicado:

```html
<!-- Adicionar como PRIMEIRO script no <head>, antes de qualquer <link> -->
<script>
  (function () {
    var t = localStorage.getItem('dtx-theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (t === 'dark' || (!t && prefersDark)) {
      document.documentElement.classList.add('dark');
    }
  })();
</script>
```

**Lógica de preferência:**
1. Se o usuário escolheu explicitamente → respeitar sempre (`localStorage`)
2. Se nunca escolheu → seguir `prefers-color-scheme` do sistema operacional
3. Padrão final (sem preferência) → light mode

---

### 9.4 Botão Toggle na Navbar — `components/navbar.html`

**Posição:** entre o seletor de idioma e o perfil do usuário, à direita.

```html
<!-- Botão Sol/Lua -->
<button
  id="btn-theme-toggle"
  type="button"
  aria-label="Alternar tema"
  class="min-w-[44px] min-h-[44px] p-3 rounded-dtx-lg text-gray-600 dark-text-nav-text
         hover:bg-surface-raised transition-all duration-200 inline-flex items-center
         justify-center outline-none focus-visible:ring-2 focus-visible:ring-dtx-400
         border border-transparent hover:border-surface-border"
>
  <!-- Ícone sol: visível no dark mode -->
  <svg id="icon-sun" class="w-5 h-5 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
      d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707
         M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z"/>
  </svg>
  <!-- Ícone lua: visível no light mode -->
  <svg id="icon-moon" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
      d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
  </svg>
</button>
```

**JS do toggle** — adicionar em `base.html` (inline, com nonce):
```js
(function () {
  var btn = document.getElementById('btn-theme-toggle');
  var sun = document.getElementById('icon-sun');
  var moon = document.getElementById('icon-moon');
  if (!btn) return;

  function aplicarTema(dark) {
    document.documentElement.classList.toggle('dark', dark);
    if (sun) sun.classList.toggle('hidden', !dark);
    if (moon) moon.classList.toggle('hidden', dark);
    localStorage.setItem('dtx-theme', dark ? 'dark' : 'light');
  }

  // Estado inicial
  aplicarTema(document.documentElement.classList.contains('dark'));

  btn.addEventListener('click', function () {
    aplicarTema(!document.documentElement.classList.contains('dark'));
  });
})();
```

---

### 9.5 Componentes que precisam de ajuste manual

Elementos com cores **hardcoded** (não usam tokens CSS) precisam de `dark:` Tailwind:

| Componente | Problema | Solução |
|---|---|---|
| Flash toasts | `bg-red-50 text-red-800` hardcoded | Adicionar `dark:bg-red-950 dark:text-red-300` |
| Notificação não lida | `bg-blue-50` hardcoded | `dark:bg-blue-950` |
| Dropdown de perfil | Header `bg-surface-raised` (ok via token) | Verificar |
| Tabela zebra | `bg-gray-50` hardcoded em alguns lugares | Converter para `bg-surface-raised` (já usa token) |
| Badge admin_global | `bg-purple-50 text-purple-700` | `dark:bg-purple-950 dark:text-purple-300` |
| Web push banner | `bg-white` + `text-gray-900` | `dark:bg-surface-base dark:text-gray-100` |
| Spinner de loading | `border-dtx-600` (ok — vira azul claro no dark) | Nenhum |

---

### 9.6 Login Page — Dark Mode

O split layout proposto fica bem no dark automaticamente:
- Hero esquerdo: usa `--gradient-dtx` que já tem variante dark nos tokens
- Formulário direito: usa `--color-surface-base` (#161B22 no dark) — correto

Adicionar no painel do formulário:
```html
class="... dark:border-surface-border dark:bg-surface-base"
```

---

### 9.7 Navbar: Dark Navbar + Dark Mode

Com a Opção A (navbar dark), o dark mode da navbar fica **praticamente grátis**:
- No light mode: navbar usa `--color-nav-bg: #0F1729`
- No dark mode: navbar usa `--color-nav-bg: var(--color-surface-base)` — que já é escuro (#161B22)

Isso significa que os tokens já cuidam da transição. Apenas o ícone sol/lua muda.

---

## 10. Arquivos a Modificar (por fase)

### Fase 1
```
app/static/css/input.css              ← novos tokens de cor
app/templates/components/navbar.html  ← dark navbar
app/templates/login.html              ← split layout
```

### Fase 2
```
app/static/css/input.css              ← .dtx-card melhorado, .btn-primary
app/static/css/dashboard.css          ← ajustes de tabela e header
app/templates/base.html               ← body background-color
```

### Fase 3
```
app/templates/dashboard.html          ← KPI cards section
app/templates/components/_status_badge.html  ← pulsante
app/static/js/gsap-motion.js          ← counter animation, scroll effects
```

### Fase 4 — Dark Mode
```
tailwind.config.js                    ← darkMode: 'class'
app/static/css/input.css              ← html.dark { } tokens
app/templates/base.html               ← script anti-flash no <head> + JS do toggle
app/templates/components/navbar.html  ← botão sol/lua
app/templates/components/_status_badge.html  ← dark: variants
app/templates/base.html               ← dark: nos flash toasts, web push banner
```

---

## 11. Decisões em Aberto

| Decisão | Opções | Status |
|---|---|---|
| Navbar: dark (`#13274b`) ou light+accent bar? | **Dark navy #13274b** | ✅ Decidido |
| Login: split layout ou card melhorado? | **Split 50/50** — hero dark + form light | ✅ Decidido |
| KPI cards no dashboard: sim/não? | Sim — 4 cards: Abertos / Em andamento / Concluídos / Urgentes | ⏳ Pendente |
| Dark mode: padrão light ou seguir SO? | **Seguir `prefers-color-scheme`** na 1ª visita — localStorage prevalece depois | ✅ Decidido |
| Dark mode: persistir no BD ou só localStorage? | **localStorage** — sem roundtrip, sem campo extra no Firestore | ✅ Decidido |
| IDs de chamados em `font-mono`? | Sim — ex: `#CHM-0042` em JetBrains Mono | ⏳ Pendente |
| Fonte JetBrains Mono: Google Fonts CDN ou self-hosted? | **CDN** — sem custo de infra, já tem Inter/Plus Jakarta assim | ⏳ Pendente |
