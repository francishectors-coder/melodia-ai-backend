
"""MELODIA AI - Universal Object Schema V1.4

Converts learned geometric component models into a reusable,
category-independent object representation.

Standard library only.
Preserves the existing V1.3 engine and production video generator.
"""

import argparse
import json
import math
from pathlib import Path

SCHEMA_VERSION = "1.4"

SUPPORTED_SHAPES = {
    "circle",
    "ellipse",
    "rectangle",
    "triangle",
    "polygon",
}

GEOMETRY_FIELDS = (
    "dx",
    "dy",
    "width",
    "height",
)


def finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_component(component):
    """Validate a category-independent component."""

    required = {
        "id",
        "role",
        "parent",
        "geometry",
        "appearance",
        "constraints",
    }

    if not required.issubset(component):
        raise ValueError(
            "Component is missing required fields"
        )

    if not isinstance(component["id"], str):
        raise ValueError("Invalid component ID")

    if not component["id"]:
        raise ValueError("Empty component ID")

    if not isinstance(component["role"], str):
        raise ValueError("Invalid component role")

    if not component["role"]:
        raise ValueError("Empty component role")

    parent = component["parent"]

    if parent is not None and not isinstance(
        parent, str
    ):
        raise ValueError("Invalid parent reference")

    geometry = component["geometry"]

    if not isinstance(geometry, dict):
        raise ValueError("Invalid geometry")

    for field in GEOMETRY_FIELDS:
        value = geometry.get(field)

        if not finite_number(value):
            raise ValueError(
                f"Invalid geometry field: {field}"
            )

    if (
        geometry["width"] <= 0
        or geometry["height"] <= 0
    ):
        raise ValueError(
            "Component dimensions must be positive"
        )

    appearance = component["appearance"]

    if not isinstance(appearance, dict):
        raise ValueError("Invalid appearance")

    shape = appearance.get("shape")

    if shape not in SUPPORTED_SHAPES:
        raise ValueError(
            f"Unsupported shape: {shape}"
        )

    color = appearance.get("color")

    if not isinstance(color, str) or not color:
        raise ValueError("Invalid color")

    constraints = component["constraints"]

    if not isinstance(constraints, dict):
        raise ValueError("Invalid constraints")

    frequency = constraints.get(
        "overlap_frequency"
    )

    if not finite_number(frequency):
        raise ValueError(
            "Invalid overlap frequency"
        )

    if not 0 <= frequency <= 1:
        raise ValueError(
            "Overlap frequency outside range"
        )

    deviations = component.get(
        "training_deviations", []
    )

    if not isinstance(deviations, list):
        raise ValueError(
            "Invalid training deviations"
        )

    for deviation in deviations:
        if not isinstance(deviation, dict):
            raise ValueError(
                "Invalid deviation record"
            )

        for field in GEOMETRY_FIELDS:
            if not finite_number(
                deviation.get(field)
            ):
                raise ValueError(
                    f"Invalid deviation: {field}"
                )

    return True


def validate_object(obj):
    """Validate component references and hierarchy."""

    if not isinstance(obj, dict):
        raise ValueError("Object must be a dictionary")

    components = obj.get("components")

    if not isinstance(components, list):
        raise ValueError(
            "Object components must be a list"
        )

    if not components:
        raise ValueError(
            "Object must contain components"
        )

    roles = {}

    for component in components:
        validate_component(component)

        role = component["role"]

        if role in roles:
            raise ValueError(
                f"Duplicate component role: {role}"
            )

        roles[role] = component

    root = obj.get("root")

    if root not in roles:
        raise ValueError(
            "Object root is missing"
        )

    roots = [
        component["role"]
        for component in components
        if component["parent"] is None
    ]

    if roots != [root]:
        raise ValueError(
            "Object must have exactly one root"
        )

    for component in components:
        role = component["role"]
        parent = component["parent"]

        if parent is None:
            continue

        if parent not in roles:
            raise ValueError(
                f"Missing parent for {role}"
            )

        if parent == role:
            raise ValueError(
                "Component cannot parent itself"
            )

    # Detect cyclic parent relationships.
    for role in roles:
        visited = set()
        current = role

        while current is not None:
            if current in visited:
                raise ValueError(
                    "Cyclic component relationships"
                )

            visited.add(current)
            current = roles[current]["parent"]

    return True


def convert_category(category, learned):
    """Convert one V1.3 learned category to V1.4."""

    components = []

    for index, part in enumerate(
        learned["parts"], start=1
    ):
        geometry = {
            field: part[field]
            for field in GEOMETRY_FIELDS
        }

        deviations = [
            {
                field: record[field]
                for field in GEOMETRY_FIELDS
            }
            for record in part.get(
                "deviations", []
            )
        ]

        component = {
            "id": f"component_{index}",
            "role": part["role"],
            "parent": part["parent"],
            "geometry": geometry,
            "appearance": {
                "shape": part["shape"],
                "color": part["color"],
            },
            "constraints": {
                "overlap_frequency": part[
                    "overlap_frequency"
                ],
            },
            "training_deviations": deviations,
        }

        components.append(component)

    obj = {
        "schema_version": SCHEMA_VERSION,
        "object_type": category,
        "root": learned["root"],
        "training_examples": learned[
            "training_examples"
        ],
        "components": components,
    }

    validate_object(obj)

    return obj


def build_universal_library(learned_model):
    """Convert all learned categories to one library."""

    objects = {}

    for category, learned in sorted(
        learned_model.items()
    ):
        objects[category] = convert_category(
            category, learned
        )

    return {
        "project": "MELODIA AI",
        "schema_version": SCHEMA_VERSION,
        "representation": (
            "universal_geometric_component_graph"
        ),
        "objects": objects,
    }


def load_existing_model(path):
    """Load a previously generated relationship model."""

    data = json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )

    categories = data.get("categories")

    if not isinstance(categories, dict):
        raise ValueError(
            "Model has no category dictionary"
        )

    return categories


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Optional existing relationship_model.json"
        ),
    )

    parser.add_argument(
        "--output",
        default="melodia_universal_output",
    )

    args = parser.parse_args()

    if args.model:
        learned = load_existing_model(
            args.model
        )
    else:
        # Import only when needed.
        # The V1.3 learner remains unchanged.
        from melodia_component_relationship_learner import (
            train,
        )
        from melodia_geometric_object_learner import (
            EXAMPLES,
        )

        learned = train(EXAMPLES)

    library = build_universal_library(
        learned
    )

    output = Path(args.output)

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        output / "universal_object_library.json"
    )

    destination.write_text(
        json.dumps(
            library,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "MELODIA UNIVERSAL OBJECT SCHEMA V1.4"
    )
    print(
        "Objects:",
        len(library["objects"]),
    )
    print(
        "Components:",
        sum(
            len(obj["components"])
            for obj in library[
                "objects"
            ].values()
        ),
    )
    print(
        "Validation: PASSED"
    )
    print(
        "Output:",
        destination,
    )


if __name__ == "__main__":
    main()
