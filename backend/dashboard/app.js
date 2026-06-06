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

  var HIGHLIGHT_TERMS = [
    { text: "critical capability", cls: "hl-risk" },
    { text: "success probability", cls: "hl-positive" },
    { text: "capability coverage", cls: "hl-positive" },
    { text: "delivery risk", cls: "hl-risk" },
    { text: "Impact Score", cls: "hl-neutral" },
    { text: "Generative AI", cls: "hl-positive" },
    { text: "91%", cls: "hl-positive" },
    { text: "100%", cls: "hl-positive" },
    { text: "67%", cls: "hl-risk" },
    { text: "37%", cls: "hl-risk" },
    { text: "Python", cls: "hl-neutral" },
    { text: "Azure", cls: "hl-positive" },
    { text: "Kavi", cls: "hl-neutral" },
    { text: "High", cls: "hl-risk" },
    { text: "Low", cls: "hl-positive" },
  ];

  var NAV_SECTIONS = [
    { id: "hero", nav: "hero" },
    { id: "readiness", nav: "readiness" },
    { id: "intelligence", nav: "intelligence" },
    { id: "strategy", nav: "strategy" },
    { id: "analysis", nav: "analysis" },
  ];

  var countUpFrames = {};

  function $(id) {
    return document.getElementById(id);
  }

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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

  function countKey(el) {
    return el.id || el.getAttribute("data-count-id") || String(Math.random());
  }

  function finishCountAnimation(el) {
    if (!el) return;
    el.classList.remove("count-pop", "count-glow");
    void el.offsetWidth;
    el.classList.add("count-pop", "count-glow");
  }

  function runCountUp(el, endValue, options) {
    if (!el) return;

    options = options || {};
    var suffix = options.suffix !== undefined ? options.suffix : (el.getAttribute("data-count-suffix") || "");
    var duration = options.duration || 1200;
    var force = options.force || false;
    var key = countKey(el);

    if (!force && el.getAttribute("data-count-done") === "1") return;

    if (countUpFrames[key]) {
      cancelAnimationFrame(countUpFrames[key]);
      delete countUpFrames[key];
    }

    endValue = Math.round(Number(endValue));
    if (isNaN(endValue)) return;

    if (prefersReducedMotion()) {
      el.textContent = endValue + suffix;
      el.setAttribute("data-count-done", "1");
      finishCountAnimation(el);
      return;
    }

    el.setAttribute("data-count-done", "0");
    el.textContent = "0" + suffix;
    var startTime = null;

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = Math.round(endValue * eased);
      el.textContent = current + suffix;

      if (progress < 1) {
        countUpFrames[key] = requestAnimationFrame(step);
      } else {
        el.textContent = endValue + suffix;
        el.setAttribute("data-count-done", "1");
        delete countUpFrames[key];
        finishCountAnimation(el);
      }
    }

    countUpFrames[key] = requestAnimationFrame(step);
  }

  function runCountUpFromElement(el, force) {
    if (!el || !el.hasAttribute("data-count-to")) return;
    var target = parseFloat(el.getAttribute("data-count-to"));
    var suffix = el.getAttribute("data-count-suffix") || "";
    runCountUp(el, target, { suffix: suffix, duration: 1200, force: force });
  }

  function animateTextIn(el, text, force) {
    if (!el) return;
    if (!force && el.getAttribute("data-text-done") === "1") return;

    el.textContent = text;
    el.setAttribute("data-text-done", "1");

    if (prefersReducedMotion()) return;

    el.classList.remove("metric-text-enter");
    void el.offsetWidth;
    el.classList.add("metric-text-enter");
  }

  var HERO_COUNT_IDS = {
    "hero-metric-display": true,
    "hero-success-percent": true,
    "hero-coverage-value": true,
    "hero-chip-coverage": true,
  };

  function initCountUpObserver() {
    var elements = document.querySelectorAll("[data-count-to]");

    elements.forEach(function (el) {
      if (el.id === "success-percent" || HERO_COUNT_IDS[el.id]) return;
      if (el.id === "sim-impact") return;

      if ("IntersectionObserver" in window) {
        var observer = new IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry) {
              if (!entry.isIntersecting) return;
              if (el.getAttribute("data-count-done") === "1") return;
              runCountUpFromElement(el, false);
              observer.unobserve(el);
            });
          },
          { threshold: 0.25 }
        );
        observer.observe(el);
      } else {
        runCountUpFromElement(el, false);
      }
    });
  }

  function startHeroCountUps() {
    window.setTimeout(function () {
      runCountUp($("hero-metric-display"), 91, { suffix: "%", duration: 1200, force: true });
      runCountUp($("hero-success-percent"), 91, { suffix: "%", duration: 1200, force: true });
      runCountUp($("hero-coverage-value"), 100, { suffix: "%", duration: 1200, force: true });
      runCountUp($("hero-chip-coverage"), 100, { suffix: "%", duration: 1200, force: true });
      animateTextIn($("hero-risk-value"), "Low", true);
      animateTextIn($("hero-chip-risk"), "Low", true);
    }, 350);
  }

  function renderSuccess(data) {
    var percent = data.success_probability;

    $("success-loading").classList.add("hidden");
    $("success-content").classList.remove("hidden");

    if ($("success-percent")) {
      $("success-percent").setAttribute("data-count-to", String(percent));
    }

    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        runCountUp($("success-percent"), percent, { suffix: "%", duration: 1300, force: true });
        runCountUp($("hero-success-percent"), percent, { suffix: "%", duration: 1300, force: true });
        runCountUp($("hero-metric-display"), percent, { suffix: "%", duration: 1300, force: true });
        animateTextIn($("success-confidence"), data.confidence, true);
        $("success-outlook").textContent = data.delivery_outlook;
      });
    });
  }

  function showSuccessError() {
    $("success-loading").classList.add("hidden");
    $("success-error").classList.remove("hidden");
    renderSuccess(FALLBACK.success);
  }

  function riskClass(level) {
    if (level === "High") return "danger";
    if (level === "Medium") return "warning";
    return "";
  }

  function animateSimAfterValue(containerId, afterValue, suffix) {
    var container = $(containerId);
    if (!container) return;
    var afterEl = container.querySelector(".after");
    if (!afterEl) return;

    window.setTimeout(function () {
      runCountUp(afterEl, afterValue, { suffix: suffix || "%", duration: 1100, force: true });
    }, prefersReducedMotion() ? 0 : 1500);
  }

  function animateSimRiskText(afterRisk) {
    var afterEl = $("sim-risk") && $("sim-risk").querySelector(".after");
    if (!afterEl) return;

    window.setTimeout(function () {
      afterEl.textContent = afterRisk;
      afterEl.classList.remove("metric-text-enter");
      void afterEl.offsetWidth;
      afterEl.classList.add("metric-text-enter");
      if (afterRisk === "High") {
        afterEl.classList.add("hl-risk");
      }
      finishCountAnimation(afterEl);
    }, prefersReducedMotion() ? 0 : 1500);
  }

  function animateConstellationEntry() {
    var nodes = ["node-core", "node-azure", "node-python", "node-genai"];
    var lines = ["line-azure", "line-python", "line-genai"];

    nodes.forEach(function (id, i) {
      var node = $(id);
      if (!node) return;
      node.classList.add("is-entering");
      window.setTimeout(function () {
        node.classList.remove("is-entering");
        node.classList.add("is-entered", "is-active");
      }, prefersReducedMotion() ? 0 : 200 * i);
    });

    lines.forEach(function (id, i) {
      var line = $(id);
      if (!line) return;
      window.setTimeout(function () {
        line.classList.add("is-drawn");
      }, prefersReducedMotion() ? 0 : 450 + 220 * i);
    });
  }

  function syncConstellationImpact(data) {
    var panel = $("constellation-panel");
    var genaiNode = $("node-genai");
    var genaiLine = $("line-genai");
    var lostWrap = $("sim-lost-wrap");
    var hasLoss = data.lost_capabilities && data.lost_capabilities.length > 0;

    if (!panel) return;

    window.setTimeout(function () {
      if (hasLoss) {
        panel.classList.add("is-simulated");
        if (genaiNode) genaiNode.classList.add("is-lost");
        if (genaiLine) genaiLine.classList.add("is-severed");
        if (lostWrap) {
          lostWrap.classList.remove("lost-capability--emphasized");
          void lostWrap.offsetWidth;
          lostWrap.classList.add("lost-capability--emphasized");
        }
      }

      var riskRow = $("sim-risk-row");
      if (riskRow && data.risk_after === "High") {
        riskRow.classList.add("risk-morph-high");
      }
    }, prefersReducedMotion() ? 0 : 1500);
  }

  function renderSimulate(data) {
    var removed =
      data.removed_engineers && data.removed_engineers.length
        ? data.removed_engineers.join(", ")
        : "Kavi";

    $("sim-scenario").textContent = "If " + removed + " is removed:";

    $("sim-coverage").innerHTML =
      '<span class="before">' +
      data.coverage_before +
      '%</span><span class="arrow">→</span><span class="after ' +
      (data.coverage_after < 80 ? "danger" : "") +
      '">0%</span>';

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
      '">0%</span>';

    var lost =
      data.lost_capabilities && data.lost_capabilities.length
        ? data.lost_capabilities.join(", ")
        : "None";

    $("sim-lost").textContent = lost;

    if ($("sim-impact")) {
      $("sim-impact").setAttribute("data-count-to", String(data.impact_score));
    }

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

    animateConstellationEntry();

    window.requestAnimationFrame(function () {
      runCountUp($("sim-impact"), data.impact_score, { suffix: "", duration: 1200, force: true });
      animateSimAfterValue("sim-coverage", data.coverage_after, "%");
      animateSimAfterValue("sim-success", data.success_probability_after, "%");
      animateSimRiskText(data.risk_after);
      syncConstellationImpact(data);
    });
  }

  function showSimulateError() {
    $("sim-loading").classList.add("hidden");
    $("sim-error").classList.remove("hidden");
    renderSimulate(FALLBACK.simulate);
  }

  function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function highlightCopilotText(text) {
    var safe = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    HIGHLIGHT_TERMS.forEach(function (term) {
      var pattern = escapeRegex(term.text);
      if (/^[A-Za-z]+$/.test(term.text)) {
        pattern = "\\b" + pattern + "\\b";
      }
      var re = new RegExp(pattern, "gi");
      safe = safe.replace(re, function (match) {
        return '<span class="' + term.cls + '">' + match + "</span>";
      });
    });

    return safe;
  }

  function typewriterEffect(el, text, speedMs, onComplete) {
    if (!el) return;

    var html = highlightCopilotText(text);
    var cursor = $("copilot-cursor");

    if (prefersReducedMotion()) {
      el.innerHTML = html;
      if (cursor) cursor.classList.add("is-hidden");
      if (onComplete) onComplete();
      return;
    }

    el.innerHTML = "";
    if (cursor) cursor.classList.remove("is-hidden");

    var tokens = [];
    var i = 0;
    while (i < html.length) {
      if (html[i] === "<") {
        var close = html.indexOf(">", i);
        tokens.push(html.slice(i, close + 1));
        i = close + 1;
      } else {
        tokens.push(html[i]);
        i += 1;
      }
    }

    var index = 0;
    var buffer = "";

    function tick() {
      if (index >= tokens.length) {
        el.innerHTML = html;
        if (cursor) cursor.classList.add("is-hidden");
        if (onComplete) onComplete();
        return;
      }

      buffer += tokens[index];
      el.innerHTML = buffer;
      index += 1;
      window.setTimeout(tick, speedMs);
    }

    tick();
  }

  function renderSourceTags(sources) {
    var container = $("copilot-sources");
    container.innerHTML = "";

    if (!sources || !sources.length) return;

    sources.forEach(function (source, i) {
      var tag = document.createElement("span");
      tag.className = "source-tag";
      tag.textContent = source.replace(/_/g, " ");
      tag.style.animationDelay = prefersReducedMotion() ? "0s" : (0.15 + i * 0.12) + "s";
      container.appendChild(tag);
    });
  }

  function setCopilotStatus(mode) {
    var status = $("copilot-status");
    if (!status) return;

    status.classList.toggle("is-analyzing", mode === "analyzing");

    var label = status.querySelector("span:last-child");
    if (!label) return;

    if (mode === "analyzing") {
      label.textContent = "Analyzing feasibility";
    } else if (mode === "ready") {
      label.textContent = "Ready for briefing";
    } else if (mode === "complete") {
      label.textContent = "Briefing complete";
    }
  }

  function hideCopilotPlaceholder() {
    var placeholder = $("copilot-placeholder");
    if (placeholder) placeholder.classList.add("is-hidden");
  }

  function renderCopilotAnswer(data) {
    hideCopilotPlaceholder();
    $("copilot-loading").classList.add("hidden");
    $("copilot-answer-wrap").classList.remove("hidden");
    setCopilotStatus("complete");

    typewriterEffect($("copilot-answer-text"), data.answer, 16, function () {
      renderSourceTags(data.sources_used);
    });
  }

  function showCopilotError(message) {
    hideCopilotPlaceholder();
    $("copilot-loading").classList.add("hidden");
    $("copilot-answer-wrap").classList.remove("hidden");
    setCopilotStatus("ready");

    var text =
      message ||
      "SignalForge could not reach the copilot service. Please try again in a moment.";

    typewriterEffect($("copilot-answer-text"), text, 12, function () {
      $("copilot-sources").innerHTML = "";
    });
  }

  function askCopilot(question) {
    var trimmed = (question || "").trim();
    if (!trimmed) return;

    $("copilot-input").value = trimmed;
    $("copilot-ask-btn").disabled = true;
    $("copilot-answer-wrap").classList.add("hidden");
    $("copilot-error").classList.add("hidden");
    $("copilot-loading").classList.remove("hidden");
    hideCopilotPlaceholder();
    setCopilotStatus("analyzing");

    if ($("copilot-answer-text")) {
      $("copilot-answer-text").innerHTML = "";
    }
    if ($("copilot-cursor")) {
      $("copilot-cursor").classList.add("is-hidden");
    }
    $("copilot-sources").innerHTML = "";

    apiPost("/copilot", {
      project_name: PROJECT_NAME,
      question: trimmed,
    })
      .then(renderCopilotAnswer)
      .catch(function () {
        showCopilotError(
          "Unable to fetch a copilot answer right now. The project still shows strong execution readiness with 91% success probability and 100% capability coverage. Removing Kavi would drop coverage to 67% and elevate delivery risk from Low to High, with Generative AI as the critical lost capability."
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
        btn.classList.add("is-pressed");
        window.setTimeout(function () {
          btn.classList.remove("is-pressed");
        }, 180);
        askCopilot(question);
      });
      container.appendChild(btn);
    });
  }

  function revealInViewport() {
    var viewportH = window.innerHeight || document.documentElement.clientHeight;
    document.querySelectorAll(".reveal, .reveal-stagger").forEach(function (el) {
      var rect = el.getBoundingClientRect();
      if (rect.top < viewportH * 0.92 && rect.bottom > 0) {
        el.classList.add("is-visible");
      }
    });
  }

  function initScrollReveal() {
    revealInViewport();

    if (prefersReducedMotion()) {
      document.querySelectorAll(".reveal, .reveal-stagger").forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }

    document.documentElement.classList.add("motion-on");

    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.1, rootMargin: "0px 0px -5% 0px" }
      );

      document.querySelectorAll(".reveal, .reveal-stagger").forEach(function (el) {
        if (!el.classList.contains("is-visible")) {
          observer.observe(el);
        }
      });
    }
  }

  function initNav() {
    var links = document.querySelectorAll(".top-bar-link[data-nav]");

    links.forEach(function (link) {
      link.addEventListener("click", function () {
        links.forEach(function (l) {
          l.classList.remove("top-bar-link--active");
        });
        link.classList.add("top-bar-link--active");
      });
    });

    if (!("IntersectionObserver" in window)) return;

    var spyObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var id = entry.target.id;
          links.forEach(function (link) {
            link.classList.toggle(
              "top-bar-link--active",
              link.getAttribute("data-nav") === id
            );
          });
        });
      },
      { threshold: 0.25, rootMargin: "-20% 0px -55% 0px" }
    );

    NAV_SECTIONS.forEach(function (section) {
      var el = $(section.id);
      if (el) spyObserver.observe(el);
    });
  }

  function initHeroParallax() {
    if (prefersReducedMotion()) return;

    var hero = document.querySelector("[data-parallax]");
    var layer = document.querySelector("[data-parallax-depth]");
    var cursorGlow = $("hero-cursor-glow");
    if (!hero) return;

    var isFinePointer = window.matchMedia("(pointer: fine)").matches;
    if (!isFinePointer) return;

    hero.addEventListener("mousemove", function (event) {
      var rect = hero.getBoundingClientRect();
      var x = (event.clientX - rect.left) / rect.width - 0.5;
      var y = (event.clientY - rect.top) / rect.height - 0.5;

      if (layer) {
        var depth = parseFloat(layer.getAttribute("data-parallax-depth")) || 0.1;
        layer.style.transform =
          "translate(" + x * 28 * depth + "px, " + y * 18 * depth + "px)";
      }

      if (cursorGlow) {
        hero.classList.add("has-cursor-glow");
        cursorGlow.style.left = event.clientX - rect.left + "px";
        cursorGlow.style.top = event.clientY - rect.top + "px";
      }
    });

    hero.addEventListener("mouseleave", function () {
      if (layer) layer.style.transform = "translate(0, 0)";
      hero.classList.remove("has-cursor-glow");
    });
  }

  function initTextMetrics() {
    var textEls = document.querySelectorAll("[data-metric-text]");
    textEls.forEach(function (el) {
      if ("IntersectionObserver" in window) {
        var observer = new IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry) {
              if (!entry.isIntersecting) return;
              animateTextIn(el, el.getAttribute("data-metric-text"), false);
              observer.unobserve(el);
            });
          },
          { threshold: 0.35 }
        );
        observer.observe(el);
      }
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
    initScrollReveal();
    initCountUpObserver();
    initTextMetrics();
    initNav();
    initHeroParallax();
    startHeroCountUps();
    loadSuccessPrediction();
    loadSimulation();
  });
})();
