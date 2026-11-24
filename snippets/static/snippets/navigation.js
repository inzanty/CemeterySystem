(() => {
    const groups = Array.from(document.querySelectorAll(".nav-group"));
    const close = (group) => { group.open = false; };

    for (const group of groups) {
        group.addEventListener("toggle", () => {
            if (group.open) groups.filter((other) => other !== group).forEach(close);
        });
    }

    document.addEventListener("click", (event) => {
        groups.filter((group) => !group.contains(event.target)).forEach(close);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        const opened = groups.filter((group) => group.open);
        if (!opened.length) return;
        event.preventDefault();
        const focused = opened.find((group) => group.contains(document.activeElement));
        opened.forEach(close);
        (focused || opened[0]).querySelector("summary").focus();
    });
})();
