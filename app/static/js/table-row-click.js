document.addEventListener('DOMContentLoaded', function () {
  var rows = document.querySelectorAll('tr[data-detail-url]');
  if (!rows.length) return;

  rows.forEach(function (row) {
    row.addEventListener('click', function (event) {
      var target = event.target;

      // Não dispara navegação se o clique for em elementos interativos
      if (target.closest('a, button, input, textarea, select, label, svg, path')) {
        return;
      }

      var url = row.getAttribute('data-detail-url');
      if (!url) return;

      try {
        window.open(url, '_blank', 'noopener');
      } catch (e) {
        window.location.href = url;
      }
    });
  });
});

