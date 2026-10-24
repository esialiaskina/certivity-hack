"""Offline tests with a fake LLM: grounding check must reject invented quotes, keep verbatim ones."""
import json
from regir.compile import atomize
from regir.ingest.parse import Node
from regir import llm

n = Node("5.2", 7, 7, "5.2. The lamp shall emit red light.\nThe intensity shall not exceed 185 cd.")
good = lambda s, u: json.dumps({"atoms": [
    {"quote": "The lamp shall emit red light.", "text": "The lamp shall emit red light.", "role": "performance", "modality": "shall"},
    {"quote": "The intensity  shall not exceed\n185 cd.", "text": "The lamp intensity shall not exceed 185 cd.", "role": "performance", "modality": "shall_not"}]})
invented = lambda s, u: json.dumps({"atoms": [{"quote": "The lamp shall be waterproof to IP67.", "text": "x", "role": "performance"}]})
llm.CACHE = __import__("pathlib").Path("/tmp/regir_test_cache"); llm.CACHE.mkdir(exist_ok=True)
for f in llm.CACHE.glob("*"): f.unlink()
atoms, bad = atomize.atomize_node("UN R999", "1.0.0", n, ["Requirements"], fake=good)
assert len(atoms) == 2 and bad == 0 and atoms[1]["page"] == 7, (atoms, bad)
for f in llm.CACHE.glob("*"): f.unlink()
atoms, bad = atomize.atomize_node("UN R999", "1.0.0", n, [], fake=invented)
assert atoms == [] and bad >= 1, (atoms, bad)
assert llm.parse_json('chatter ```json\n{"atoms": []}\n``` bye') == {"atoms": []}
print("atomize tests passed")
