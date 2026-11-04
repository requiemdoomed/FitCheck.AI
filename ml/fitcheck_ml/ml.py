"""
The machine-learning layer. Kept apart from the rules on purpose.

Two exported models (trained in notebooks/FitCheck_AI_ML_Analysis.ipynb):
  - Decision Tree   -> P(person likes this outfit | context, outfit features)
  - KNN classifier  -> the same question answered by looking at the most
                       similar outfits in the training data

Plus one model that's fitted live, per person:
  - a nearest-neighbour lookup over the outfits *this* person has rated,
    which says whether a new outfit resembles their likes or their dislikes.

If any file is missing or doesn't match the current feature list, the bundle
reports itself unavailable and the recommender scores on rules alone.
"""

import json
import logging
from pathlib import Path

import joblib
import numpy as np

from . import features

log = logging.getLogger(__name__)

MODEL_FILES = {
    "decision_tree": "decision_tree_model.joblib",
    "knn": "knn_model.joblib",
    "scaler": "scaler.joblib",
    "encoders": "encoders.joblib",
}
METADATA_FILE = "model_metadata.json"

MIN_FEEDBACK_FOR_PERSONAL = 3


class ModelBundle:
    def __init__(self, model_dir):
        self.model_dir = Path(model_dir)
        self.available = False
        self.reason = "not loaded"
        self.metadata = {}
        self.dt = self.knn = self.scaler = self.encoders = None
        self.blend = {"decision_tree": 0.5, "knn": 0.5}

    def load(self):
        try:
            meta_path = self.model_dir / METADATA_FILE
            if not meta_path.exists():
                raise FileNotFoundError(f"{METADATA_FILE} not found in {self.model_dir}")
            self.metadata = json.loads(meta_path.read_text(encoding="utf-8"))

            expected = features.feature_names()
            if self.metadata.get("feature_names") != expected:
                raise ValueError("model was trained on a different feature list; re-run the notebook")

            loaded = {}
            for key, filename in MODEL_FILES.items():
                path = self.model_dir / filename
                if not path.exists():
                    raise FileNotFoundError(f"{filename} not found")
                loaded[key] = joblib.load(path)

            self.dt = loaded["decision_tree"]
            self.knn = loaded["knn"]
            self.scaler = loaded["scaler"]
            self.encoders = loaded["encoders"]
            self.blend = self.metadata.get("blend", self.blend)

            # one throwaway prediction proves the pieces fit together
            probe = features.to_matrix([_probe_row()], self.encoders)
            self.dt.predict_proba(probe)
            self.knn.predict_proba(self.scaler.transform(probe))

            self.available = True
            self.reason = "ok"
            log.info("ML models loaded (version %s)", self.metadata.get("model_version"))
        except Exception as err:  # any failure means "run without ML", never crash
            self.available = False
            self.reason = str(err)
            log.warning("ML models unavailable, using rules only: %s", err)
        return self

    # -- global taste models -------------------------------------------------

    def matrix(self, rows):
        return features.to_matrix(rows, self.encoders)

    def predict(self, rows):
        """Returns (blended, dt, knn) probability arrays, or None if unavailable."""
        if not self.available or not rows:
            return None
        X = self.matrix(rows)
        dt = self.dt.predict_proba(X)[:, _like_column(self.dt)]
        knn = self.knn.predict_proba(self.scaler.transform(X))[:, _like_column(self.knn)]
        w_dt, w_knn = self.blend.get("decision_tree", 0.5), self.blend.get("knn", 0.5)
        blended = (w_dt * dt + w_knn * knn) / (w_dt + w_knn)
        return blended, dt, knn

    def status(self):
        return {
            "available": self.available,
            "reason": self.reason,
            "version": self.metadata.get("model_version"),
            "trained_at": self.metadata.get("trained_at"),
        }


def _like_column(model):
    classes = list(model.classes_)
    return classes.index(1) if 1 in classes else len(classes) - 1


def _probe_row():
    row = {name: 0.0 for name in features.NUMERIC_FEATURES}
    row.update({"occasion": "casual", "weather": "sunny", "style_pref": "none", "palette": "any"})
    return row


# ---------------------------------------------------------------------------
# per-person feedback model
# ---------------------------------------------------------------------------

def personal_similarity(candidate_rows, history, bundle):
    """
    How much each candidate resembles outfits this person liked vs disliked.

    history: list of (raw_feature_dict, verdict) with verdict 'like'/'dislike'.
    Returns an array in 0..1 (0.5 = no signal), or None when there's too
    little feedback to say anything.
    """
    if len(history) < MIN_FEEDBACK_FOR_PERSONAL or not candidate_rows:
        return None
    from sklearn.neighbors import NearestNeighbors

    hist_rows = [h[0] for h in history]
    labels = np.array([1.0 if h[1] == "like" else -1.0 for h in history])

    if bundle is not None and bundle.available:
        H = bundle.scaler.transform(bundle.matrix(hist_rows))
        C = bundle.scaler.transform(bundle.matrix(candidate_rows))
    else:
        # no exported scaler: standardise numeric features on the history itself
        cols = features.NUMERIC_FEATURES
        Hn = np.array([[float(r[c]) for c in cols] for r in hist_rows])
        Cn = np.array([[float(r[c]) for c in cols] for r in candidate_rows])
        mu, sd = Hn.mean(axis=0), Hn.std(axis=0)
        sd[sd == 0] = 1.0
        H, C = (Hn - mu) / sd, (Cn - mu) / sd

    k = min(5, len(history))
    nn = NearestNeighbors(n_neighbors=k).fit(H)
    dist, idx = nn.kneighbors(C)
    weights = 1.0 / (dist + 0.5)
    signal = (weights * labels[idx]).sum(axis=1) / weights.sum(axis=1)   # -1..1
    return 0.5 + 0.5 * signal


_bundle = None


def get_bundle(model_dir):
    global _bundle
    if _bundle is None or Path(model_dir) != _bundle.model_dir:
        _bundle = ModelBundle(model_dir).load()
    return _bundle


def reset_bundle():
    global _bundle
    _bundle = None
