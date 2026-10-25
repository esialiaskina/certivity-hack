"""Offline tests for predicate compilation and atom applicability."""
import json
import tempfile
from pathlib import Path

from regir.compile.conditions import compile_atom, compile_file, valid_predicate
from regir.evaluate.applicability import evaluate_atom


def fake(_system, _user):
    return json.dumps({
        "conditions": [{
            "predicate": {"facet": "location", "op": "has", "value": "rear"},
            "evidence": "at the rear",
        }, {
            "predicate": {"facet": "not.a.facet", "op": "eq", "value": "x"},
            "evidence": "vehicle",
        }],
        "inherited": [{
            "predicate": {"facet": "product.approval_level", "op": "eq", "value": "component"},
            "evidence": "Component requirements",
        }],
    })


atom = {
    "atom_id": "UN_TEST@1#1/a1",
    "quote": "The device at the rear shall emit red light.",
    "text": "The device at the rear shall emit red light.",
    "chain": ["Component requirements"],
}
compiled = compile_atom(atom, fake=fake)
assert len(compiled["conditions"]) == 1
assert len(compiled["inherited"]) == 1
assert valid_predicate({"all": [compiled["conditions"][0]["predicate"]]})
assert not valid_predicate({"facet": "unknown", "op": "eq", "value": 1})

known = {
    "location": {"value": ["rear"], "status": "known"},
    "product.approval_level": {"value": "component", "status": "known"},
}
assert evaluate_atom(compiled, known)["verdict"] == "true"

assumed = dict(known)
assumed["product.approval_level"] = {"value": "component", "status": "assumed"}
proof = evaluate_atom(compiled, assumed)
assert proof["raw_verdict"] == "true" and proof["verdict"] == "unknown"
assert proof["assumptions_used"] == ["product.approval_level"]
assert evaluate_atom(compiled, assumed, allow_assumptions=True)["verdict"] == "true"

missing = {"location": {"value": ["rear"], "status": "known"}}
proof = evaluate_atom(compiled, missing)
assert proof["verdict"] == "unknown" and proof["missing_facets"] == ["product.approval_level"]

wrong = dict(known)
wrong["location"] = {"value": ["front"], "status": "known"}
assert evaluate_atom(compiled, wrong)["verdict"] == "false"

with tempfile.TemporaryDirectory() as tmp:
    source = Path(tmp) / "atoms.jsonl"
    target = Path(tmp) / "compiled.jsonl"
    source.write_text(json.dumps(atom) + "\n")
    batch = compile_file(source, target, workers=1, fake=fake)
    assert len(batch) == 1 and target.exists()
    assert json.loads(target.read_text())["conditions"] == compiled["conditions"]

print("condition compiler/applicability tests passed")
