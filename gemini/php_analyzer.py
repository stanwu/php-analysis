

import os
import sys
import json
import re
from collections import defaultdict

def find_php_files(directory):
    """Recursively finds all .php files in a directory."""
    php_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.php'):
                php_files.append(os.path.join(root, file))
    return php_files

def analyze_php_file(file_path):
    """
    Analyzes a single PHP file to find if/else blocks, nesting depth,
    and condition expressions using regex and string parsing.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        # Return None if file can't be read
        return None

    branches = []
    max_depth = 0
    
    # This regex finds 'if', 'elseif', or 'else' keywords that are not preceded by a '$',
    # to avoid matching variable names like $if_condition.
    control_flow_pattern = r'(?<!$)\b(if|elseif|else)\b'

    for match in re.finditer(control_flow_pattern, content):
        keyword = match.group(1)
        start_pos = match.start()

        # Calculate nesting depth by counting open/closed braces before the statement.
        # This gives the depth level at which the control statement is defined.
        preceding_code = content[:start_pos]
        depth = preceding_code.count('{') - preceding_code.count('}')

        # The block introduced by this statement will be at `depth + 1`.
        # We track the maximum depth reached by any block.
        block_depth = depth + 1
        if block_depth > max_depth:
            max_depth = block_depth

        line_num = preceding_code.count('\n') + 1

        condition = None
        if keyword in ['if', 'elseif']:
            # To extract the condition, we find the opening parenthesis and then
            # scan forward, balancing parentheses to find the matching closing one.
            try:
                search_start = match.end()
                open_paren_pos = content.index('(', search_start)
                
                balance = 1
                scan_pos = open_paren_pos + 1
                
                while scan_pos < len(content) and balance > 0:
                    char = content[scan_pos]
                    if char == '(':
                        balance += 1
                    elif char == ')':
                        balance -= 1
                    scan_pos += 1
                
                if balance == 0:
                    condition = content[open_paren_pos + 1 : scan_pos - 1].strip()
                else:
                    condition = "[Parsing Error: Unbalanced parentheses]"
            except ValueError:
                condition = "[Parsing Error: Could not find condition's opening parenthesis]"
            except Exception:
                condition = "[Parsing Error: Unknown issue extracting condition]"

        branches.append({
            "type": keyword,
            "line": line_num,
            "depth": depth,
            "condition": condition,
        })

    return {
        "max_depth": max_depth,
        "total_branches": len(branches),
        "branches": branches,
    }

def main():
    """
    Main function to drive the PHP analysis.
    """
    if len(sys.argv) != 2:
        print("Usage: python php_analyzer.py /path/to/directory")
        sys.exit(1)
    
    target_dir = sys.argv[1]
    if not os.path.isdir(target_dir):
        print(f"Error: Directory not found at '{target_dir}'")
        sys.exit(1)

    php_files = find_php_files(target_dir)
    if not php_files:
        print(f"No .php files found in '{target_dir}'.")
        sys.exit(0)

    all_files_data = {}
    file_summaries = []
    total_branches_overall = 0

    for file_path in php_files:
        analysis_result = analyze_php_file(file_path)
        if analysis_result and analysis_result['total_branches'] > 0:
            # Use relative paths for cleaner reporting
            relative_path = os.path.relpath(file_path, os.path.dirname(target_dir))
            all_files_data[relative_path] = analysis_result
            total_branches_overall += analysis_result['total_branches']
            file_summaries.append({
                "file": relative_path,
                "max_depth": analysis_result['max_depth'],
                "total_branches": analysis_result['total_branches']
            })

    # Sort files by max nesting depth to find the most complex
    most_complex_files = sorted(file_summaries, key=lambda x: x['max_depth'], reverse=True)[:10]

    report = {
        "summary": {
            "total_files_scanned": len(php_files),
            "total_files_with_branches": len(file_summaries),
            "total_branches": total_branches_overall,
            "most_complex_files": most_complex_files
        },
        "files": all_files_data
    }

    # Write the detailed JSON report
    report_path = 'analysis_report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    # --- Print Terminal Summary ---
    print("--- PHP Code Analysis Summary ---")
    print(f"Total files scanned: {len(php_files)}")
    print(f"Total branches found (if/elseif/else): {total_branches_overall}")
    
    print("\nTop 10 Most Complex Files (by max nesting depth):")
    if not most_complex_files:
        print("  No complex files found.")
    else:
        for item in most_complex_files:
            print(f"  - {item['file']} (Max Depth: {item['max_depth']}, Branches: {item['total_branches']})")
    
    print("\nBranch Count Per File (files with branches, sorted by count):")
    files_by_branch_count = sorted(file_summaries, key=lambda x: x['total_branches'], reverse=True)
    if not files_by_branch_count:
        print("  No files with branches found.")
    else:
        for item in files_by_branch_count:
            print(f"  - {item['file']}: {item['total_branches']} branches")

    print(f"\nFull report written to {os.path.abspath(report_path)}")

if __name__ == "__main__":
    main()
