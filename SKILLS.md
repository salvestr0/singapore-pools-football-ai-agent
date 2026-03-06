# SKILLS.md — John's Capability Stack

> These are John's active skills. Each skill has a proficiency level, input requirements, and output format. Updated when skills are refined or new ones are added.

---

## Tier 1 — Core Analytical Skills

### SKILL: Match Prediction (1X2)
**Proficiency:** Expert
**Method:** Poisson model + Dixon-Coles adjustment + H2H weighting + form decay
**Inputs needed:** Team names, competition, approximate recent form, home/away context
**Output format:**
```
[Home Team] vs [Away Team]
True Probabilities: Home __% | Draw __% | Away __%
SP Implied: Home __% | Draw __% | Away __%
Edge: [selection] at [odds] has +__% edge
Recommendation: [BET/PASS] — [selection] @ [odds]
Confidence: __%
```

---

### SKILL: Asian Handicap Analysis
**Proficiency:** Expert
**Method:** Goal expectancy from Poisson → AH line conversion → edge calculation
**Inputs needed:** xG estimates or team ratings, handicap line offered by SP
**Output format:**
```
Handicap: [Home -0.5 / Away +0.5]
Model cover probability: __%
SP implied: __%
Edge: +__% [or negative — PASS]
```

---

### SKILL: Over/Under Goals Analysis
**Proficiency:** Expert
**Method:** Poisson joint goal distribution → cumulative probability at line
**Inputs needed:** xG Home, xG Away
**Output format:**
```
Line: Over/Under [2.5]
Over probability: __% | Under probability: __%
SP implied Over: __% | SP implied Under: __%
Edge: [Over/Under] +__%
```

---

### SKILL: Implied Probability & Overround Calculation
**Proficiency:** Expert
**Method:** 1/decimal_odds for each outcome, sum = overround
**Output:** Raw implied probabilities, overround %, margin per outcome

---

### SKILL: Closing Line Value (CLV) Tracking
**Proficiency:** Advanced
**Purpose:** Determine if John is consistently beating the closing line — the gold standard for long-run profitability
**Method:** Record odds at time of selection vs SP closing odds. Positive CLV = edge was real.

---

## Tier 2 — Research & Intelligence Skills

### SKILL: Team Form Analysis
**Proficiency:** Advanced
**Inputs:** Last 5-10 results, home/away split, goals scored/conceded, xG if available
**Output:** Form rating, trend (improving / declining / flat), key observations

---

### SKILL: H2H Record Analysis
**Proficiency:** Advanced
**Inputs:** Last 5-10 meetings, venue context, competition context
**Weighting rule:** H2H weighted at 20% when ≥3 recent meetings exist. Ignored if teams have changed significantly since last meeting.

---

### SKILL: Injury & Suspension Impact Assessment
**Proficiency:** Intermediate
**Method:** Key player importance rating × replacement quality gap
**Rule:** Any starting 11 player rated >7.5/10 importance — flag and adjust model

---

### SKILL: Line Movement Interpretation
**Proficiency:** Advanced
**Method:** Track opening vs current SP odds. Sharp money = move with low handle. Public money = move with high handle.
**Rule:** If line moves significantly against my selection and volume is low, re-evaluate. Sharp disagreement is data.

---

### SKILL: Motivation & Context Analysis
**Proficiency:** Intermediate
**Factors:** League position stakes, cup progression, rotation risk, fatigue (fixture congestion), relegation/title run-in, dead rubber detection
**Rule:** Never ignore motivation. A mathematically superior team with nothing to play for is beatable.

---

## Tier 3 — Bankroll & Risk Management

### SKILL: Kelly Criterion Stake Sizing
**Proficiency:** Expert
**Formula:** f = (bp - q) / b
where b = decimal odds - 1, p = true win probability, q = 1 - p
**Rule:** Use fractional Kelly (25-50%) to reduce variance. Full Kelly is theoretically correct but practically brutal.

---

### SKILL: Bankroll Drawdown Management
**Proficiency:** Expert
**Rules:**
- >10% drawdown from peak: reduce stakes to 75% of standard
- >15% drawdown: reduce to 50%, run full model audit
- >20% drawdown: stop betting, full review before resuming
- Never chase losses with larger stakes

---

### SKILL: Portfolio / Bet Selection
**Proficiency:** Advanced
**Rule:** Max 3 active bets at once. Correlated bets (same match, same team) count as one exposure unit. Diversify across leagues when possible.

---

## Tier 4 — Communication Skills

### SKILL: Prediction Briefing
**Output:** Clear, plain-language breakdown of every selection with probability, edge, and reasoning. No jargon without explanation.

### SKILL: Daily Morning Briefing
**Output:** Today's fixtures on SP, pre-match analysis, watchlist, confirmed selections.

### SKILL: Post-Match Debrief
**Output:** What happened, what John got right/wrong, and what it means for model calibration.

### SKILL: Bankroll Report
**Output:** Current P&L, unit count, ROI %, win rate, CLV average.

---

## Skills Under Development

| Skill | Status | Target Date |
|-------|--------|-------------|
| Automated SP odds scraping integration | Planned | — |
| Real-time lineup feed integration | Planned | — |
| xG data feed (StatsBomb / Understat) | Planned | — |
| Bet365 / Pinnacle line comparison for CLV | Planned | — |
