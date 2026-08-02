"""
Topic classifier: TF-IDF + Decision Tree.

Trained on the knowledge_base questions at startup (tiny synthetic dataset).
In production this would be a proper ML model trained on historical tickets.
Confidence = max class probability from predict_proba().
"""
from pathlib import Path
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.tree import DecisionTreeClassifier
from sklearn.pipeline import Pipeline

TOPICS = [
    "account_access",
    "billing",
    "technical_issue",
    "general_question",
    "complaint",
    "abuse",
]

# Risky topics — always escalate regardless of confidence
RISKY_TOPICS = {"complaint", "abuse", "billing"}

KB_PATH = Path(__file__).parent / "data" / "knowledge_base.json"


def _load_training_data():
    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)
    texts, labels = [], []
    for item in kb:
        texts.append(item["question"])
        labels.append(item["topic"])
    # Add a few extra examples for complaint/abuse (not in KB)
    extras = [
        ("буду жаловаться роспотребнадзор подам в суд", "complaint"),
        ("требую компенсацию ужасный сервис", "complaint"),
        ("это уже третье обращение никто не отвечает", "complaint"),
        ("оскорбительное поведение оператора", "abuse"),
        ("хамство грубость сотрудника поддержки", "abuse"),
    ]
    for text, label in extras:
        texts.append(text)
        labels.append(label)
    return texts, labels


def build_classifier() -> Pipeline:
    texts, labels = _load_training_data()
    clf = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            max_features=2000,
            sublinear_tf=True,
        )),
        ("dt", DecisionTreeClassifier(
            max_depth=10,
            min_samples_leaf=1,
            random_state=42,
        )),
    ])
    clf.fit(texts, labels)
    return clf


# Module-level singleton — loaded once at import time
_clf = build_classifier()


def predict(text: str) -> dict:
    """
    Returns:
        topic      : predicted topic string
        confidence : max class probability (0..1)
        all_probs  : dict topic -> probability
    """
    proba = _clf.predict_proba([text])[0]
    classes = _clf.classes_
    idx = proba.argmax()
    topic = classes[idx]
    confidence = float(proba[idx])
    return {
        "topic": topic,
        "confidence": confidence,
        "all_probs": {c: round(float(p), 3) for c, p in zip(classes, proba)},
        "is_risky_topic": topic in RISKY_TOPICS,
    }
