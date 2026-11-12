"""MELODIA AI geometric object learner V1.1.

Learns component roles, normalized bounding boxes and primitive types from
structured examples. Standard-library only. This is a small demonstration,
not a general-purpose visual model.
"""
import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

SHAPES = {"circle", "ellipse", "rectangle", "triangle", "polygon"}
FEATURES = ["roundness", "elongation", "angularity", "verticality", "symmetry", "component_count"]

# Each tuple: role, primitive, normalized center x/y, width, height, color.
# Two independently positioned examples per category demonstrate averaging.
EXAMPLES = {
    "tree": [
        [("trunk", "rectangle", .50,.73,.14,.46,"#85522f"), ("canopy", "ellipse", .50,.32,.62,.55,"#348c45")],
        [("trunk", "rectangle", .52,.74,.13,.44,"#85522f"), ("canopy", "ellipse", .49,.33,.59,.53,"#348c45")],
    ],
    "house": [
        [("body", "rectangle", .50,.65,.64,.51,"#d8a46a"), ("roof", "triangle", .50,.30,.78,.40,"#ad5142"), ("door", "rectangle", .50,.78,.16,.25,"#714d3b")],
        [("body", "rectangle", .51,.64,.62,.52,"#d8a46a"), ("roof", "triangle", .50,.29,.76,.38,"#ad5142"), ("door", "rectangle", .51,.78,.15,.24,"#714d3b")],
    ],
    "vehicle": [
        [("body", "rectangle", .50,.57,.75,.34,"#4a89b5"), ("wheel_left", "circle", .27,.77,.18,.18,"#333333"), ("wheel_right", "circle", .73,.77,.18,.18,"#333333")],
        [("body", "rectangle", .50,.56,.73,.33,"#4a89b5"), ("wheel_left", "circle", .28,.76,.17,.17,"#333333"), ("wheel_right", "circle", .72,.76,.17,.17,"#333333")],
    ],
    "animal": [
        [("body", "ellipse", .49,.52,.55,.36,"#ad8c70"), ("head", "circle", .77,.39,.24,.24,"#ad8c70"), ("leg_left", "rectangle", .33,.76,.10,.29,"#ad8c70"), ("leg_right", "rectangle", .62,.76,.10,.29,"#ad8c70")],
        [("body", "ellipse", .50,.52,.54,.37,"#ad8c70"), ("head", "circle", .76,.40,.23,.23,"#ad8c70"), ("leg_left", "rectangle", .34,.76,.10,.28,"#ad8c70"), ("leg_right", "rectangle", .63,.76,.10,.28,"#ad8c70")],
    ],
    "flower": [
        [("stem", "rectangle", .50,.70,.05,.43,"#36824c"), ("petal_left", "ellipse", .37,.34,.24,.28,"#e781aa"), ("petal_right", "ellipse", .63,.34,.24,.28,"#e781aa"), ("petal_top", "ellipse", .50,.23,.23,.27,"#e781aa"), ("center", "circle", .50,.39,.19,.19,"#e9bb42")],
        [("stem", "rectangle", .50,.71,.05,.42,"#36824c"), ("petal_left", "ellipse", .38,.35,.23,.27,"#e781aa"), ("petal_right", "ellipse", .62,.35,.23,.27,"#e781aa"), ("petal_top", "ellipse", .50,.24,.22,.26,"#e781aa"), ("center", "circle", .50,.40,.18,.18,"#e9bb42")],
    ],
}


def train_prototypes(examples):
    result = {}
    for category, samples in examples.items():
        if not samples:
            raise ValueError("Empty category")
        grouped = defaultdict(list)
        for sample in samples:
            seen = set()
            for role, shape, x, y, w, h, color in sample:
                if role in seen or shape not in SHAPES:
                    raise ValueError("Duplicate role or unsupported shape")
                seen.add(role)
                if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x,y,w,h)) or w == 0 or h == 0:
                    raise ValueError("Invalid normalized geometry")
                grouped[role].append((shape,x,y,w,h,color))
        parts = []
        for role, observations in grouped.items():
            if len(observations) != len(samples):
                raise ValueError("All examples must contain the same roles")
            shape = Counter(p[0] for p in observations).most_common(1)[0][0]
            color = Counter(p[5] for p in observations).most_common(1)[0][0]
            geometry = [round(sum(p[i] for p in observations)/len(observations), 5) for i in range(1,5)]
            parts.append(dict(role=role, shape=shape, x=geometry[0], y=geometry[1], width=geometry[2], height=geometry[3], color=color))
        result[category] = {"training_examples": len(samples), "parts": parts,
                            "features": [0.5, 0.5, 0.5, 0.5, 0.5, min(1.0, len(parts)/5)],
                            "component_distribution": {s: sum(p['shape']==s for p in parts)/len(parts) for s in sorted(SHAPES)}}
    return result


def generate_representation(name, prototypes, seed=1337):
    if name not in prototypes:
        return {"status": "unknown", "requested_object": name, "reason": "Object has no learned prototype"}
    prototype = prototypes[name]
    # Preserve learned roles and geometry rather than sampling unrelated shapes.
    parts = [dict(id=f"component_{i}", **part) for i, part in enumerate(prototype["parts"], 1)]
    return {"status": "generated", "object": name, "features": prototype["features"],
            "components": parts, "method": "averaged_structured_component_examples", "seed": seed}


def render_svg(representation, width=512, height=288):
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(width), height=str(height), viewBox=f"0 0 {width} {height}")
    ET.SubElement(svg, "rect", width=str(width), height=str(height), fill="#ffffff")
    for part in representation.get("components", []):
        cx, cy = part["x"]*width, part["y"]*height
        w, h = part["width"]*width, part["height"]*height
        color = part["color"]
        shape = part["shape"]
        if shape == "rectangle":
            ET.SubElement(svg, "rect", x=f"{cx-w/2:.2f}", y=f"{cy-h/2:.2f}", width=f"{w:.2f}", height=f"{h:.2f}", fill=color)
        elif shape in ("ellipse", "circle"):
            # Elliptical pixel scaling preserves normalized proportions.
            ET.SubElement(svg, "ellipse", cx=f"{cx:.2f}", cy=f"{cy:.2f}", rx=f"{w/2:.2f}", ry=f"{h/2:.2f}", fill=color)
        elif shape == "triangle":
            pts = [(cx,cy-h/2),(cx-w/2,cy+h/2),(cx+w/2,cy+h/2)]
            ET.SubElement(svg, "polygon", points=" ".join(f"{x:.2f},{y:.2f}" for x,y in pts), fill=color)
        else:
            pts = [(cx-w/2,cy),(cx-w/4,cy-h/2),(cx+w/4,cy-h/2),(cx+w/2,cy),(cx+w/4,cy+h/2),(cx-w/4,cy+h/2)]
            ET.SubElement(svg, "polygon", points=" ".join(f"{x:.2f},{y:.2f}" for x,y in pts), fill=color)
    return ET.tostring(svg, encoding="unicode")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="melodia_object_learning_output")
    parser.add_argument("--object", default="tree")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    prototypes = train_prototypes(EXAMPLES)
    # Keep version 1.0 for compatibility with the existing GitHub workflow.
    model = {"project": "MELODIA AI", "version": "1.0", "learner_version": "1.1",
             "model_type": "geometric_object_prototypes", "features": FEATURES,
             "shapes": sorted(SHAPES), "prototypes": prototypes}
    (out/"object_model.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    representation = generate_representation(args.object, prototypes, args.seed)
    (out/"object_representation.json").write_text(json.dumps(representation, indent=2), encoding="utf-8")
    if representation["status"] == "generated":
        (out/"object_preview.svg").write_text(render_svg(representation), encoding="utf-8")
    print("MELODIA GEOMETRIC OBJECT LEARNER V1.1")
    print("Learned categories:", len(prototypes))
    print("Requested:", args.object)
    print("Status:", representation["status"])
    print("Output:", out)


if __name__ == "__main__":
    main()
