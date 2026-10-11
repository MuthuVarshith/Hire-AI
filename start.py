#!/usr/bin/env python
"""Start the Recruiting Platform: `uvicorn app.main:app` on HOST:PORT (default 127.0.0.1:8000)."""
import os
import sys

import uvicorn


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print("=" * 70)
    print("AI RECRUITING PLATFORM - STARTUP")
    print("=" * 70)
    try:
        import scorer

        # Load the embedding model once, up front, so the first screening request doesn't pay for it.
        print("Loading embedding model (first run may take a moment)...")
        scorer.load_embedding_model()
        print(f"\nAPI Health: http://{host}:{port}/api/health")
        print(f"Dashboard:  http://{host}:{port}\n")
        uvicorn.run("app.main:app", host=host, port=port)
    except Exception as e:
        print(f"Error starting backend: {e}")
        print("1. Install dependencies: pip install -r requirements.txt")
        print(f"2. Check that port {port} is free")
        print("3. Check .env configuration")
        sys.exit(1)


if __name__ == "__main__":
    main()
