"""Embedding providers: the local Sentence-Transformers model and the Gemini API (mocked)."""
import math
from types import SimpleNamespace

import pytest

import config
import embeddings
from embeddings import EmbeddingUnavailable, GeminiEmbeddingProvider, SentenceTransformerProvider


def _norm(vector):
    return math.sqrt(sum(v * v for v in vector))


def _cosine(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_normalize():
    assert embeddings.normalize([3.0, 4.0]) == [0.6, 0.8]
    assert embeddings.normalize([0.0, 0.0]) == [0.0, 0.0]


# --- Sentence-Transformers (real model) ----------------------------------------

@pytest.fixture(scope="module")
def local_provider():
    try:
        return SentenceTransformerProvider()
    except EmbeddingUnavailable:
        pytest.skip("embedding model unavailable")


@pytest.mark.slow
def test_local_provider_vectors(local_provider):
    import scorer

    assert local_provider._model is scorer.load_embedding_model()  # shares the scoring model, no second copy
    assert local_provider.name == "sentence-transformers/all-MiniLM-L6-v2"
    assert local_provider.dimension == 384

    texts = ["Skills: Python, FastAPI, Docker", "Experience: Built REST APIs in FastAPI",
             "Education: Culinary arts diploma, pastry specialization"]
    vectors = local_provider.embed(texts)
    assert [len(v) for v in vectors] == [384, 384, 384]
    assert all(abs(_norm(v) - 1.0) < 1e-5 for v in vectors)
    assert local_provider.embed(texts) == vectors  # deterministic
    assert local_provider.embed([]) == []

    query = local_provider.embed(["Who has FastAPI experience?"], kind="query")[0]
    assert _cosine(query, vectors[1]) > _cosine(query, vectors[2])


@pytest.mark.slow
def test_local_provider_fits_uses_the_tokenizer(local_provider):
    assert local_provider.fits("Skills: Python, SQL")
    assert not local_provider.fits("Kubernetes, Terraform, gRPC, PostgreSQL. " * 60)


def test_local_provider_unavailable(monkeypatch):
    import scorer

    monkeypatch.setattr(scorer, "load_embedding_model", lambda: None)
    with pytest.raises(EmbeddingUnavailable):
        SentenceTransformerProvider()


# --- Gemini (mocked client; never reaches the network) ------------------------

class _FakeModels:
    def __init__(self, dimension, fail=False):
        self.dimension, self.fail, self.calls = dimension, fail, []

    def embed_content(self, *, model, contents, config):
        self.calls.append((model, list(contents), config))
        if self.fail:
            raise ConnectionError("network down: https://internal.example/path?key=SECRET")
        # Deliberately not unit-length, like gemini-embedding-001 below 3072 dimensions.
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[float(len(t))] + [1.0] * (self.dimension - 1))
                                           for t in contents])


def _gemini(dimension=768, fail=False):
    models = _FakeModels(dimension, fail)
    return GeminiEmbeddingProvider(client=SimpleNamespace(models=models), model="gemini-embedding-001",
                                   dimension=768), models


def test_gemini_provider_requests_and_normalizes():
    provider, models = _gemini()
    vectors = provider.embed(["a", "bb", "ccc"])
    assert provider.name == "gemini/gemini-embedding-001@768" and provider.dimension == 768
    assert len(vectors) == 3 and all(len(v) == 768 for v in vectors)
    assert all(abs(_norm(v) - 1.0) < 1e-9 for v in vectors)

    model, contents, settings = models.calls[0]
    assert (model, contents) == ("gemini-embedding-001", ["a", "bb", "ccc"])
    assert (settings.task_type, settings.output_dimensionality, settings.auto_truncate) == \
        ("RETRIEVAL_DOCUMENT", 768, False)

    provider.embed(["who knows Rust?"], kind="query")
    assert models.calls[-1][2].task_type == "RETRIEVAL_QUERY"


def test_gemini_provider_batches_requests():
    provider, models = _gemini()
    vectors = provider.embed([f"chunk {i}" for i in range(250)])
    assert len(vectors) == 250
    assert [len(call[1]) for call in models.calls] == [100, 100, 50]


def test_gemini_provider_rejects_wrong_dimension():
    provider, _ = _gemini(dimension=3072)
    with pytest.raises(EmbeddingUnavailable, match="expected 768 dimensions"):
        provider.embed(["text"])


def test_gemini_provider_errors_do_not_leak_details():
    provider, _ = _gemini(fail=True)
    with pytest.raises(EmbeddingUnavailable) as error:
        provider.embed(["text"])
    assert "SECRET" not in str(error.value) and "ConnectionError" in str(error.value)


def test_gemini_provider_needs_a_key():
    # conftest makes get_api_key return None for every test.
    with pytest.raises(EmbeddingUnavailable, match="GOOGLE_API_KEY"):
        GeminiEmbeddingProvider()


def test_gemini_fits_is_bounded():
    provider, _ = _gemini()
    assert provider.fits("x" * 2048) and not provider.fits("x" * 2049)


# --- Selection --------------------------------------------------------------------

def test_get_provider_selection(monkeypatch):
    monkeypatch.setattr(embeddings, "SentenceTransformerProvider", lambda: "local")
    monkeypatch.setattr(embeddings, "GeminiEmbeddingProvider", lambda: "gemini")
    assert embeddings.get_provider() == "local"  # default
    assert embeddings.get_provider("Gemini ") == "gemini"
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "gemini")
    assert embeddings.get_provider() == "gemini"
    with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
        embeddings.get_provider("pinecone")
