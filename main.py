"""Demo runner.  python main.py --scenario happy_path   |   python main.py --list   |   add --llm"""
import argparse
import os

from agent import LLMChooser, RuleChooser, run_agent
from scenarios import ORIG, SCENARIOS, make
from tools import MockERP


def print_trace(result):
    for t in result["trace"]:
        d = t["detail"]
        if t["step"] == "OPTIONS":
            print("  OPTIONS")
            for o in d:
                ok = f"qty={o['qty']} cost={o['cost']} score={o['score']}"
                tag = ok if o["feasible"] else f"NO - {o['why_not']}"
                print(f"    {o['id']}: {tag}")
        elif t["step"] == "VALIDATE":
            print("  VALIDATE")
            for c in d:
                print(f"    [{'ok' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}")
        else:
            print(f"  {t['step']}: {d}")


def ask_human(option):
    print(f"\n  >> APPROVAL NEEDED for {option['id']} qty={option['qty']} cost={option['cost']}")
    for r in option["approval_reasons"]:
        print(f"     - {r}")
    return input("     approve? [y/N] ").strip().lower() == "y"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="happy_path")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--llm", action="store_true", help="use Claude to pick among safe options")
    ap.add_argument("--auto-approve", action="store_true", help="skip the approval prompt")
    a = ap.parse_args()
    if a.list:
        for s in SCENARIOS:
            print(f"{s['name']:26}{s['about']}")
        raise SystemExit
    sc = next(s for s in SCENARIOS if s["name"] == a.scenario)
    erp = MockERP(make(sc["mutate"]), sc["faults"])
    chooser = LLMChooser() if a.llm and os.getenv("ANTHROPIC_API_KEY") else RuleChooser()
    print(f"SCENARIO: {sc['name']} - {sc['about']}\n")
    res = run_agent(erp, ORIG, chooser, (lambda o: True) if a.auto_approve else ask_human)
    print_trace(res)
    print(f"\nRESULT: {res['decision']} (attempts: {res['attempts']})")
