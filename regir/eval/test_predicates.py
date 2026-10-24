from regir.evaluate.predicates import evaluate
sheet = {"product.approval_level": {"value": "ESA", "status": "known"},
         "vehicle.category": {"value": "M1", "status": "known"},
         "tech.has_electronics": {"value": True, "status": "assumed"},
         "location": {"value": ["rear"], "status": "known"}}
assert evaluate({"facet": "product.approval_level", "op": "eq", "value": "ESA"}, sheet)[0] == "true"
assert evaluate({"facet": "product.approval_level", "op": "eq", "value": "vehicle"}, sheet)[0] == "false"
assert evaluate({"facet": "vehicle.category", "op": "in", "value": ["M1", "N1"]}, sheet)[0] == "true"
v, a, m = evaluate({"facet": "tech.has_electronics", "op": "truthy"}, sheet); assert (v, a) == ("true", ["tech.has_electronics"])
v, a, m = evaluate({"facet": "tech.sensors", "op": "has", "value": "radar"}, sheet); assert v == "unknown" and m == ["tech.sensors"]
# false dominates unknown in AND; true dominates unknown in OR
assert evaluate({"all": [{"facet": "tech.sensors", "op": "has", "value": "radar"}, {"facet": "vehicle.category", "op": "eq", "value": "L3"}]}, sheet)[0] == "false"
assert evaluate({"any": [{"facet": "tech.sensors", "op": "has", "value": "radar"}, {"facet": "location", "op": "has", "value": "rear"}]}, sheet)[0] == "true"
assert evaluate({"free": "where an optional lamp is mounted above 2100 mm"}, sheet)[0] == "unknown"
assert evaluate([{"facet": "vehicle.category", "op": "eq", "value": "M1"}], sheet)[0] == "true"   # list = AND
print("predicate tests passed")
