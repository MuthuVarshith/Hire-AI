import os
import sys
import argparse

# Ensure imports work from the project directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import config
    import utils
    import jd_parser
    import resume_parser
    import scorer
    import ranker
except ImportError as e:
    print(f"Error importing required modules: {e}")
    sys.exit(1)

def main():
    utils.print_banner()

    parser = argparse.ArgumentParser(description="Resume Screening Agent")
    parser.add_argument("--jd", type=str, help="Path to job description file")
    parser.add_argument("--resumes", type=str, help="Path to directory of resumes")
    parser.add_argument("--output", type=str, default="output", help="Output directory (default: 'output')")
    parser.add_argument("--top", type=int, default=5, help="Show detailed view for top N candidates (default: 5)")
    parser.add_argument("--no-llm", action="store_true", help="Flag to disable LLM even if API key is available")

    args = parser.parse_args()

    # Interactive mode fallback
    jd_path = args.jd
    resumes_dir = args.resumes

    if not jd_path or not resumes_dir:
        print("Running in interactive mode. Please provide the required paths.")
        if not jd_path:
            jd_path = input("Enter path to job description file: ").strip()
        if not resumes_dir:
            resumes_dir = input("Enter path to directory of resumes: ").strip()

    if not jd_path or not resumes_dir:
        print("Error: Both Job Description and Resumes Directory are required.")
        sys.exit(1)

    if args.no_llm:
        # Temporarily disable API key if flag is set
        config.get_api_key = lambda: None

    api_key = config.get_api_key()

    try:
        print(f"\n[1/5] Parsing Job Description from {jd_path}...")
        jd = jd_parser.parse_jd(jd_path)

        print(f"\n[2/5] Discovering resumes in {resumes_dir}...")
        resume_files = utils.discover_files(resumes_dir)
        print(f"      Found {len(resume_files)} resumes.")

        if not resume_files:
            print("No resumes found. Exiting.")
            sys.exit(0)

        print(f"\n[3/5] Loading embedding model ({config.EMBEDDING_MODEL})...")
        model = scorer.load_embedding_model()

        print(f"\n[4/5] Processing and scoring {len(resume_files)} candidates...")
        scores = []
        for i, resume_file in enumerate(resume_files, 1):
            print(f"      Processing [{i}/{len(resume_files)}]: {os.path.basename(resume_file)}")
            resume = resume_parser.parse_resume(resume_file)
            score = scorer.score_candidate(resume, jd, model)
            scores.append(score)

        print("\n[5/5] Ranking candidates...")
        ranked_results = ranker.rank_candidates(scores, api_key=api_key)

        print("\n" + "="*50)
        print("RESULTS SUMMARY")
        print("="*50)
        utils.print_results_table(ranked_results)

        print(f"\nDetailed View (Top {args.top} Candidates):")
        for res in ranked_results[:args.top]:
            utils.print_candidate_detail(res)

        # Save results
        os.makedirs(args.output, exist_ok=True)
        json_path = os.path.join(args.output, "ranked_results.json")
        csv_path = os.path.join(args.output, "ranked_results.csv")
        utils.save_json(ranked_results, json_path)
        utils.save_csv(ranked_results, csv_path)

        print("\nSummary: Processing complete. Results saved to:")
        print(f"  - {json_path}")
        print(f"  - {csv_path}")

    except Exception as e:
        print(f"\nAn error occurred during processing: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
