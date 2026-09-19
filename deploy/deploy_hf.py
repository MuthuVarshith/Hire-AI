"""Deploy HireAI to a Hugging Face Docker Space.

Uploads through the Hub API instead of `git push`: a Space's git remote
rejects binary files that aren't stored with Xet/LFS, and this repo's history
contains screenshots.

Usage (after `hf auth login`):
    python deploy/deploy_hf.py                      # <your-username>/hire-ai
    python deploy/deploy_hf.py --space user/name
    python deploy/deploy_hf.py --private
"""
import argparse
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent

# Not needed to run the app; binaries and local data must not be uploaded.
IGNORE = [
    ".git/*", ".github/*", "docs/*", "tests/*", "output/*", "uploads/*", "data/*",
    "*.db", ".env", "__pycache__/*", "*/__pycache__/*", ".pytest_cache/*",
    "README.md", "deploy/*",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--space", help="Space id, e.g. username/hire-ai")
    parser.add_argument("--private", action="store_true", help="Create the Space as private")
    args = parser.parse_args()

    api = HfApi()
    space_id = args.space or f"{api.whoami()['name']}/hire-ai"

    api.create_repo(space_id, repo_type="space", space_sdk="docker",
                    private=args.private, exist_ok=True)
    api.upload_folder(repo_id=space_id, repo_type="space", folder_path=ROOT,
                      ignore_patterns=IGNORE, commit_message="Deploy HireAI")
    api.upload_file(repo_id=space_id, repo_type="space",
                    path_or_fileobj=ROOT / "deploy" / "hf_space_readme.md",
                    path_in_repo="README.md", commit_message="Space README")

    print(f"Deployed: https://huggingface.co/spaces/{space_id}")
    print("The first build takes several minutes; watch the Logs tab on that page.")


if __name__ == "__main__":
    main()
