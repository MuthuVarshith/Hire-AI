"""LangChain adapter for the candidate-pool retriever.

Kept separate so the core retrieval code has no LangChain dependency; LangChain
chains and agents can use `CandidatePoolRetriever` like any other retriever.
"""
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from retrieval import RetrievalConfig, Retriever


class CandidatePoolRetriever(BaseRetriever):
    """Returns resume chunks as Documents; metadata carries what a citation needs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    retriever: Retriever
    config: RetrievalConfig = RetrievalConfig()
    job_id: int | None = None

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun,
                                **kwargs: Any) -> list[Document]:
        hits = self.retriever.search(query, self.config, job_id=self.job_id)
        return [
            Document(page_content=hit.text, metadata={
                "chunk_id": hit.chunk_id, "candidate_id": hit.candidate_id, "section": hit.section,
                "char_start": hit.char_start, "char_end": hit.char_end,
                "score": hit.score, "method": hit.method,
            })
            for hit in hits
        ]
