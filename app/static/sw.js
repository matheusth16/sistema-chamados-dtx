/* Service Worker: Web Push - Sistema de Chamados */
self.addEventListener('push', function(event) {
    var data = { title: 'Sistema de Chamados', body: '', url: '' };
    if (event.data) {
        try {
            var payload = event.data.json();
            data.title = payload.title || data.title;
            data.body = payload.body || '';
            data.url = payload.url || '';
        } catch (e) {}
    }
    var options = {
        body: data.body,
        data: { url: data.url },
        tag: 'chamado-' + (data.url || Date.now()),
        icon: self.location.origin + '/static/favicon.ico'
    };
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    var url = event.notification.data && event.notification.data.url;
    if (url) {
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(windowClients) {
                for (var i = 0; i < windowClients.length; i++) {
                    if (windowClients[i].url.indexOf(self.location.origin) === 0 && 'focus' in windowClients[i]) {
                        windowClients[i].navigate(url);
                        return windowClients[i].focus();
                    }
                }
                if (clients.openWindow) {
                    return clients.openWindow(url);
                }
            })
        );
    }
});
