
"""
MELODIA AI - Unseen Language Intelligence Test
Version 1.0

Evaluates spatial-language generalization using
held-out vocabulary and sentence constructions.

No training or model modification occurs.

Python standard library only.
"""

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path


TEST_CASES = [
    # ABOVE
    ("A kite drifts skyward of the farmhouse.", "above"),
    ("The eagle soars at a greater altitude than the hill.", "above"),
    ("A helicopter hovers overhead relative to the stadium.", "above"),
    ("The lantern hangs aloft relative to the doorway.", "above"),
    ("The satellite occupies a loftier position than the planet.", "above"),

    # BELOW
    ("A tunnel runs subterraneously relative to the highway.", "below"),
    ("The diver descends to a depth greater than the vessel.", "below"),
    ("The cellar lies at a lower elevation than the kitchen.", "below"),
    ("A mineral deposit rests deep beneath the surface.", "below"),
    ("The foundation occupies a deeper level than the entrance.", "below"),

    # BESIDE
    ("The two cabins stand abreast of one another.", "beside"),
    ("A bench flanks the fountain.", "beside"),
    ("The bicycle occupies a neighboring position to the gate.", "beside"),
    ("The two boats are positioned laterally to one another.", "beside"),
    ("The cottage stands immediately alongside the barn.", "beside"),

    # INSIDE
    ("The gemstone is encapsulated by transparent resin.", "inside"),
    ("A document is housed within the archive box.", "inside"),
    ("The pearl is enveloped by the oyster shell.", "inside"),
    ("A tiny mechanism is embedded in the device.", "inside"),
    ("The figurine occupies the interior of the display case.", "inside"),

    # OVERLAPPING
    ("Two disks have a shared intersection.", "overlapping"),
    ("The colored patches partially coincide.", "overlapping"),
    ("Two silhouettes are superimposed across one another.", "overlapping"),
    ("The circular regions possess a common area.", "overlapping"),
    ("The two panels have intersecting boundaries.", "overlapping"),
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
    words = tokenize(prompt)

    known_words = []
    unknown_words = []

    for word in words:
        index = vocabulary.get(word)

        if index is None:
            unknown_words.append(word)
        else:
            known_words.append(word)
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

    return {
        "predicted": model["classes"][best],
        "confidence": round(probabilities[best], 5),
        "known_words": known_words,
        "unknown_words": unknown_words
    }


def evaluate(model_data):
    results = []
    correct = 0

    by_relation = defaultdict(
        lambda: {"correct": 0, "total": 0}
    )

    for prompt, expected in TEST_CASES:
        prediction = predict(prompt, model_data)

        passed = prediction["predicted"] == expected

        if passed:
            correct += 1
            by_relation[expected]["correct"] += 1

        by_relation[expected]["total"] += 1

        results.append({
            "prompt": prompt,
            "expected": expected,
            "predicted": prediction["predicted"],
            "confidence": prediction["confidence"],
            "correct": passed,
            "known_words": prediction["known_words"],
            "unknown_words": prediction["unknown_words"]
        })

    total = len(TEST_CASES)

    return {
        "project": "MELODIA AI",
        "test_version": "1.0",
        "test_type": "unseen_language",
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 5),
        "by_relation": dict(by_relation),
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
        default="melodia_unseen_language_output"
    )

    args = parser.parse_args()

    model_path = Path(args.model)

    if not model_path.is_file():
        raise FileNotFoundError(
            f"Trained model not found: {model_path}"
        )

    model_data = json.loads(
        model_path.read_text(encoding="utf-8")
    )

    report = evaluate(model_data)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    report_path = (
        output / "unseen_language_report.json"
    )

    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    print("MELODIA UNSEEN-LANGUAGE TEST")
    print("Total:", report["total"])
    print("Correct:", report["correct"])
    print(
        "Accuracy:",
        f"{report['accuracy']:.2%}"
    )

    for relation, result in report["by_relation"].items():
        print(
            relation,
            f"{result['correct']}/{result['total']}"
        )

    print()

    for result in report["results"]:
        status = (
            "PASS" if result["correct"] else "FAIL"
        )

        print(
            f"{status} | {result['expected']} | "
            f"{result['predicted']} | "
            f"{result['prompt']}"
        )

    print()
    print("Report:", report_path)


if __name__ == "__main__":
    main()
