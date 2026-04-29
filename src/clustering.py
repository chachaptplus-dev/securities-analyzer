"""
TF-IDF + KMeans clustering for investment thesis text.
Swap `cluster_theses` for an LLM-based topic modeller when ready.
"""
from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


def cluster_theses(
    theses: list[str],
    n_clusters: int = 5,
    top_terms: int = 10,
) -> tuple[list[int], list[str], dict[int, list[str]]]:
    """
    Returns
    -------
    labels          : cluster index per thesis (same length as `theses`)
    cluster_names   : human-readable label per cluster (length = n_clusters)
    cluster_terms   : {cluster_id: [top keyword, ...]}
    """
    valid = [t for t in theses if t and t.strip()]
    if len(valid) < 2:
        labels = [0] * len(theses)
        return labels, ["클러스터 1: (데이터 부족)"], {0: []}

    n_clusters = min(n_clusters, len(valid))

    vectorizer = TfidfVectorizer(
        max_features=500,
        min_df=1,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    X = vectorizer.fit_transform(valid)
    X_norm = normalize(X)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    valid_labels = km.fit_predict(X_norm).tolist()

    feature_names = vectorizer.get_feature_names_out()
    cluster_terms: dict[int, list[str]] = {}
    cluster_names: list[str] = []

    for cid in range(n_clusters):
        top_idx = km.cluster_centers_[cid].argsort()[-top_terms:][::-1]
        terms = [feature_names[i] for i in top_idx]
        cluster_terms[cid] = terms
        cluster_names.append(f"클러스터 {cid + 1}: {' · '.join(terms[:3])}")

    # Map back to original theses list (blanks → cluster 0)
    valid_iter = iter(valid_labels)
    labels = [next(valid_iter) if t and t.strip() else 0 for t in theses]

    return labels, cluster_names, cluster_terms
