"""Offline tests for evidence verification and explicit assumption scenarios."""
from regir.product.extract_text import _apply_assumptions, _verify_known_evidence
from regir.product.ontology import FacetValue, empty_sheet

spec = "Product name: Example\nContains an electronic control unit.\nMounted at the rear."
sheet = empty_sheet()
sheet["tech.has_electronics"] = FacetValue(
    True, "known", "spec line 2: 'Contains an electronic control unit.'"
)
sheet["location"] = FacetValue(["rear"], "known", "spec line 1: 'Mounted at the rear.'")
verified = _verify_known_evidence(spec, sheet)
assert verified["tech.has_electronics"].status == "known"
assert verified["location"].status == "unknown"

assert verified["vehicle.category"].status == "unknown"
_apply_assumptions(verified)
assert verified["vehicle.category"].status == "assumed"
assert verified["vehicle.category"].value == ["M1"]

print("product evidence tests passed")
