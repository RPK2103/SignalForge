# ROI Hypothesis Model

**This is a hypothesis model, not an ROI claim.**
SignalForge has **not** measured customer financial benefit in this repository.

Every numeric example below is:

> **ILLUSTRATIVE ASSUMPTION — NOT A MEASURED SIGNALFORGE RESULT**

## Variables

| Symbol | Meaning |
|---|---|
| \(N\) | Initiatives reviewed per year |
| \(H\) | Leadership hours per manual readiness review |
| \(C\) | Fully loaded cost per leadership hour |
| \(E\) | Avoidable dependency escalations per year (hypothesis) |
| \(C_e\) | Average escalation cost |
| \(R_d\) | Delayed-release exposure (hypothesis) |
| \(R_i\) | Incident-response exposure tied to ownership gaps (hypothesis) |
| \(R_c\) | Capability-shortage exposure (hypothesis) |
| \(R_o\) | Ownership-concentration exposure (hypothesis) |
| \(O\) | Annual cost to operate SignalForge |
| \(I\) | POC / implementation + change-management cost |

## Formulas

**Manual review cost**

\[
M = N \times H \times C
\]

**Avoided review effort (hypothesis fraction \(f \in [0,1]\))**

\[
A = f \times M
\]

**Risk-exposure reduction hypothesis** (do **not** assume 100% of identified risk
is avoided; use reduction factor \(g \in [0,1]\)):

\[
X = g \times (E \times C_e + R_d + R_i + R_c + R_o)
\]

**Net estimated benefit (hypothesis)**

\[
B = A + X - O - I
\]

**Payback period (years, if \(A+X > O\))**

\[
P = \frac{I}{(A + X - O)}
\]

**ROI percentage (hypothesis)**

\[
\mathrm{ROI} = \frac{B}{I + O} \times 100\%
\]

## ILLUSTRATIVE ASSUMPTION — NOT A MEASURED SIGNALFORGE RESULT

| Variable | Low | Base | High |
|---|---|---|---|
| \(N\) | 20 | 40 | 80 |
| \(H\) | 4 | 8 | 12 |
| \(C\) | 150 | 250 | 400 |
| \(f\) | 0.10 | 0.25 | 0.40 |
| \(g\) | 0.05 | 0.15 | 0.25 |
| \(E \times C_e\) | 50k | 150k | 400k |
| \(R_d+R_i+R_c+R_o\) | 100k | 300k | 800k |
| \(O\) | 40k | 120k | 250k |
| \(I\) | 30k | 75k | 150k |

Worked **base** illustration (currency units arbitrary):

- \(M = 40 \times 8 \times 250 = 80{,}000\)
- \(A = 0.25 \times 80{,}000 = 20{,}000\)
- \(X = 0.15 \times (150{,}000 + 300{,}000) = 67{,}500\)
- \(B = 20{,}000 + 67{,}500 - 120{,}000 - 75{,}000 = -107{,}500\)

Interpretation: under conservative base assumptions the hypothesis may be
**negative** in year one — POC value may be learning and risk visibility, not
immediate cash ROI. Do not present a positive ROI as fact.

Sensitivity: vary \(f\), \(g\), \(O\), and \(I\) independently; report ranges,
not a single headline number.

## Safeguards against misuse

- No double counting the same escalation across \(E\) and \(R_*\).
- Never treat every identified risk as avoided loss (\(g \ll 1\)).
- Never count NovaBank synthetic outcomes as customer evidence.
- Scenario estimates are not causal.
- Always include implementation and change-management costs.
- Label every external market sizing input:

> EXTERNAL RESEARCH REQUIRED — DO NOT PRESENT AS FACT
