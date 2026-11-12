
"""
MELODIA AI - Geometric Intelligence Model Trainer
Version 1.0

Lightweight neural classifier for spatial relationships.

No external Python dependencies.
Designed for unattended GitHub Actions execution.
"""

import argparse
import json
import math
import random
import re
from pathlib import Path


RELATIONS = [
    "above",
    "below",
    "beside",
    "inside",
    "overlapping",
]


def tokenize(text):
    return re.findall(r"[a-z]+", text.lower())


def load_dataset(path):
    records = []

    with Path(path).open(
        "r", encoding="utf-8"
    ) as file:
        for line in file:
            if not line.strip():
                continue

            record = json.loads(line)

            prompt = record["prompt"]
            relation = record["scene"][
                "relationship"
            ]["relation"]

            if relation not in RELATIONS:
                raise ValueError(
                    "Unknown relationship: " + relation
                )

            records.append((prompt, relation))

    if not records:
        raise ValueError("Dataset is empty.")

    return records


def build_vocabulary(records):
    words = set()

    for prompt, _ in records:
        words.update(tokenize(prompt))

    return {
        word: index
        for index, word in enumerate(sorted(words))
    }


def encode(text, vocabulary):
    vector = [0.0] * len(vocabulary)

    for word in tokenize(text):
        index = vocabulary.get(word)

        if index is not None:
            vector[index] = 1.0

    return vector


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


class GeometricNeuralModel:
    """
    Small fully connected neural network.

    Input: bag-of-words features
    Hidden: tanh activation
    Output: five spatial relationship classes
    """

    def __init__(
        self,
        input_size,
        hidden_size=24,
        seed=1337,
    ):
        rng = random.Random(seed)

        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = len(RELATIONS)

        scale1 = 1.0 / math.sqrt(
            max(1, input_size)
        )

        scale2 = 1.0 / math.sqrt(
            max(1, hidden_size)
        )

        self.w1 = [
            [
                rng.uniform(-scale1, scale1)
                for _ in range(input_size)
            ]
            for _ in range(hidden_size)
        ]

        self.b1 = [0.0] * hidden_size

        self.w2 = [
            [
                rng.uniform(-scale2, scale2)
                for _ in range(hidden_size)
            ]
            for _ in range(self.output_size)
        ]

        self.b2 = [0.0] * self.output_size

    def forward(self, x):
        hidden = []

        for j in range(self.hidden_size):
            value = self.b1[j]

            for i, feature in enumerate(x):
                if feature:
                    value += self.w1[j][i] * feature

            hidden.append(math.tanh(value))

        logits = []

        for k in range(self.output_size):
            value = self.b2[k]

            for j in range(self.hidden_size):
                value += self.w2[k][j] * hidden[j]

            logits.append(value)

        return hidden, softmax(logits)

    def train_example(self, x, target, rate):
        hidden, probabilities = self.forward(x)

        output_gradient = probabilities[:]
        output_gradient[target] -= 1.0

        hidden_gradient = []

        for j in range(self.hidden_size):
            gradient = sum(
                self.w2[k][j] * output_gradient[k]
                for k in range(self.output_size)
            )

            gradient *= 1.0 - hidden[j] ** 2
            hidden_gradient.append(gradient)

        for k in range(self.output_size):
            for j in range(self.hidden_size):
                self.w2[k][j] -= (
                    rate
                    * output_gradient[k]
                    * hidden[j]
                )

            self.b2[k] -= (
                rate * output_gradient[k]
            )

        for j in range(self.hidden_size):
            for i, feature in enumerate(x):
                if feature:
                    self.w1[j][i] -= (
                        rate
                        * hidden_gradient[j]
                        * feature
                    )

            self.b1[j] -= (
                rate * hidden_gradient[j]
            )

        return -math.log(
            max(probabilities[target], 1e-12)
        )

    def predict(self, x):
        _, probabilities = self.forward(x)

        index = max(
            range(self.output_size),
            key=lambda k: probabilities[k],
        )

        return RELATIONS[index], probabilities[index]

    def export(self):
        return {
            "architecture": "bow_tanh_classifier",
            "input_size": self.input_size,
            "hidden_size": self.hidden_size,
            "classes": RELATIONS,
            "w1": self.w1,
            "b1": self.b1,
            "w2": self.w2,
            "b2": self.b2,
        }


def evaluate(model, records, vocabulary):
    correct = 0
    predictions = []

    for prompt, expected in records:
        vector = encode(prompt, vocabulary)

        predicted, confidence = model.predict(
            vector
        )

        if predicted == expected:
            correct += 1

        predictions.append({
            "prompt": prompt,
            "expected": expected,
            "predicted": predicted,
            "confidence": round(confidence, 5),
            "correct": predicted == expected,
        })

    return {
        "total": len(records),
        "correct": correct,
        "accuracy": round(
            correct / len(records), 5
        ),
        "predictions": predictions,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--data",
        default="melodia_training_output",
    )

    parser.add_argument(
        "--output",
        default="melodia_model_output",
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=15,
    )

    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.03,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
    )

    args = parser.parse_args()

    if args.epochs < 1:
        parser.error("Epochs must be positive.")

    if (
        not math.isfinite(args.learning_rate)
        or args.learning_rate <= 0
    ):
        parser.error(
            "Learning rate must be positive and finite."
        )

    data_folder = Path(args.data)
    output_folder = Path(args.output)

    training = load_dataset(
        data_folder / "train.jsonl"
    )

    evaluation = load_dataset(
        data_folder / "evaluation.jsonl"
    )

    vocabulary = build_vocabulary(training)

    model = GeometricNeuralModel(
        input_size=len(vocabulary),
        hidden_size=24,
        seed=args.seed,
    )

    rng = random.Random(args.seed)

    history = []

    print("MELODIA GEOMETRIC INTELLIGENCE")
    print("Training examples:", len(training))
    print("Evaluation examples:", len(evaluation))
    print("Vocabulary size:", len(vocabulary))

    baseline = evaluate(
        model, evaluation, vocabulary
    )

    print(
        "Initial evaluation accuracy:",
        baseline["accuracy"],
    )

    for epoch in range(1, args.epochs + 1):
        rng.shuffle(training)

        total_loss = 0.0

        for prompt, relation in training:
            vector = encode(
                prompt, vocabulary
            )

            target = RELATIONS.index(relation)

            total_loss += model.train_example(
                vector,
                target,
                args.learning_rate,
            )

        results = evaluate(
            model, evaluation, vocabulary
        )

        average_loss = total_loss / len(training)

        history.append({
            "epoch": epoch,
            "loss": round(average_loss, 6),
            "accuracy": results["accuracy"],
        })

        print(
            f"Epoch {epoch:02d} | "
            f"Loss: {average_loss:.5f} | "
            f"Accuracy: {results['accuracy']:.2%}"
        )

    final_results = evaluate(
        model, evaluation, vocabulary
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    model_file = output_folder / "model.json"

    model_file.write_text(
        json.dumps({
            "version": "1.0",
            "model": model.export(),
            "vocabulary": vocabulary,
        }),
        encoding="utf-8",
    )

    report = {
        "project": "MELODIA Geometric Intelligence",
        "version": "1.0",
        "training_examples": len(training),
        "evaluation_examples": len(evaluation),
        "baseline_accuracy": baseline["accuracy"],
        "final_accuracy": final_results["accuracy"],
        "epochs": args.epochs,
        "history": history,
        "evaluation": final_results,
    }

    (
        output_folder / "training_report.json"
    ).write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print()
    print("TRAINING COMPLETED")
    print("Model saved:", model_file)
    print(
        "Final evaluation accuracy:",
        final_results["accuracy"],
    )


if __name__ == "__main__":
    main()
