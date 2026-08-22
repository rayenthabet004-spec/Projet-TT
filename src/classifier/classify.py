"""
classify.py

Inference wrapper around the trained real-error-vs-informational classifier.
Not wired into src/rag/pipeline.py yet (that integration wasn't part of this
build's scope) -- this module is the standalone building block for it.

Usage (standalone):
    python -m src.classifier.classify "ORA-16111: log mining and apply setting up"

Usage (as a library, e.g. from generator.py later):
    from src.classifier.classify import ErrorClassifier
    clf = ErrorClassifier.load()
    is_error, confidence = clf.predict("ORA-00600: internal error code, arguments: [...]", context="...")
"""

import json
import os
import re
import sys
from dataclasses import dataclass

import joblib

from src.classifier.features import CombinedVectorizer  # noqa: F401 -- required for joblib.load to resolve the pickled vectorizer's class

MODELS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
MODEL_PATH = os.path.join(MODELS_DIR, "error_classifier.joblib")
VECTORIZER_PATH = os.path.join(MODELS_DIR, "error_classifier_vectorizer.joblib")
THRESHOLD_PATH = os.path.join(MODELS_DIR, "error_classifier_threshold.json")


@dataclass
class ClassificationResult:
    is_real_error: bool
    confidence: float  # probability of the predicted class

    def to_dict(self):
        return {"is_real_error": self.is_real_error, "confidence": round(self.confidence, 4)}


class ErrorClassifier:
    def __init__(self, model, vectorizer, informational_threshold: float = 0.5):
        self.model = model
        self.vectorizer = vectorizer
        self.informational_threshold = informational_threshold

    @classmethod
    def load(
        cls,
        model_path: str = MODEL_PATH,
        vectorizer_path: str = VECTORIZER_PATH,
        threshold_path: str = THRESHOLD_PATH,
    ) -> "ErrorClassifier":
        if not os.path.exists(model_path) or not os.path.exists(vectorizer_path):
            raise FileNotFoundError(
                f"Classifier model not found at {model_path}.\n"
                f"Train it first: python -m src.classifier.train_classifier"
            )
        model = joblib.load(model_path)
        vectorizer = joblib.load(vectorizer_path)

        threshold = 0.5
        if os.path.exists(threshold_path):
            with open(threshold_path, "r", encoding="utf-8") as f:
                threshold = json.load(f)["informational_threshold"]

        return cls(model, vectorizer, informational_threshold=threshold)

    def predict(self, raw_line: str, context: str = "") -> ClassificationResult:
        text = raw_line + " \n " + context
        X = self.vectorizer.transform([text])

        proba = self.model.predict_proba(X)[0]
        informational_col = list(self.model.classes_).index(0)
        informational_score = proba[informational_col]

        # Use the tuned threshold on the informational-class score, rather
        # than the model's default 0.5-cutoff .predict() -- this classifier
        # is meant to be a flag for human review (see PROGRESS.md), so the
        # threshold is deliberately tuned to favor recall on informational
        # messages over precision (see train_classifier.py).
        is_info = informational_score >= self.informational_threshold
        confidence = float(informational_score) if is_info else float(proba[1 - informational_col])

        # FIX 8: Classifier override rule:
        # If classifier predicts informational with < 60% confidence, but the raw line contains
        # explicit high-severity error tokens (FATAL, PANIC, ERROR), override to real error.
        if is_info and confidence < 0.60:
            if re.search(r"\b(FATAL|PANIC|ERROR)\b", raw_line, re.IGNORECASE):
                is_info = False
                confidence = float(proba[1 - informational_col])

        return ClassificationResult(is_real_error=not is_info, confidence=confidence)


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m src.classifier.classify "<log line>" ["<context>"]')
        sys.exit(1)

    raw_line = sys.argv[1]
    context = sys.argv[2] if len(sys.argv) > 2 else ""

    clf = ErrorClassifier.load()
    result = clf.predict(raw_line, context)
    label = "REAL ERROR" if result.is_real_error else "INFORMATIONAL (not a real error)"
    print(f"{label}  (confidence: {result.confidence:.1%})")


if __name__ == "__main__":
    main()
