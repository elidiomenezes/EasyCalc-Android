# Gaussian 2-adic conjugation HDL experiment

Isolated experiment; no changes to EasyCalc Android application.

Three combinational implementations of conjugation of Gaussian **units** modulo 2^W:
- direct component negation (baseline)
- Newton Gaussian inversion followed by norm multiplication
- scalar Newton inversion of the norm (redundant control)

Inputs must satisfy a+b odd. Even/nonunit inputs require valuation factoring and are **not** tested here.
All results are congruences modulo 2^W; this is NOT native base (-1+i) digit-stream hardware.
The experiment deliberately tests whether inversion-based conjugation can beat the trivial componentwise baseline.

GitHub Actions simulates 2000 randomized operands at W=8,16,32, then runs generic Yosys synthesis.
ABC generic cell counts are not silicon area or real timing. Inspect Actions artifacts and logs.
No success or performance result is claimed until the workflow completes.
