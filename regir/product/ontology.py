"""Facet ontology for the product formaliser.
A 'facet sheet' is a dict mapping facet_name -> FacetValue.
Each FacetValue carries the value, confidence status, and evidence (spec line or image region).
Product-agnostic: no lamp or bumper knowledge here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

STATUS = ("known", "assumed", "unknown")


@dataclass
class FacetValue:
    value: Any                 # str, list[str], or bool
    status: str = "unknown"    # known | assumed | unknown
    evidence: str = ""         # "spec line 7" / "image region: top-left" / "assumed: ..."

    def to_dict(self):
        return {"value": self.value, "status": self.status, "evidence": self.evidence}


# Canonical facet names and their type hints (for validation and UI display).
# Values: str = single string, list = multi-value, bool = boolean.
FACET_SCHEMA: dict[str, dict] = {
    "product.kind_path":       {"type": "str",  "desc": "Hierarchical kind, e.g. 'lighting > lamp > rear-lamp'"},
    "product.approval_level":  {"type": "str",  "desc": "vehicle | system | component | ESA | STU"},
    "vehicle.category":        {"type": "list", "desc": "UNECE vehicle categories, e.g. ['M1','N1']"},
    "function.set":            {"type": "list", "desc": "Functions the product performs, e.g. ['signalling','braking']"},
    "location":                {"type": "list", "desc": "Mounting location(s): front|rear|side|roof|interior|exterior"},
    "tech.has_electronics":    {"type": "bool", "desc": "True if product contains PCB, ECU, LED driver, or similar"},
    "tech.sensors":            {"type": "list", "desc": "Sensor types: radar|camera|ultrasonic|lidar|none"},
    "tech.has_software":       {"type": "bool", "desc": "True if product contains programmable firmware/software"},
    "tech.light_sources":      {"type": "list", "desc": "Light source types: none|LED|filament|gas-discharge"},
    "tech.optics":             {"type": "list", "desc": "Optical elements: lens|reflector|prism|none"},
    "material.classes":        {"type": "list", "desc": "Material classes present: polymer|glass|metal|composite|rubber"},
    "power.supply":            {"type": "list", "desc": "Supply voltages: none|12V|24V|HV"},
    "interfaces":              {"type": "list", "desc": "Communication interfaces: bus|wiring|wireless|none"},
    "part.list":               {"type": "list", "desc": "Named parts with their function (list of 'name: function' strings)"},
}

# Defaults used when a facet cannot be determined from the spec.
ASSUMED_DEFAULTS: dict[str, Any] = {
    "product.approval_level": "component",
    "vehicle.category": ["M1"],
    "tech.has_software": False,
    "tech.sensors": ["none"],
    "tech.light_sources": ["none"],
    "power.supply": ["12V"],
    "interfaces": ["wiring"],
}


def empty_sheet() -> dict[str, FacetValue]:
    return {k: FacetValue(value=None, status="unknown") for k in FACET_SCHEMA}


def from_dict(d: dict) -> dict[str, FacetValue]:
    """Reconstruct a facet sheet from serialised dict (output of extract_text)."""
    return {k: FacetValue(**v) if isinstance(v, dict) else FacetValue(value=v) for k, v in d.items()}


def to_dict(sheet: dict[str, FacetValue]) -> dict:
    return {k: v.to_dict() for k, v in sheet.items()}
