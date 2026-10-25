"""Offline semantic subgoal tests with fake model responses."""
import json

from regir.subgoal.semantic import extract_added, judge_group, pure_reordering_equivalent

assert pure_reordering_equivalent(
    "The ACPE shall control acceleration when the vehicle moves.",
    "When the vehicle moves, the ACPE shall control acceleration.",
)
assert not pure_reordering_equivalent("The lamp shall operate at 12 V.", "The lamp shall operate at 24 V.")
assert not pure_reordering_equivalent("The vehicle shall tow the trailer.", "The trailer shall tow the vehicle.")

old = "The lamp shall emit red light."
new = "The lamp shall emit amber light."
reqs = [{"id": "R-1", "text": old}]
fake_mod = lambda _s, _u: json.dumps({"decisions": [{
    "requirement_id": "R-1", "decision": "modified", "new_text": new,
    "old_quote": old, "new_quote": new,
}]})
decisions = judge_group(old, new, reqs, fake=fake_mod)
assert decisions[0]["decision"] == "modified"

fake_bad = lambda _s, _u: json.dumps({"decisions": [{
    "requirement_id": "R-1", "decision": "modified", "new_text": "Invented.",
    "old_quote": old, "new_quote": "not present",
}]})
assert judge_group(old, new, reqs, fake=fake_bad)[0]["decision"] == "unresolved"

fake_add = lambda _s, _u: json.dumps({"added": [{"new_text": new, "source_quote": new}]})
assert extract_added(old, new, [], fake=fake_add) == [{"new_text": new, "source_quote": new}]

print("subgoal semantic tests passed")
