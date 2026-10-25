"""Offline safety tests for candidate triggers and coverage selection."""
from regir.select.candidates import _run_horizontal
from regir.select.coverage import P_THRESHOLD, _supersession_edges, solve

cards = {"UN R10": {}, "UN R37": {}, "UN R48": {}, "UN R155": {}}

component = {
    "tech.has_electronics": {"value": True, "status": "known"},
    "tech.has_software": {"value": True, "status": "known"},
    "product.approval_level": {"value": "component", "status": "known"},
}
assert _run_horizontal(component, cards) == ["UN R10"]

vehicle = dict(component)
vehicle["product.approval_level"] = {"value": "vehicle", "status": "known"}
assert _run_horizontal(vehicle, cards) == ["UN R10", "UN R155"]

# A citation or scope overlap must never silently delete another regulation.
assert _supersession_edges(cards) == set()
scored = [
    {"regulation": "UN R37", "p": P_THRESHOLD, "scope_quotes": []},
    {"regulation": "UN R48", "p": P_THRESHOLD, "scope_quotes": []},
]
assert {x["regulation"] for x in solve(scored, cards)} == {"UN R37", "UN R48"}

print("selection safety tests passed")
