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

/* Workout Logging */
function logExercise(exerciseId) {
    var repsInput = document.getElementById("reps-" + exerciseId);
    var weightInput = document.getElementById("weight-" + exerciseId);

    var reps = repsInput.value;
    var weight = weightInput.value;

    if (!reps || !weight) {
        alert("Please enter both reps and weight.");
        return;
    }

    fetch("/workout/log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            exercise_id: exerciseId,
            actual_reps: parseInt(reps),
            actual_weight_kg: parseFloat(weight),
        }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data.success) {
            var card = document.getElementById("exercise-" + exerciseId);
            var badge = card.querySelector(".gym-logged-badge");
            if (!badge) {
                var top = card.querySelector(".gym-card-top");
                badge = document.createElement("span");
                badge.className = "gym-logged-badge";
                badge.innerHTML = '<i data-feather="check-circle" style="width:16px;height:16px;"></i> Logged';
                top.appendChild(badge);
                feather.replace();
            }
            var btn = card.querySelector(".gym-log-btn");
            if (btn) btn.textContent = "Update";
        } else {
            alert("Error: " + (data.error || "Unknown error"));
        }
    })
    .catch(function (err) {
        alert("Failed to log exercise.");
    });
}

/* Chat Sidebar */
function toggleChat() {
    var sidebar = document.getElementById("chatSidebar");
    if (sidebar) {
        sidebar.classList.toggle("open");
    }
}

function sendChat() {
    var input = document.getElementById("chatInput");
    var message = input.value.trim();
    if (!message) return;

    var messagesDiv = document.getElementById("chatMessages");

    // Add user message
    var userMsg = document.createElement("div");
    userMsg.className = "chat-msg chat-msg-user";
    userMsg.textContent = message;
    messagesDiv.appendChild(userMsg);

    input.value = "";
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    // Show typing indicator
    var typing = document.createElement("div");
    typing.className = "chat-msg chat-msg-ai chat-typing";
    typing.textContent = "Thinking...";
    messagesDiv.appendChild(typing);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message }),
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
        messagesDiv.removeChild(typing);

        var aiMsg = document.createElement("div");
        aiMsg.className = "chat-msg chat-msg-ai";

        if (data.error) {
            aiMsg.textContent = "Error: " + data.error;
        } else {
            aiMsg.textContent = data.reply;
            if (data.plan_updated) {
                var notice = document.createElement("div");
                notice.className = "chat-plan-updated";
                notice.innerHTML = '<i data-feather="refresh-cw" style="width:14px;height:14px;"></i> Plan updated! <a href="/workout/plan">View changes</a>';
                aiMsg.appendChild(notice);
                feather.replace();
            }
        }

        messagesDiv.appendChild(aiMsg);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    })
    .catch(function (err) {
        messagesDiv.removeChild(typing);
        var errMsg = document.createElement("div");
        errMsg.className = "chat-msg chat-msg-ai";
        errMsg.textContent = "Failed to connect. Please try again.";
        messagesDiv.appendChild(errMsg);
    });
}

/* Food / Nutrition */
var _foodDebounce = null;
var _foodResults = [];

function foodSearch() {
    var q = document.getElementById("foodSearchInput").value.trim();
    var resultsEl = document.getElementById("foodResults");

    if (!q) {
        resultsEl.style.display = "none";
        return;
    }

    clearTimeout(_foodDebounce);
    _foodDebounce = setTimeout(function () {
        fetch("/food/search?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (items) {
            _foodResults = items;
            resultsEl.innerHTML = "";
            if (!items.length) {
                resultsEl.style.display = "none";
                return;
            }
            items.forEach(function (item, i) {
                var div = document.createElement("div");
                div.className = "food-result-item";
                div.textContent = item.name + " — " + item.cal_100g + " kcal / 100g";
                div.onclick = function () { selectFood(i); };
                resultsEl.appendChild(div);
            });
            resultsEl.style.display = "block";
        })
        .catch(function () { resultsEl.style.display = "none"; });
    }, 300);
}

function selectFood(index) {
    var item = _foodResults[index];
    if (!item) return;
    document.getElementById("foodSearchInput").value = item.name;
    document.getElementById("selectedName").value = item.name;
    document.getElementById("selectedCal").value = item.cal_100g;
    document.getElementById("selectedProtein").value = item.protein_100g;
    document.getElementById("selectedCarbs").value = item.carbs_100g;
    document.getElementById("selectedFat").value = item.fat_100g;
    document.getElementById("foodResults").style.display = "none";
}

function addFood() {
    var name = document.getElementById("selectedName").value;
    var serving = document.getElementById("servingInput").value;

    if (!name) { alert("Please search and select a food first."); return; }
    if (!serving || parseFloat(serving) <= 0) { alert("Please enter a valid serving size."); return; }

    fetch("/food/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            food_name: name,
            serving_g: parseFloat(serving),
            cal_100g: parseFloat(document.getElementById("selectedCal").value) || 0,
            protein_100g: parseFloat(document.getElementById("selectedProtein").value) || 0,
            carbs_100g: parseFloat(document.getElementById("selectedCarbs").value) || 0,
            fat_100g: parseFloat(document.getElementById("selectedFat").value) || 0,
        }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (!data.success) { alert(data.error || "Failed to add food."); return; }

        var e = data.entry;

        // Show table if it was hidden (first entry)
        var empty = document.getElementById("emptyState");
        var wrap = document.getElementById("foodTableWrap");
        if (empty) empty.style.display = "none";
        if (wrap) wrap.style.display = "block";

        // Append row
        var tbody = document.getElementById("foodTableBody");
        var tr = document.createElement("tr");
        tr.id = "food-row-" + e.id;
        tr.innerHTML =
            "<td>" + e.food_name + "</td>" +
            "<td>" + Math.round(e.serving_g) + "g</td>" +
            "<td>" + e.calories + "</td>" +
            "<td>" + e.protein_g + "g</td>" +
            "<td>" + e.carbs_g + "g</td>" +
            "<td>" + e.fat_g + "g</td>" +
            "<td><button class='btn-icon' onclick='deleteFood(" + e.id + ", this)' title='Remove'>" +
            "<i data-feather='trash-2' style='width:14px;height:14px;'></i></button></td>";
        tbody.appendChild(tr);
        feather.replace();

        // Update totals
        updateTotals(e.calories, e.protein_g, e.carbs_g, e.fat_g);

        // Reset inputs
        document.getElementById("foodSearchInput").value = "";
        document.getElementById("servingInput").value = "";
        document.getElementById("selectedName").value = "";
        document.getElementById("selectedCal").value = "";
        document.getElementById("selectedProtein").value = "";
        document.getElementById("selectedCarbs").value = "";
        document.getElementById("selectedFat").value = "";
    })
    .catch(function () { alert("Failed to add food."); });
}

function deleteFood(id, btnEl) {
    fetch("/food/delete/" + id, { method: "POST" })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (!data.success) { alert(data.error || "Failed to delete."); return; }
        var row = document.getElementById("food-row-" + id);
        if (!row) return;

        // Read values from row before removing
        var cells = row.querySelectorAll("td");
        var cal = parseFloat(cells[2].textContent) || 0;
        var pro = parseFloat(cells[3].textContent) || 0;
        var carbs = parseFloat(cells[4].textContent) || 0;
        var fat = parseFloat(cells[5].textContent) || 0;

        row.remove();
        updateTotals(-cal, -pro, -carbs, -fat);

        // Show empty state if no rows left
        var tbody = document.getElementById("foodTableBody");
        if (tbody && tbody.children.length === 0) {
            var empty = document.getElementById("emptyState");
            var wrap = document.getElementById("foodTableWrap");
            if (empty) empty.style.display = "";
            if (wrap) wrap.style.display = "none";
        }
    })
    .catch(function () { alert("Failed to delete."); });
}

function updateTotals(cal, pro, carbs, fat) {
    function add(id, val) {
        var el = document.getElementById(id);
        if (!el) return;
        el.textContent = Math.round((parseFloat(el.textContent) + val) * 10) / 10;
    }
    add("total-calories", cal);
    add("total-protein", pro);
    add("total-carbs", carbs);
    add("total-fat", fat);
}

// Close food search dropdown when clicking outside
document.addEventListener("click", function (e) {
    var wrap = document.querySelector(".food-search-wrap");
    if (wrap && !wrap.contains(e.target)) {
        var results = document.getElementById("foodResults");
        if (results) results.style.display = "none";
    }
});
