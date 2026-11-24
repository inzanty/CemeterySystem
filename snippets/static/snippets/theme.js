(() => {
    "use strict";
    const key = "memoria-theme";
    const root = document.documentElement;
    const device = window.matchMedia("(prefers-color-scheme: dark)");
    const normalize = (value) => ["light", "dark", "system"].includes(value) ? value : "system";
    let preference = "system";
    const modes = ["system", "light", "dark"];
    const labels = { light: "Jasny", dark: "Ciemny", system: "Systemowy" };
    const nextMode = () => modes[(modes.indexOf(preference) + 1) % modes.length];
    let button;

    const apply = () => {
        root.dataset.theme = preference === "system" ? (device.matches ? "dark" : "light") : preference;
        if (button) {
            button.dataset.preference = preference;
            const label = `Motyw: ${labels[preference]}. Zmień na ${labels[nextMode()]}.`;
            button.setAttribute("aria-label", label);
            button.title = label;
        }
    };
    try {
        preference = normalize(window.localStorage.getItem(key));
    } catch (_) {
        // Storage may be blocked; the current page can still switch themes.
    }
    apply();
    const deviceChanged = () => { if (preference === "system") apply(); };
    if (device.addEventListener) device.addEventListener("change", deviceChanged);
    else device.addListener(deviceChanged);

    window.addEventListener("storage", (event) => {
        if (event.key !== key && event.key !== null) return;
        // Ignore sessionStorage events and other storage areas.
        try { if (event.storageArea !== window.localStorage) return; } catch (_) { return; }
        preference = normalize(event.newValue);
        apply();
    });

    document.addEventListener("DOMContentLoaded", () => {
        button = document.getElementById("theme-preference");
        if (!button) return;
        apply();
        button.addEventListener("click", () => {
            preference = nextMode();
            apply();
            try { window.localStorage.setItem(key, preference); } catch (_) { /* Keep the page preference. */ }
        });
        button.hidden = false;
    });
})();
