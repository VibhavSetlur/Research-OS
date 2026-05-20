# Assumption Validator (Pre-Execution Gate)

## Purpose
Before any analysis script runs, this skill verifies its statistical assumptions against the data profile. If a required assumption fails, it blocks execution of the primary method, logs the failure to dead ends, and routes to a designated fallback method.

---

## Protocol

For each analytical task:
1. **Identify the Method**: Detect the method planned for the research question (e.g., OLS regression, t-test, ANOVA).
2. **Retrieve Stated Assumptions**: Read the planned assumptions from the methodology layout.
3. **Execute Statistical Assumption Tests**: Run specific validation checks on the actual input datasets.
4. **Determine Pass/Fail**: Evaluate the test statistics and p-values against standard criteria.
5. **Route Execution**:
   - **PASS**: Allow the primary script to execute.
   - **FAIL**: Block execution, log to dead ends, and trigger the fallback method (e.g., nonparametric alternative).

---

## Statistical Tests & Fallback Mapping

| Method | Assumption | Statistical Test | Criteria | Fallback Method |
|---|---|---|---|---|
| **t-test (independent)** | Normality of groups | Shapiro-Wilk test | $p \ge 0.05$ | Mann-Whitney U test |
| | Homogeneity of variance | Levene's test | $p \ge 0.05$ | Welch's t-test |
| **ANOVA (one-way)** | Normality of residuals | Shapiro-Wilk or Kolmogorov-Smirnov | $p \ge 0.05$ | Kruskal-Wallis test |
| | Homogeneity of variances | Levene's test | $p \ge 0.05$ | Welch's ANOVA |
| **OLS Regression** | Linearity | Harvey-Collier or Ramsey RESET | $p \ge 0.05$ | Generalized Additive Models (GAM) / Polynomial |
| | Homoscedasticity | Breusch-Pagan or White test | $p \ge 0.05$ | Weighted Least Squares (WLS) or robust errors |
| | Normality of residuals | Jarque-Bera or Shapiro-Wilk | $p \ge 0.05$ | Robust regression (RLM) or bootstrapping |
| | No Multicollinearity | Variance Inflation Factor (VIF) | $VIF < 5$ (or $< 10$) | Ridge/Lasso Regression or drop collinear feature |
| | Independence of residuals | Durbin-Watson test | $1.5 < DW < 2.5$ | Newey-West standard errors or ARMA modeling |
| **Time Series (ARIMA)** | Stationarity | Augmented Dickey-Fuller (ADF) | $p < 0.05$ | Differencing ($d \ge 1$) or detrending |

---

## Output Validation Report

The validator generates `reports/analysis/assumption_validation_{question_id}.json` with the following structure:

```json
{
  "question_id": "q1",
  "planned_method": "OLS",
  "timestamp": "2026-05-19T21:30:00Z",
  "verdict": "PASS | FAIL",
  "results": [
    {
      "assumption": "Normality of residuals",
      "test_name": "Shapiro-Wilk",
      "statistic": 0.985,
      "p_value": 0.123,
      "status": "PASS",
      "message": "Residuals are normally distributed."
    },
    {
      "assumption": "Homoscedasticity",
      "test_name": "Breusch-Pagan",
      "statistic": 12.4,
      "p_value": 0.002,
      "status": "FAIL",
      "message": "Heteroscedasticity detected (p < 0.05)."
    }
  ],
  "routing": {
    "action": "execute_fallback | execute_primary",
    "target_method": "Robust Regression (RLM)",
    "reason": "Failed Homoscedasticity assumption."
  }
}
```

---

## Integration

- Run automatically prior to script execution.
- If a check fails, the orchestrator updates `.research/cache/state.json` with the fallback target and writes a dead end entry describing the violation to `docs/dead_ends/`.
- CLI Command: `python .research/scripts/utils/assumption_validator.py --data <path> --config <config_path>`
