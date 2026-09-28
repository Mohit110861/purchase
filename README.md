# Purchasing Agent: supplier cannot fulfil the order

An agent that reacts when a supplier confirms less than we ordered (Scenario 2), and also handles
budget, storage and minimum-order limits (Scenario 4). It decides, acts, checks its own result with
plain code, and recovers or escalates when something goes wrong.

## Run it
```bash
python3 --version          # 3.9 or newer. No packages needed.
python3 main.py --list                                   # see scenarios
python3 main.py --scenario happy_path                    # asks you before risky orders
python3 main.py --scenario price_jumps_at_confirm --auto-approve
python3 evaluate.py                                      # run and grade all 10 scenarios
cp .env.example .env  # optional: put ANTHROPIC_API_KEY in your shell, then add --llm
```

## Approach (short)
- Code builds the options and checks every hard limit (budget, storage, minimum order, arrival time).
- The LLM (optional) only picks from options that already passed. If it fails, a rule picks.
- Before acting, risky orders need a human (value > 5000, new supplier, or reduced order).
- After acting, a separate validator re-reads the ERP and checks the PO. It does not trust the agent.
- If validation fails: cancel the PO, exclude that supplier, retry. After 2 retries, escalate.
- The unfilled 250 on the old PO is only closed after the replacement passes validation.

## Files
| File | Job |
|---|---|
| data.py | Mock data |
| tools.py | Mock ERP with read tools, write tools, and fault injection |
| policy.py | Rules and maths (stock-out day, shortfall, option building) |
| agent.py | The loop, LLM chooser, rule chooser |
| validator.py | Post-action checks |
| scenarios.py / evaluate.py | 10 test scenarios and grading |
| main.py | Demo runner |
| docs/architecture.png | Diagram |

## Evaluation
`python3 evaluate.py` grades each scenario on: right decision, gathered all data, respected
constraints (audited from raw ERP state), right action, and validated. Sanity check done: replacing
the validator with one that always says OK makes `price_jumps_at_confirm` fail.

## Known limits
- One SKU, demand is a flat daily number, no seasonality.
- The LLM path is written but was not run against the live API in development.
- Escalations do not yet carry the stock-out date as an urgency level.
