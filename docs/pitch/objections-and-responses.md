# Objections and Responses

## “Is this employee surveillance?”

**Response:** No. SignalForge evaluates delivery-system risk, capability
coverage, dependencies and evidence. There is no employee-ranking permission,
and PR count is not treated as productivity. Employment decisions are out of
scope.

## “Can I trust the AI?”

**Response:** Deterministic scoring does not depend on an LLM. Chief-of-Staff
output is grounded with claims/citations, support statuses, and reject paths for
unsupported claims and prompt-injection detections. Local demos often use
deterministic fallback (`AI_ENABLED=false`). Residual NL risk remains — human
review is expected.

## “Are these delivery probabilities?”

**Response:** Only calibrated probabilities from production-eligible models
should be discussed as probabilities. NovaBank uses an uncalibrated scorecard
fallback and an unpromoted candidate — **not** calibrated probabilities.

## “Do scenarios predict the future?”

**Response:** Scenarios are counterfactual overlays for decision support. They
are not causal predictions and must not be presented as guarantees.

## “Is NovaBank a customer case study?”

**Response:** No. NovaBank is a fictional synthetic demo tenant for product
tours and tests.

## “Are you Microsoft-endorsed / on Marketplace?”

**Response:** No. Microsoft has not endorsed the project. Azure services are
proposed hosting/identity options for POCs. Marketplace publishing is deferred.

## “Do you have production customers and ROI?”

**Response:** This repository does not claim production or paid customers.
ROI materials are labelled hypotheses with illustrative assumptions only.

## “Is security enterprise-ready?”

**Response:** A security **foundation** exists (default-deny JWT, RBAC, audit,
PostgreSQL FORCE RLS, hardening gates). It is not a completed certification
program: no SOC 2/ISO claim, no pen-test completion claim, and interactive Entra
login SPA still requires integration work.

## “Will this replace our PM / analytics stack?”

**Response:** No. SignalForge complements status and analytics tools by focusing
on readiness, capability, dependency risk, scenarios, and grounded briefs.

## “Can we start without perfect data?”

**Response:** Yes, with explicit evidence-gap visibility. POC entry criteria
still require approved sources and owners; completeness is measured, not assumed.
