/* Substitui visualmente todo <select> do site por um painel de opções com a
 * cara do bento (cantos arredondados, hover, etc.) — a lista de opções nativa
 * do navegador não é estilizável de forma consistente entre engines (Chrome/
 * Firefox/Safari), então em vez de tentar, o <select> original é escondido
 * (opacity:0, pointer-events:none) mas continua no DOM funcional: mantém
 * navegação por teclado, leitor de tela e testes E2E que usam
 * locator.select_option() (Playwright) — nenhum deles interage com o painel
 * visual, todos continuam lendo/escrevendo o <select> real.
 *
 * Uso: automático. Todo <select> sem [multiple] é aprimorado no load da
 * página e também quando adicionado dinamicamente depois (ex.: selects de
 * transferência/escalonamento em visualizar_chamado.html, populados via JS).
 */
(function () {
  "use strict";

  function currentOption(select) {
    return select.options[select.selectedIndex] || null;
  }

  function closePanel(shell) {
    shell.classList.remove("is-open");
    var panel = shell.querySelector(".bento-select-panel");
    if (panel) panel.setAttribute("aria-hidden", "true");
  }

  function closeAllPanels(except) {
    document.querySelectorAll(".bento-select-shell.is-open").forEach(function (shell) {
      if (shell !== except) closePanel(shell);
    });
  }

  function openPanel(shell) {
    closeAllPanels(shell);
    shell.classList.add("is-open");
    var panel = shell.querySelector(".bento-select-panel");
    panel.setAttribute("aria-hidden", "false");
    var selected = panel.querySelector(".is-selected");
    if (selected) selected.scrollIntoView({ block: "nearest" });
  }

  function togglePanel(shell) {
    if (shell.classList.contains("is-open")) {
      closePanel(shell);
    } else {
      openPanel(shell);
    }
  }

  function syncTrigger(shell) {
    var select = shell.querySelector("select");
    var textEl = shell.querySelector(".bento-select-trigger-text");
    var panel = shell.querySelector(".bento-select-panel");
    if (!select || !textEl) return;

    var opt = currentOption(select);
    textEl.textContent = opt ? opt.textContent : "";
    textEl.classList.toggle("is-placeholder", !!(opt && opt.disabled));
    shell.classList.toggle("is-disabled", select.disabled);
    // Espelha hidden/.hidden do <select> real no shell — outras telas
    // escondem/mostram selects via classList (ex.: responsavel_select em
    // formulario.html), e isso não afeta os elementos visuais que o JS
    // deste componente criou ao lado dele.
    shell.hidden = select.hidden;
    shell.classList.toggle("hidden", select.classList.contains("hidden"));

    if (panel) {
      panel.querySelectorAll(".bento-select-option").forEach(function (li) {
        var isSelected = li.dataset.value === select.value;
        li.classList.toggle("is-selected", isSelected);
        li.setAttribute("aria-selected", isSelected ? "true" : "false");
      });
    }
  }

  function addOptionItem(panel, select, shell, option) {
    var li = document.createElement("li");
    li.className = "bento-select-option";
    li.setAttribute("role", "option");
    li.dataset.value = option.value;
    li.textContent = option.textContent;

    if (option.disabled) {
      li.classList.add("is-disabled");
      li.setAttribute("aria-disabled", "true");
    } else {
      li.addEventListener("click", function () {
        if (select.value !== option.value) {
          select.value = option.value;
          select.dispatchEvent(new Event("input", { bubbles: true }));
          select.dispatchEvent(new Event("change", { bubbles: true }));
        }
        closePanel(shell);
        select.focus({ preventScroll: true });
      });
    }
    panel.appendChild(li);
  }

  function rebuildPanel(shell) {
    var select = shell.querySelector("select");
    var panel = shell.querySelector(".bento-select-panel");
    if (!select || !panel) return;

    panel.innerHTML = "";
    Array.prototype.forEach.call(select.children, function (child) {
      if (child.tagName === "OPTGROUP") {
        var label = document.createElement("li");
        label.className = "bento-select-group-label";
        label.setAttribute("aria-hidden", "true");
        label.textContent = child.label;
        panel.appendChild(label);
        Array.prototype.forEach.call(child.children, function (opt) {
          addOptionItem(panel, select, shell, opt);
        });
      } else if (child.tagName === "OPTION") {
        addOptionItem(panel, select, shell, child);
      }
    });

    syncTrigger(shell);
  }

  function chevronSvg() {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "bento-select-chevron");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M6 9l6 6 6-6"></path>';
    return svg;
  }

  function enhanceSelect(select) {
    if (!select || select.tagName !== "SELECT" || select.multiple) return;
    if (select.dataset.bentoEnhanced) return;
    select.dataset.bentoEnhanced = "1";

    var shell = document.createElement("div");
    shell.className = "bento-select-shell";
    // Herda classes do <select> original (ex.: "hidden", "mt-1") — outras
    // telas escondem/mostram o campo inteiro via classList no select; o
    // shell precisa reagir junto (ver syncTrigger) desde o primeiro render.
    if (select.className) {
      shell.className += " " + select.className;
    }

    var trigger = document.createElement("div");
    trigger.className = "bento-select-trigger";
    trigger.setAttribute("aria-hidden", "true");

    var textEl = document.createElement("span");
    textEl.className = "bento-select-trigger-text";
    trigger.appendChild(textEl);
    trigger.appendChild(chevronSvg());

    var panel = document.createElement("ul");
    panel.className = "bento-select-panel";
    panel.setAttribute("role", "listbox");
    panel.setAttribute("aria-hidden", "true");
    // Sem isso, o mousedown num item tira o foco do <select> ANTES do
    // clique completar — o handler de blur fecha o painel no meio do
    // gesto e cancela a seleção (clássico bug de dropdown customizado).
    panel.addEventListener("mousedown", function (e) {
      e.preventDefault();
    });

    select.parentNode.insertBefore(shell, select);
    shell.appendChild(select);
    shell.appendChild(trigger);
    shell.appendChild(panel);
    select.classList.add("bento-select-native");

    // Bloqueia o popup nativo (sem estilo) em qualquer via de ativação —
    // clique direto, teclado (Enter/Espaço/Alt+seta) e clique em <label
    // for="...">, que o navegador também traduz num "click" sintético no
    // select. O painel customizado assume o lugar dele.
    ["mousedown", "click"].forEach(function (evt) {
      select.addEventListener(evt, function (e) {
        e.preventDefault();
      });
    });

    select.addEventListener("keydown", function (e) {
      var isOpenKey =
        e.key === "Enter" ||
        e.key === " " ||
        (e.altKey && (e.key === "ArrowDown" || e.key === "ArrowUp"));
      if (isOpenKey) {
        e.preventDefault();
        togglePanel(shell);
      } else if (e.key === "Escape") {
        closePanel(shell);
      }
    });

    select.addEventListener("change", function () {
      syncTrigger(shell);
    });
    select.addEventListener("focus", function () {
      shell.classList.add("is-focused");
    });
    select.addEventListener("blur", function () {
      shell.classList.remove("is-focused");
      closePanel(shell);
    });

    trigger.addEventListener("click", function () {
      if (select.disabled) return;
      togglePanel(shell);
      select.focus({ preventScroll: true });
    });

    rebuildPanel(shell);

    // Reconstrói o painel quando outro script popula/troca as <option>
    // dinamicamente (ex.: responsavel_select, selects de transferência).
    new MutationObserver(function () {
      rebuildPanel(shell);
    }).observe(select, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["disabled", "class", "hidden"],
    });
  }

  function enhanceAll(root) {
    root.querySelectorAll("select:not([multiple])").forEach(enhanceSelect);
  }

  function init() {
    enhanceAll(document);

    document.addEventListener("click", function (e) {
      var openShell = document.querySelector(".bento-select-shell.is-open");
      if (openShell && !openShell.contains(e.target)) {
        closePanel(openShell);
      }
    });

    // Selects adicionados depois do load (conteúdo de modal montado via JS,
    // linhas de tabela renderizadas por AJAX etc.).
    new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) return;
          if (node.matches && node.matches("select:not([multiple])")) enhanceSelect(node);
          if (node.querySelectorAll) enhanceAll(node);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
