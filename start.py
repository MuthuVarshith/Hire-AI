#!/usr/bin/env python
"""Simple startup script for the Recruiting Platform."""
import os
import sys
import webbrowser
from pathlib import Path

print("=" * 70)
print("AI RECRUITING PLATFORM - STARTUP")
print("=" * 70)

# Check if backend can start
print("\n[1] Starting Flask Backend...")
print("    Listening on http://localhost:5000")
print("    Press Ctrl+C to stop\n")

# Import and run the app
try:
    from app import app

    import scorer

    # Load the embedding model once, up front, so the first screening request
    # doesn't pay the load cost.
    print("[2] Loading embedding model (first run may take a moment)...")
    scorer.load_embedding_model()

    print("\nAPI Health: http://127.0.0.1:5000/api/health")
    print("Dashboard:  http://127.0.0.1:5000\n")
    print("=" * 70)
    print()

    # use_reloader=False: the reloader treats torch's lazy imports inside
    # site-packages as code changes and restarts the process mid-screening.
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)

except Exception as e:
    print(f"Error starting backend: {e}")
    print("\nTroubleshooting:")
    print("1. Make sure all dependencies are installed: pip install -r requirements.txt")
    print("2. Check that port 5000 is not in use")
    print("3. Check .env configuration")
    sys.exit(1)
