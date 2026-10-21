/*
 * Nimmi AI widget loader (older embed URL).
 * Forwards to the current widget, which runs your flow, AI chat, human handover
 * and call-backs, so sites using this URL get the same chat as new embeds.
 */
(function () {
    var current = document.currentScript;
    if (!current) return;
    var api = current.getAttribute('data-api-url') || 'https://api.nimmiai.in';
    var s = document.createElement('script');
    ['data-bot-id', 'data-api-url', 'data-dashboard-url', 'data-is-demo'].forEach(function (name) {
        var v = current.getAttribute(name);
        if (v !== null) s.setAttribute(name, v);
    });
    if (!current.getAttribute('data-api-url')) s.setAttribute('data-api-url', api);
    s.src = api.replace(/\/$/, '') + '/static/nimmi-widget.js?v=8';
    s.async = true;
    document.body.appendChild(s);
})();
