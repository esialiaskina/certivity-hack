"""Offline tests for the hard atom verification gate."""
from regir.ingest.parse import Node
from regir.verify.requirements import fingerprint, verify_atom

node = Node("5.2", 7, 8, "5.2. The lamp shall not exceed 185 cd.")
atom = {
    "atom_id": "UN_TEST@1.0#5.2/a1", "regulation": "UN TEST", "version": "1.0",
    "paragraph": "5.2", "page": 7, "quote": "The lamp shall not exceed 185 cd.",
    "text": "The lamp shall not exceed 185 cd.",
}
assert verify_atom(atom, [node], "1.0") == {"valid": True, "errors": [], "warnings": []}

bad_page = {**atom, "page": 9}
assert not verify_atom(bad_page, [node], "1.0")["valid"]
bad_quote = {**atom, "quote": "The lamp shall survive 200 °C."}
assert not verify_atom(bad_quote, [node], "1.0")["valid"]
bad_version = {**atom, "version": "2.0"}
assert not verify_atom(bad_version, [node], "1.0")["valid"]

drift = {**atom, "text": "The lamp may exceed the limit."}
warnings = verify_atom(drift, [node], "1.0")["warnings"]
assert any("numeric anchors" in w for w in warnings)
assert any("negation" in w for w in warnings)

assert fingerprint(atom) == fingerprint(dict(atom))
assert fingerprint(atom) != fingerprint({**atom, "text": atom["text"] + " Extra."})

print("requirement verification tests passed")
