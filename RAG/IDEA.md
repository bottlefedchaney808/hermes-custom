Hermes is a local-first RAG that indexes personal notes, PDFs, memories, sessions, trade journals and Git repos, then answers questions with cited snippets via hybrid retrieval.

- Ingest Markdown, PDF, and repo files with metadata-aware chunking into a vector store plus BM25.
- Retrieve with hybrid search and a reranker, then stream a local LLM answer with inline citations.
- Ship a TUI chat, incremental reindex, and offline persistence with no cloud calls.
- Include a tiny eval harness that scores retrieval on a personal corpus.
