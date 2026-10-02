from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/"benchmark"/"benchmark.json").read_text())
cases=data["cases"]
errors=[]
if len(cases)!=30: errors.append(f"Expected 30 cases, got {len(cases)}")
ids=[c["case_id"] for c in cases]
if len(ids)!=len(set(ids)): errors.append("Duplicate case IDs")
for c in cases:
    for f in c["contract_stack"]:
        if not (ROOT/f).exists(): errors.append(f'{c["case_id"]}: missing {f}')
    if c["expected_behavior"]=="ANSWER" and c["expected_answer"] is None:
        errors.append(f'{c["case_id"]}: ANSWER case has null expected_answer')
    if c["expected_behavior"]!="ANSWER" and c["expected_answer"] is not None:
        errors.append(f'{c["case_id"]}: abstention case has non-null expected_answer')
counts={}
for c in cases: counts[c["case_type"]]=counts.get(c["case_type"],0)+1
if counts != {"authentic":10,"controlled":15,"adversarial":5}: errors.append(f"Bad type counts: {counts}")
if errors:
    print("VALIDATION FAILED")
    print("\n".join("- "+e for e in errors)); sys.exit(1)
print("VALIDATION PASSED")
print("30 cases: 10 authentic + 15 controlled + 5 adversarial")
print("All referenced contract-stack files exist.")
