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
