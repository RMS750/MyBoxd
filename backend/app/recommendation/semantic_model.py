import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.recommendation.features import movie_text

_SENTENCE_MODEL=None
_SENTENCE_MODEL_ATTEMPTED=False

class SemanticSimilarity:
    def __init__(self):
        global _SENTENCE_MODEL,_SENTENCE_MODEL_ATTEMPTED
        self.backend='tfidf';self._model=None
        if not _SENTENCE_MODEL_ATTEMPTED:
            _SENTENCE_MODEL_ATTEMPTED=True
            try:
                from sentence_transformers import SentenceTransformer
                _SENTENCE_MODEL=SentenceTransformer('all-MiniLM-L6-v2')
            except Exception:
                _SENTENCE_MODEL=None
        if _SENTENCE_MODEL is not None:
            self._model=_SENTENCE_MODEL;self.backend='sentence-transformers/all-MiniLM-L6-v2'
    def similarities(self,refs,cands):
        if not cands:return []
        if not refs:return [.5]*len(cands)
        rt=[movie_text(m) for m in refs];ct=[movie_text(m) for m in cands]
        if self._model is not None:
            e=np.asarray(self._model.encode(rt+ct,normalize_embeddings=True)); sims=e[len(rt):]@e[:len(rt)].T;return [float(max(0,min(1,row.max()))) for row in sims]
        docs=rt+ct
        if not any(x.strip() for x in docs):return [.5]*len(cands)
        try:
            v=TfidfVectorizer(stop_words='english',max_features=6000,ngram_range=(1,2));mat=v.fit_transform(docs);s=cosine_similarity(mat[len(rt):],mat[:len(rt)]);return [float(max(0,min(1,row.max()))) for row in s]
        except ValueError:
            return [.5]*len(cands)
