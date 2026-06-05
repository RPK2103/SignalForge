(function () {
  "use strict";

  var PROJECT_NAME = "Azure AI Migration";
  var API_BASE = window.location.origin;

  var FALLBACK = {
    success: {
      success_probability: 91,
      confidence: "High",
      delivery_outlook: "Likely Success",
    },
    simulate: {
      coverage_before: 100,
      coverage_after: 67,
      risk_before: "Low",
      risk_after: "High",
      success_probability_before: 100,
      success_probability_after: 37,
      lost_capabilities: ["Generative AI"],
      impact_score: 63,
      removed_engineers: ["Kavi"],
    },
  };

  var SUGGESTED_QUESTIONS = [
    "Why is this project likely to succeed?",
    "What happens if Kavi is removed?",
    "Based on staffing simulation, which capability is most critical?",
    "How can we reduce delivery risk?",
  ];

  function $(id) {
    return document.getElementById(id);
  }

  function apiPost(path, body) {
    return fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("Request failed (" + response.status + ")");
      }
      return response.json();
    });
  }

  function renderSuccess(data) {
    var percent = data.success_probability + "%";
    $("success-percent").textContent = percent;
    $("hero-success-percent").textContent = percent;
    $("success-confidence").textContent = data.confidence;
    $("success-outlook").textContent = data.delivery_outlook;
    $("success-loading").classList.add("hidden");
    $("success-content").classList.remove("hidden");
  }

  function showSuccessError() {
    $("success-loading").classList.add("hidden");
    $("success-error").classList.remove("hidden");
    renderSuccess(FALLBACK.success);
    $("success-content").classList.remove("hidden");
  }

  function riskClass(level) {
    if (level === "High") return "danger";
    if (level === "Medium") return "warning";
    return "";
  }

  function renderSimulate(data) {
    var removed = data.removed_engineers && data.removed_engineers.length
      ? data.removed_engineers.join(", ")
      : "Kavi";

    $("sim-scenario").textContent = "If " + removed + " is removed:";

    $("sim-coverage").innerHTML =
      '<span class="before">' +
      data.coverage_before +
      '%</span><span class="arrow">→</span><span class="after ' +
      (data.coverage_after < 80 ? "danger" : "") +
      '">' +
      data.coverage_after +
      "%</span>";

    $("sim-risk").innerHTML =
      '<span class="before">' +
      data.risk_before +
      '</span><span class="arrow">→</span><span class="after ' +
      riskClass(data.risk_after) +
      '">' +
      data.risk_after +
      "</span>";

    $("sim-success").innerHTML =
      '<span class="before">' +
      data.success_probability_before +
      '%</span><span class="arrow">→</span><span class="after ' +
      (data.success_probability_after < 70 ? "danger" : "") +
      '">' +
      data.success_probability_after +
      "%</span>";

    var lost = data.lost_capabilities && data.lost_capabilities.length
      ? data.lost_capabilities.join(", ")
      : "None";

    $("sim-lost").textContent = lost;
    $("sim-impact").textContent = data.impact_score;

    if (data.lost_capabilities && data.lost_capabilities.length) {
      $("sim-lost-wrap").classList.remove("hidden");
      $("sim-takeaway").textContent =
        lost + " is a critical dependency for this project.";
    } else {
      $("sim-lost-wrap").classList.add("hidden");
      $("sim-takeaway").textContent =
        "No single capability loss detected in this scenario.";
    }

    $("sim-loading").classList.add("hidden");
    $("sim-content").classList.remove("hidden");
  }

  function showSimulateError() {
    $("sim-loading").classList.add("hidden");
    $("sim-error").classList.remove("hidden");
    renderSimulate(FALLBACK.simulate);
    $("sim-content").classList.remove("hidden");
  }

  function renderCopilotAnswer(data) {
    $("copilot-answer-text").textContent = data.answer;
    $("copilot-sources").innerHTML = "";

    if (data.sources_used && data.sources_used.length) {
      data.sources_used.forEach(function (source) {
        var tag = document.createElement("span");
        tag.className = "source-tag";
        tag.textContent = source.replace(/_/g, " ");
        $("copilot-sources").appendChild(tag);
      });
    }

    $("copilot-loading").classList.add("hidden");
    $("copilot-answer-wrap").classList.remove("hidden");
  }

  function showCopilotError(message) {
    $("copilot-loading").classList.add("hidden");
    $("copilot-answer-wrap").classList.remove("hidden");
    $("copilot-answer-text").textContent =
      message ||
      "SignalForge could not reach the copilot service. Please try again in a moment.";
    $("copilot-sources").innerHTML = "";
  }

  function askCopilot(question) {
    var trimmed = (question || "").trim();
    if (!trimmed) return;

    $("copilot-input").value = trimmed;
    $("copilot-ask-btn").disabled = true;
    $("copilot-answer-wrap").classList.add("hidden");
    $("copilot-error").classList.add("hidden");
    $("copilot-loading").classList.remove("hidden");

    apiPost("/copilot", {
      project_name: PROJECT_NAME,
      question: trimmed,
    })
      .then(renderCopilotAnswer)
      .catch(function () {
        showCopilotError(
          "Unable to fetch a copilot answer right now. The project still shows strong execution readiness based on capability coverage and team fit."
        );
      })
      .finally(function () {
        $("copilot-ask-btn").disabled = false;
      });
  }

  function initSuggestedQuestions() {
    var container = $("suggested-questions");
    SUGGESTED_QUESTIONS.forEach(function (question) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "suggested-btn";
      btn.textContent = question;
      btn.addEventListener("click", function () {
        askCopilot(question);
      });
      container.appendChild(btn);
    });
  }

  function loadSuccessPrediction() {
    apiPost("/success-prediction", { project_name: PROJECT_NAME })
      .then(renderSuccess)
      .catch(showSuccessError);
  }

  function loadSimulation() {
    apiPost("/simulate", {
      project_name: PROJECT_NAME,
      remove_engineers: ["Kavi"],
    })
      .then(renderSimulate)
      .catch(showSimulateError);
  }

  function bindCopilotForm() {
    $("copilot-form").addEventListener("submit", function (event) {
      event.preventDefault();
      askCopilot($("copilot-input").value);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initSuggestedQuestions();
    bindCopilotForm();
    loadSuccessPrediction();
    loadSimulation();
  });
})();
