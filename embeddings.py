"""Pluggable embedding providers for retrieval.

These embed resume and job-description chunks for search. They never affect
candidate scores: the scoring engine always uses its own Sentence-Transformers
model (scorer.py), whichever provider is configured here.

Providers:
- "sentence-transformers" (default): local and offline; shares the scoring
  model instance, so nothing is loaded twice.
- "gemini": Google's embedding API. Synthetic or sample data only (the free
  tier uses submitted content to improve Google's products).

Every vector is L2-normalized, so cosine similarity is a plain dot product and
vectors from different code paths are comparable.
"""
import math
from collections.abc import Sequence
from typing import Any, Literal, Protocol

import config

Kind = Literal["document", "query"]


class EmbeddingUnavailable(RuntimeError):
    """The configured provider can't embed right now (model missing, no API key, API error)."""


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str:
        """Stored with every vector; vectors from different models must never be compared."""
        ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: Sequence[str], kind: Kind = "document") -> list[list[float]]: ...

    def fits(self, text: str) -> bool:
        """Whether `text` is embedded whole, without being truncated by the model."""
        ...


def normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else [0.0 for _ in vector]


class SentenceTransformerProvider:
    def __init__(self, model: Any = None) -> None:
        if model is None:
            import scorer

            model = scorer.load_embedding_model()
        if model is None:
            raise EmbeddingUnavailable("Sentence-Transformers model could not be loaded")
        self._model = model

    @property
    def name(self) -> str:
        return f"sentence-transformers/{config.EMBEDDING_MODEL}"

    @property
    def dimension(self) -> int:
        return int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: Sequence[str], kind: Kind = "document") -> list[list[float]]:
        # all-MiniLM-L6-v2 is symmetric: queries and documents are embedded the same way.
        if not texts:
            return []
        vectors = self._model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return [[float(x) for x in vector] for vector in vectors]

    def fits(self, text: str) -> bool:
        return len(self._model.tokenizer(text)["input_ids"]) <= int(self._model.max_seq_length)


class GeminiEmbeddingProvider:
    """gemini-embedding-001 by default: one vector per input string.

    gemini-embedding-2 merges a list of inputs into a single embedding unless each is wrapped
    separately, so passing it chunks in a batch would silently return one vector for all of them.
    """

    BATCH_SIZE = 100
    MAX_INPUT_CHARS = 2048  # the model accepts 2048 tokens; a token is at least one character

    def __init__(self, api_key: str | None = None, model: str | None = None, dimension: int | None = None,
                 client: Any = None) -> None:
        if client is None:
            key = api_key or config.get_api_key()
            if not key:
                raise EmbeddingUnavailable("GOOGLE_API_KEY is not set")
            import llm

            client = llm._client(key)
        self._client = client
        self._model = model or config.EMBEDDING_API_MODEL
        self._dimension = dimension or config.EMBEDDING_API_DIM

    @property
    def name(self) -> str:
        return f"gemini/{self._model}@{self._dimension}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: Sequence[str], kind: Kind = "document") -> list[list[float]]:
        from google.genai import types

        settings = types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT",
            output_dimensionality=self._dimension,
            auto_truncate=False,  # fail loudly rather than embed a cut-off chunk
        )
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = list(texts[i:i + self.BATCH_SIZE])
            try:
                response = self._client.models.embed_content(model=self._model, contents=batch, config=settings)
            except Exception as exc:
                raise EmbeddingUnavailable(f"Gemini embedding request failed: {type(exc).__name__}") from exc
            embeddings = response.embeddings or []
            if len(embeddings) != len(batch):
                raise EmbeddingUnavailable(f"expected {len(batch)} embeddings, got {len(embeddings)}")
            for embedding in embeddings:
                values = list(embedding.values or [])
                if len(values) != self._dimension:
                    raise EmbeddingUnavailable(f"expected {self._dimension} dimensions, got {len(values)}")
                # gemini-embedding-001 output is only normalized at its full 3072 dimensions.
                vectors.append(normalize(values))
        return vectors

    def fits(self, text: str) -> bool:
        return len(text) <= self.MAX_INPUT_CHARS


def get_provider(name: str | None = None) -> EmbeddingProvider:
    """The provider named by `name` or the EMBEDDING_PROVIDER setting."""
    choice = (name or config.EMBEDDING_PROVIDER).strip().lower()
    if choice == "sentence-transformers":
        return SentenceTransformerProvider()
    if choice == "gemini":
        return GeminiEmbeddingProvider()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER {choice!r}; use 'sentence-transformers' or 'gemini'")
