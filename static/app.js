function showDay(index) {
    document.querySelectorAll(".day-panel").forEach(function (panel) {
        panel.classList.remove("active");
    });
    document.querySelectorAll(".day-tab").forEach(function (tab) {
        tab.classList.remove("active");
    });

    var panel = document.getElementById("day-" + index);
    if (panel) panel.classList.add("active");

    var tabs = document.querySelectorAll(".day-tab");
    var panels = document.querySelectorAll(".day-panel");
    panels.forEach(function (p, i) {
        if (p.id === "day-" + index && tabs[i]) {
            tabs[i].classList.add("active");
        }
    });
}
