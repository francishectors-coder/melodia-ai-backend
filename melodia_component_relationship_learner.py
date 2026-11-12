"""MELODIA AI - Component Relationship Learner V1.0.

Learns relative offsets and overlap relationships from the structured
examples in melodia_geometric_object_learner.py. Standard library only.
This is a geometric proof of concept, not semantic object understanding.
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from melodia_geometric_object_learner import EXAMPLES, render_svg


def boxes_overlap(a, b):
    """True when normalized bounding boxes intersect with positive area."""
    return (abs(a["x"] - b["x"]) * 2 < a["width"] + b["width"]
            and abs(a["y"] - b["y"]) * 2 < a["height"] + b["height"])


def parse_sample(sample):
    return {
        role: {"role": role, "shape": shape, "x": x, "y": y,
               "width": width, "height": height, "color": color}
        for role, shape, x, y, width, height, color in sample
    }


def choose_tree(sample):
    """Choose a large root, then attach each remaining part to its nearest
    already attached part. This is a geometric heuristic, not a learned
    semantic hierarchy.
    """
    root = max(sample, key=lambda r: (sample[r]["width"] * sample[r]["height"], -len(r)))
    attached = {root}
    parents = {}
    while len(attached) < len(sample):
        candidates = []
        for child in sample:
            if child in attached:
                continue
            for parent in attached:
                a, b = sample[child], sample[parent]
                dist = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                # Prefer overlapping parts; distance breaks ties.
                score = dist - (0.5 if boxes_overlap(a, b) else 0)
                candidates.append((score, child, parent))
        _, child, parent = min(candidates)
        parents[child] = parent
        attached.add(child)
    return root, parents


def train(examples):
    model = {}
    for category, samples in sorted(examples.items()):
        parsed = [parse_sample(sample) for sample in samples]
        if not parsed:
            raise ValueError(f"No examples for {category}")
        roles = set(parsed[0])
        if not roles or any(set(sample) != roles for sample in parsed):
            raise ValueError(f"Inconsistent component roles for {category}")
        for sample in parsed:
            for part in sample.values():
                if not all(math.isfinite(part[k]) and 0 <= part[k] <= 1
                           for k in ("x", "y", "width", "height")):
                    raise ValueError("Invalid geometry")
                if part["width"] == 0 or part["height"] == 0:
                    raise ValueError("Zero-size component")

        root, parents = choose_tree(parsed[0])
        observations = defaultdict(list)
        for sample in parsed:
            for role, part in sample.items():
                parent = parents.get(role)
                reference = sample[parent] if parent else None
                observations[role].append({
                    "shape": part["shape"], "color": part["color"],
                    "width": part["width"], "height": part["height"],
                    "dx": part["x"] - reference["x"] if reference else part["x"],
                    "dy": part["y"] - reference["y"] if reference else part["y"],
                    "overlap": boxes_overlap(part, reference) if reference else False,
                })
        parts = []
        for role in sorted(roles):
            obs = observations[role]
            mean = lambda key: round(sum(o[key] for o in obs) / len(obs), 6)
            parts.append({
                "role": role, "parent": parents.get(role),
                "shape": Counter(o["shape"] for o in obs).most_common(1)[0][0],
                "color": Counter(o["color"] for o in obs).most_common(1)[0][0],
                "dx": mean("dx"), "dy": mean("dy"),
                "width": mean("width"), "height": mean("height"),
                "overlap_frequency": mean("overlap"),
            })
        model[category] = {"root": root, "training_examples": len(samples), "parts": parts}
    return model


def reconstruct(category, model):
    if category not in model:
        return {"status": "unknown", "requested_object": category,
                "reason": "No training examples for requested object"}
    learned = model[category]
    pending = {part["role"]: part for part in learned["parts"]}
    placed = {}
    components = []
    while pending:
        progress = False
        for role, part in list(pending.items()):
            parent = part["parent"]
            if parent is not None and parent not in placed:
                continue
            x = part["dx"] + (placed[parent]["x"] if parent else 0)
            y = part["dy"] + (placed[parent]["y"] if parent else 0)
            component = {
                "id": f"component_{len(components)+1}", "role": role,
                "parent": parent, "shape": part["shape"],
                "color": part["color"], "x": round(x, 6), "y": round(y, 6),
                "width": part["width"], "height": part["height"],
            }
            placed[role] = component
            components.append(component)
            del pending[role]
            progress = True
        if not progress:
            raise ValueError("Cyclic or missing parent relationships")
    return {"status": "generated", "object": category,
            "method": "averaged_relative_component_offsets",
            "components": components}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", default="tree")
    parser.add_argument("--output", default="melodia_relationship_output")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    learned = train(EXAMPLES)
    model = {"project": "MELODIA AI", "version": "1.0",
             "model_type": "geometric_component_relationships",
             "categories": learned}
    (out / "relationship_model.json").write_text(
        json.dumps(model, indent=2), encoding="utf-8")
    representation = reconstruct(args.object, learned)
    (out / "relationship_representation.json").write_text(
        json.dumps(representation, indent=2), encoding="utf-8")
    if representation["status"] == "generated":
        (out / "relationship_preview.svg").write_text(
            render_svg(representation), encoding="utf-8")
    print("MELODIA COMPONENT RELATIONSHIP LEARNER V1.0")
    print("Categories:", len(learned))
    print("Requested:", args.object)
    print("Status:", representation["status"])
    print("Output:", out)


if __name__ == "__main__":
    main()
