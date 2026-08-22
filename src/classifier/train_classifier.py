"""
train_classifier.py

Trains the "is this a real actionable error, or just an informational
message" classifier. Improved version: combines word + character n-gram
TF-IDF features, compares Logistic Regression against a calibrated Linear
SVM, and tunes the decision threshold instead of using the default 0.5 --
since this classifier is meant to be a flag for human review (not a silent
auto-filter), recall on the rare "informational" class matters more than
precision, so the threshold is chosen accordingly.

Usage:
    python -m src.classifier.train_classifier
"""

import json
import os

import joblib
import numpy as np
from scipy.sparse import hstack
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_recall_fscore_support,
)
from sklearn.svm import LinearSVC

from src.classifier.features import CombinedVectorizer


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_text(row):
    """Feature text: the raw matched line plus its surrounding context. Both
    are included because some informational-vs-error distinctions only show
    up in context (e.g. what precedes/follows), not the bare line."""
    return row["text"] + " \n " + row.get("context", "")


def find_best_threshold(y_true, scores, target_recall=0.90):
    """Sweep thresholds on the informational-class score and report:
    (a) the threshold maximizing F1, and (b) the lowest threshold that still
    hits target_recall, since this classifier's intended use (flag for
    human review) tolerates false positives better than missed
    informational messages. Returns both so you can pick either."""
    precision, recall, thresholds = precision_recall_curve(y_true, scores, pos_label=0)
    # precision_recall_curve returns arrays 1 longer than thresholds; align them
    precision, recall = precision[:-1], recall[:-1]

    f1_scores = np.where((precision + recall) > 0, 2 * precision * recall / (precision + recall + 1e-12), 0)
    best_f1_idx = int(np.argmax(f1_scores))

    candidates = np.where(recall >= target_recall)[0]
    best_recall_idx = int(candidates[np.argmax(precision[candidates])]) if len(candidates) else best_f1_idx

    return {
        "best_f1": {
            "threshold": float(thresholds[best_f1_idx]),
            "precision": float(precision[best_f1_idx]),
            "recall": float(recall[best_f1_idx]),
            "f1": float(f1_scores[best_f1_idx]),
        },
        "target_recall": {
            "threshold": float(thresholds[best_recall_idx]),
            "precision": float(precision[best_recall_idx]),
            "recall": float(recall[best_recall_idx]),
            "f1": float(f1_scores[best_recall_idx]),
        },
    }


def main():
    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_dir = os.path.join(base_dir, "data", "classifier")
    models_dir = os.path.join(base_dir, "models")
    os.makedirs(models_dir, exist_ok=True)

    # Prefer v2 (multi-engine) dataset; fall back to original Oracle-only v1
    def _pick(name_v2, name_v1):
        p = os.path.join(data_dir, name_v2)
        return p if os.path.isfile(p) else os.path.join(data_dir, name_v1)

    train_path = _pick("train_v2.jsonl", "train.jsonl")
    val_path   = _pick("val_v2.jsonl",   "val.jsonl")
    train_rows = load_jsonl(train_path)
    val_rows   = load_jsonl(val_path)
    print(f"Train: {len(train_rows)} examples ({train_path})")
    print(f"Val:   {len(val_rows)} examples ({val_path})")

    X_train_text = [build_text(r) for r in train_rows]
    y_train = [r["label"] for r in train_rows]
    X_val_text = [build_text(r) for r in val_rows]
    y_val = [r["label"] for r in val_rows]

    vectorizer = CombinedVectorizer()
    X_train = vectorizer.fit_transform(X_train_text)
    X_val = vectorizer.transform(X_val_text)

    candidates = {
        "LogisticRegression": LogisticRegression(class_weight="balanced", max_iter=1000, C=1.0),
        "LinearSVC (calibrated)": CalibratedClassifierCV(
            LinearSVC(class_weight="balanced", max_iter=5000, C=1.0), cv=3
        ),
    }

    results = {}
    for name, clf in candidates.items():
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_val)
        _, _, f1_informational, _ = precision_recall_fscore_support(y_val, y_pred, average="binary", pos_label=0)
        results[name] = {"clf": clf, "f1_informational": f1_informational}
        print(f"\n=== {name} ===")
        print(classification_report(y_val, y_pred, target_names=["informational", "real_error"], digits=3))

    best_name = max(results, key=lambda n: results[n]["f1_informational"])
    best_clf = results[best_name]["clf"]
    print(f"\n>>> Best model by informational-class F1: {best_name} (F1={results[best_name]['f1_informational']:.3f})")

    # probability of the "informational" (label=0) class, for threshold tuning
    proba = best_clf.predict_proba(X_val)
    informational_col = list(best_clf.classes_).index(0)
    informational_scores = proba[:, informational_col]

    thresholds = find_best_threshold(y_val, informational_scores, target_recall=0.90)
    print("\n=== Threshold tuning (informational-class score) ===")
    print(f"Default (0.5 via .predict()): see report above")
    print(f"Best-F1 threshold:      {thresholds['best_f1']['threshold']:.3f}  "
          f"precision={thresholds['best_f1']['precision']:.3f} recall={thresholds['best_f1']['recall']:.3f} "
          f"f1={thresholds['best_f1']['f1']:.3f}")
    print(f"Target-recall(0.90) threshold: {thresholds['target_recall']['threshold']:.3f}  "
          f"precision={thresholds['target_recall']['precision']:.3f} recall={thresholds['target_recall']['recall']:.3f} "
          f"f1={thresholds['target_recall']['f1']:.3f}")

    # Use the target-recall threshold by default: this classifier is meant to
    # be a flag for human review (per PROGRESS.md), so missing a real
    # informational message is worse than an occasional false alarm.
    chosen_threshold = thresholds["target_recall"]["threshold"]
    y_pred_tuned = np.where(informational_scores >= chosen_threshold, 0, 1)
    print(f"\n=== Final report using chosen threshold ({chosen_threshold:.3f}, targets recall>=0.90) ===")
    print(classification_report(y_val, y_pred_tuned, target_names=["informational", "real_error"], digits=3))
    print("Confusion matrix (rows=true, cols=predicted) [informational, real_error]:")
    print(confusion_matrix(y_val, y_pred_tuned))

    model_path = os.path.join(models_dir, "error_classifier.joblib")
    vectorizer_path = os.path.join(models_dir, "error_classifier_vectorizer.joblib")
    threshold_path = os.path.join(models_dir, "error_classifier_threshold.json")

    joblib.dump(best_clf, model_path)
    joblib.dump(vectorizer, vectorizer_path)
    with open(threshold_path, "w", encoding="utf-8") as f:
        json.dump({
            "model_name": best_name,
            "informational_threshold": chosen_threshold,
            "note": "predict as informational (label 0) if P(informational) >= this threshold; else real_error",
        }, f, indent=2)

    print(f"\nSaved model to {model_path}")
    print(f"Saved vectorizer to {vectorizer_path}")
    print(f"Saved tuned threshold to {threshold_path}")

    print("\n=== Sample predictions on val set (tuned threshold) ===")
    for row, pred in list(zip(val_rows, y_pred_tuned))[:8]:
        print(f"  true={row['label']} pred={pred}  code={row['code']:<14} text={row['text'][:70]}")


if __name__ == "__main__":
    main()

