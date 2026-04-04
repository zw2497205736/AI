import re

from rank_bm25 import BM25Okapi


def tokenize_chinese(text: str) -> list[str]:
    normalized = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text.lower())
    tokens: list[str] = []
    for word in normalized.split():
        if re.search(r"[\u4e00-\u9fff]", word):
            tokens.extend(list(word))
        else:
            tokens.append(word)
    return [token for token in tokens if token.strip()]


class BM25Retriever:
    def __init__(self, corpus: list[str]):
        self.corpus = corpus
        tokenized = [tokenize_chinese(doc) for doc in corpus]
        self.bm25 = BM25Okapi(tokenized)

    def retrieve(self, query: str, top_k: int) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize_chinese(query))
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        return [(self.corpus[idx], score) for idx, score in ranked[:top_k] if score > 0]

