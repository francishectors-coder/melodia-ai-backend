
"""
MELODIA AI - Geometric Language Generalization Test
Version 1.0

Tests a trained spatial classifier using unfamiliar
natural-language descriptions.

Python standard library only.
"""

import argparse
import json
import math
import re
from pathlib import Path


TEST_CASES = [
    ("A bird is above a tree.", "above"),
    ("A bird is hovering over a tree.", "above"),
    ("A cloud floats higher than a mountain.", "above"),
    ("A balloon rises over a building.", "above"),
    ("The moon appears in the sky over a village.", "above"),

    ("A stone is below a bridge.", "below"),
    ("A fish swims beneath a boat.", "below"),
    ("A child sits under a table.", "below"),
    ("Roots grow underneath the soil.", "below"),
    ("A submarine travels under a ship.", "below"),

    ("A house stands beside a river.", "beside"),
    ("A bicycle is next to a wall.", "beside"),
    ("A dog sits alongside its owner.", "beside"),
    ("Two trees stand side by side.", "beside"),
    ("A farmer works near a tractor.", "beside"),

    ("A bird is inside a cage.", "inside"),
    ("A child plays within a room.", "inside"),
    ("A fish swims in an aquarium.", "inside"),
    ("A letter rests in an envelope.", "inside"),
    ("A seed lies within a fruit.", "inside"),

    ("Two circles are overlapping.", "overlapping"),
    ("Two shapes partially cover each other.", "overlapping"),
    ("Two rings intersect.", "overlapping"),
    ("Two colored regions share the same space.", "overlapping"),
    ("Two rectangles overlap at their edges.", "overlapping"),
]


def tokenize(text):
    return re.findall(r"[a-z]+", text.lower())


def softmax(values):
    maximum = max(values)

    exponents = [
        math.exp(value - maximum)
        for value in values
    ]

    total = sum(exponents)

    return [
        value / total
        for value in exponents
    ]


def predict(prompt, model_data):
    model = model_data["model"]
    vocabulary = model_data["vocabulary"]

    vector = [0.0] * model["input_size"]

    for word in tokenize(prompt):
        index = vocabulary.get(word)

        if index is not None:
            vector[index] = 1.0

    hidden = []

    for j in range(model["hidden_size"]):
        value = model["b1"][j]

        for i, feature in enumerate(vector):
            if feature:
                value += model["w1"][j][i] * feature

        hidden.append(math.tanh(value))

    logits = []

    for k in range(len(model["classes"])):
        value = model["b2"][k]

        for j in range(model["hidden_size"]):
            value += model["w2"][k][j] * hidden[j]

        logits.append(value)

    probabilities = softmax(logits)

    best = max(
        range(len(probabilities)),
        key=lambda index: probabilities[index]
    )

    return (
        model["classes"][best],
        probabilities[best]
    )


def run_tests(model_data):
    results = []
    correct = 0

    for prompt, expected in TEST_CASES:
        predicted, confidence = predict(
            prompt, model_data
        )

        passed = predicted == expected

        if passed:
            correct += 1

        results.append({
            "prompt": prompt,
            "expected": expected,
            "predicted": predicted,
            "confidence": round(confidence, 5),
            "correct": passed
        })

    return {
        "total": len(TEST_CASES),
        "correct": correct,
        "accuracy": round(
            correct / len(TEST_CASES), 5
        ),
        "results": results
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        default="melodia_model_output/model.json"
    )

    parser.add_argument(
        "--output",
        default="melodia_generalization_output"
    )

    args = parser.parse_args()

    model_path = Path(args.model)

    if not model_path.is_file():
        raise FileNotFoundError(
            f"Model file not found: {model_path}"
        )

    model_data = json.loads(
        model_path.read_text(encoding="utf-8")
    )

    report = run_tests(model_data)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    report_file = (
        output / "generalization_report.json"
    )

    report_file.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    print("MELODIA LANGUAGE GENERALIZATION TEST")
    print("Total tests:", report["total"])
    print("Correct:", report["correct"])
    print(
        "Accuracy:",
        f"{report['accuracy']:.2%}"
    )

    print()

    for result in report["results"]:
        status = (
            "PASS"
            if result["correct"]
            else "FAIL"
        )

        print(
            f"{status}: "
            f"{result['prompt']} "
            f"Expected={result['expected']} "
            f"Predicted={result['predicted']}"
        )

    print()
    print("Report saved:", report_file)


if __name__ == "__main__":
    main()
