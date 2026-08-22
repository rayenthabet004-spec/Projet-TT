"""
features.py

Shared feature-extraction code for the classifier. CombinedVectorizer lives
here (not inline in train_classifier.py) specifically so it has a stable,
consistently-importable module path (src.classifier.features.CombinedVectorizer)
regardless of whether train_classifier.py or classify.py is the script being
run directly. When a class is defined inside a script that gets executed as
__main__ (e.g. `python -m src.classifier.train_classifier`), pickle records
its module as "__main__" rather than its real dotted path -- so loading the
pickled vectorizer from a DIFFERENT entry point (classify.py) fails with
`AttributeError: Can't get attribute 'CombinedVectorizer'` because pickle
looks for it in whatever module happens to be __main__ at load time instead.
Keeping the class in its own always-imported-by-name module avoids this
entirely.
"""

from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer


class CombinedVectorizer:
    """Word n-grams (1-2) catch whole-phrase signal ("informational
    message"); character n-grams (3-5, word-boundary-aware) catch
    morphological/structural patterns word-level features miss on short
    technical text. Concatenated via hstack into one feature matrix."""

    def __init__(self):
        self.word_vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=40_000, lowercase=True)
        self.char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=40_000, lowercase=True)

    def fit_transform(self, texts):
        w = self.word_vec.fit_transform(texts)
        c = self.char_vec.fit_transform(texts)
        return hstack([w, c]).tocsr()

    def transform(self, texts):
        w = self.word_vec.transform(texts)
        c = self.char_vec.transform(texts)
        return hstack([w, c]).tocsr()
