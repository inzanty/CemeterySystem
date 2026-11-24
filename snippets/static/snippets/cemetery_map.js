(() => {
    "use strict";
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const pointFor = (x, y, rect) => ({
        x: Math.round(clamp((x - rect.left) / rect.width * 100, 0, 100) * 100) / 100,
        y: Math.round(clamp((y - rect.top) / rect.height * 100, 0, 100) * 100) / 100,
    });
    const zoomFor = (current, delta) => clamp(current + delta, 1, 4);
    if (typeof module !== "undefined") module.exports = { pointFor, zoomFor };
    if (typeof document === "undefined") return;

    document.querySelectorAll("[data-cemetery-map]").forEach((map) => {
        if (map.dataset.initialized) return;
        map.dataset.initialized = "true";
        const viewport = map.querySelector(".map-viewport");
        const canvas = map.querySelector(".map-canvas");
        const toolbar = map.querySelector(".map-toolbar");
        let scale = 1;
        const zoom = (value) => {
            const oldScale = scale;
            scale = value;
            const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / oldScale;
            const centerY = (viewport.scrollTop + viewport.clientHeight / 2) / oldScale;
            canvas.style.width = `${scale * 100}%`;
            viewport.scrollLeft = centerX * scale - viewport.clientWidth / 2;
            viewport.scrollTop = centerY * scale - viewport.clientHeight / 2;
            map.querySelector("[data-map-scale]").textContent = `${Math.round(scale * 100)}%`;
            map.querySelector('[data-map-zoom="-0.5"]').disabled = scale === 1;
            map.querySelector('[data-map-zoom="0.5"]').disabled = scale === 4;
        };
        toolbar.hidden = false;
        zoom(1);
        map.querySelectorAll("[data-map-zoom]").forEach(button => {
            button.addEventListener("click", () => zoom(zoomFor(scale, Number(button.dataset.mapZoom))));
        });
        const centerSelected = () => {
            const selected = canvas.querySelector("a.is-selected");
            if (!selected) return;
            viewport.scrollLeft = selected.offsetLeft - viewport.clientWidth / 2;
            viewport.scrollTop = selected.offsetTop - viewport.clientHeight / 2;
        };
        map.querySelector("[data-map-reset]").addEventListener("click", () => { zoom(1); centerSelected(); });
        const image = canvas.querySelector("img");
        if (image.complete) centerSelected();
        else image.addEventListener("load", centerSelected, { once: true });

        let drag = null, dragged = false;
        viewport.addEventListener("pointerdown", (event) => {
            dragged = false;
            if (event.pointerType !== "mouse" || event.button !== 0 || event.target.closest("a")) return;
            drag = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
            viewport.setPointerCapture(event.pointerId);
        });
        viewport.addEventListener("pointermove", (event) => {
            if (!drag) return;
            if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) dragged = true;
            if (dragged) {
                viewport.scrollLeft = drag.left - (event.clientX - drag.x);
                viewport.scrollTop = drag.top - (event.clientY - drag.y);
                event.preventDefault();
            }
        });
        viewport.addEventListener("pointerup", () => { drag = null; });
        viewport.addEventListener("pointercancel", () => { drag = null; });

        const editor = map.closest("[data-marker-editor]");
        if (!editor) return;
        const x = editor.querySelector('[name="map_x"]');
        const y = editor.querySelector('[name="map_y"]');
        const status = editor.querySelector("[data-position-status]");
        const marker = document.createElement("span");
        marker.className = "map-marker is-selected";
        marker.setAttribute("aria-hidden", "true");
        marker.textContent = "+";
        canvas.append(marker);
        // Hide the saved marker while showing the editable preview.
        canvas.querySelectorAll("a.map-marker").forEach(saved => { saved.hidden = true; });
        const preview = () => {
            marker.hidden = x.value === "" || y.value === "" || !Number.isFinite(Number(x.value)) || !Number.isFinite(Number(y.value));
            marker.style.left = `${clamp(Number(x.value), 0, 100)}%`;
            marker.style.top = `${clamp(Number(y.value), 0, 100)}%`;
        };
        viewport.addEventListener("click", event => {
            if (dragged || event.target.closest("a")) return;
            const rect = canvas.getBoundingClientRect();
            if (event.clientX < rect.left || event.clientX > rect.left + rect.width ||
                event.clientY < rect.top || event.clientY > rect.top + rect.height) return;
            const point = pointFor(event.clientX, event.clientY, rect);
            x.value = point.x.toFixed(2);
            y.value = point.y.toFixed(2);
            preview();
            status.textContent = `Wybrano pozycję: ${x.value}%, ${y.value}%. Zapisz zmiany.`;
        });
        const clear = editor.querySelector("[data-clear-position]");
        clear.hidden = false;
        clear.addEventListener("click", () => {
            x.value = y.value = "";
            preview();
            status.textContent = "Znacznik zostanie usunięty po zapisaniu.";
        });
        x.addEventListener("input", preview);
        y.addEventListener("input", preview);
        preview();
    });
})();
