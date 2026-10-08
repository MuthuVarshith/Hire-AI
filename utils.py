"""Utility functions for file handling and output formatting."""
import os
import json
import csv
from pathlib import Path
from typing import List
from colorama import init, Fore, Style
from tabulate import tabulate

init(autoreset=True)

def discover_files(directory: str, extensions: tuple = ('.txt', '.pdf', '.docx')) -> List[str]:
    """Find all resume files in a directory, sorted alphabetically."""
    found_files = []
    if os.path.isdir(directory):
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(extensions):
                    found_files.append(os.path.join(root, file))
    return sorted(found_files)

def read_text_file(file_path: str) -> str:
    """Read and return file content."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"{Fore.RED}Error reading {file_path}: {e}")
        return ""

def save_json(data: list, output_path: str):
    """Save results to JSON, creating parent dirs."""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"{Fore.GREEN}Results saved to {output_path}")
    except Exception as e:
        print(f"{Fore.RED}Error saving JSON to {output_path}: {e}")

def save_csv(data: list, output_path: str):
    """Save results to CSV."""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if not data:
            print(f"{Fore.YELLOW}No data to save.")
            return

        fieldnames = ['rank', 'name', 'file', 'composite_score', 'semantic_score',
                      'skill_match_score', 'experience_score', 'education_score',
                      'matched_skills', 'missing_skills', 'reasoning']

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                # Convert lists to strings for CSV
                row_copy = row.copy()
                if isinstance(row_copy.get('matched_skills'), list):
                    row_copy['matched_skills'] = ', '.join(row_copy['matched_skills'])
                if isinstance(row_copy.get('missing_skills'), list):
                    row_copy['missing_skills'] = ', '.join(row_copy['missing_skills'])
                writer.writerow(row_copy)
        print(f"{Fore.GREEN}Results saved to {output_path}")
    except Exception as e:
        print(f"{Fore.RED}Error saving CSV to {output_path}: {e}")

def print_banner():
    """Print a colorful CLI banner."""
    banner = f"""
{Fore.CYAN}==================================================
{Fore.CYAN}          RESUME SCREENING AGENT
{Fore.CYAN}=================================================={Style.RESET_ALL}
"""
    print(banner)

def print_results_table(results: list):
    """Print ranked results as a formatted table using tabulate."""
    if not results:
        print(f"{Fore.YELLOW}No results to display.")
        return

    table_data = []
    for r in results:
        table_data.append([
            r.get('rank', '-'),
            r.get('name', 'Unknown'),
            f"{r.get('composite_score', 0):.1f}",
            f"{len(r.get('matched_skills', []))} skills"
        ])

    headers = ["Rank", "Name", "Score", "Matched"]
    print(f"\n{Fore.CYAN}RANKING RESULTS:{Style.RESET_ALL}")
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

def print_candidate_detail(result: dict):
    """Print detailed info for one candidate."""
    print(f"\n{Fore.CYAN}--- Candidate Detail: {result.get('name', 'Unknown')} ---{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Rank:{Style.RESET_ALL} {result.get('rank', '-')}")
    print(f"{Fore.YELLOW}File:{Style.RESET_ALL} {result.get('file', '-')}")
    print(f"{Fore.YELLOW}Composite Score:{Style.RESET_ALL} {result.get('composite_score', 0):.1f}")

    matched = result.get('matched_skills', [])
    missing = result.get('missing_skills', [])

    print(f"{Fore.GREEN}Matched Skills:{Style.RESET_ALL} {', '.join(matched) if matched else 'None'}")
    print(f"{Fore.RED}Missing Skills:{Style.RESET_ALL} {', '.join(missing) if missing else 'None'}")
    print(f"{Fore.YELLOW}Reasoning:{Style.RESET_ALL}\n{result.get('reasoning', '')}\n")
