import os
from typing import Dict, List
import re
from pathlib import Path
from github import Github
from github.Repository import Repository
from github.ContentFile import ContentFile

# Note: save OPENAI_API_KEY and GITHUB_API_KEY in .env file without exposing to code

class CodebaseAnalyzer:

    @staticmethod
    def derive_repo_info(model_info: Dict) -> Dict:
        """
        Derives repository information from model info object containing patch details.
        
        Args:
            model_info: Dictionary containing model information and patch
                Example:
                {
                    "model_name_or_path": "epam-ai-run",
                    "model_patch": "diff --git a/astropy/utils/misc.py ..."
                }
        
        Returns:
            Dictionary containing:
            - repo_owner: Repository owner/organization
            - repo_name: Repository name
            - file_path: Path to the modified file
        """
        if not model_info.get("model_patch"):
            raise ValueError("model_patch is required in model_info")
            
        # Extract the first file path from the patch
        patch = model_info["model_patch"]
        file_match = re.search(r'diff --git a/([^\s]+)', patch)
        
        if not file_match:
            raise ValueError("Could not extract file path from patch")
            
        file_path = file_match.group(1)
        
        # Split the path to get repository structure
        path_parts = file_path.split('/')
        
        # The first part is typically the repository name
        # For most cases, owner and repo name are the same
        repo_name = path_parts[0]

            
            
        return {
            "repo_owner": repo_name,  # In most cases, owner and repo name are the same
            "repo_name": repo_name,
            "file_path": file_path
        }

    def function_class_localization(
        repo_owner: str,
        repo_name: str,
        top_files: List[str],
        issue_desc: str,
        test_patch: str,
        base_commit_sha: str,
        github_token: str = None,
        n: int = 3
    ) -> str:
        """
        Implements UTBoost's function/class-level localization using GitHub API
        
        Args:
            repo_owner: GitHub repository owner/organization
            repo_name: GitHub repository name
            top_files: List of file paths from file-level localization
            issue_desc: SWE-Bench issue description
            test_patch: Original test patch content
            github_token: GitHub personal access token (optional, but recommended for rate limits)
            n: Number of top functions/classes to identify
        
        Returns:
            LLM prompt with compressed code context
        """
        
        # Initialize GitHub client
        g = Github(github_token) if github_token else Github()
        
        try:
            # Get repository
            repo = g.get_repo(f"{repo_owner}/{repo_name}")
            
            # 1. Code Compression
            compressed_files = {}
            for file_path in top_files:
                try:
                    # Get file content from GitHub
                    #content = repo.get_contents(file_path)
                    content = repo.get_contents(file_path, ref=base_commit_sha)

                    if content.type != "file":
                        continue
                        
                    # Decode content if it's base64 encoded (GitHub API returns base64)
                    file_content = content.decoded_content.decode('utf-8')
                    
                    compressed = []
                    in_class = False
                    in_function = False
                    
                    # Process each line
                    for line in file_content.split('\n'):
                        # Capture class/function headers
                        class_match = re.match(r'^(class\s+\w+.*?:)', line)
                        func_match = re.match(r'^(def\s+\w+.*?:)', line)
                        decorator_match = re.match(r'^@\w+', line)
                        
                        if decorator_match:
                            compressed.append(line.strip())
                        elif class_match:
                            compressed.append(class_match.group(1))
                            in_class = True
                        elif func_match:
                            compressed.append(func_match.group(1))
                            in_function = True
                        elif in_class and line.strip() == '':
                            in_class = False
                        elif in_function and line.strip() == '':
                            in_function = False

                    compressed_files[file_path] = '\n'.join(compressed)
                    
                except Exception as e:
                    print(f"Error processing file {file_path}: {str(e)}")
                    continue

            # 2. Prompt Construction
            prompt = f"""Analyze these code structures to identify the top {n} functions/classes
    needing augmented test cases for issue resolution.

    Repository Files:
    """
            for file_path, content in compressed_files.items():
                prompt += f"\n=== {file_path} ===\n{content}\n"

            prompt += f"""
    Issue Description:
    {issue_desc}

    Original Test Patch:
    {test_patch}

    Output Requirements:
    1. List {n} fully qualified function/class names
    2. Order by relevance to the issue
    3. Format as bullet points with explanations
    4. Include parent classes/modules where applicable

    Example Response:
    - sklearn.svm.tests.test_svm.test_sparse_fit_sv_empty (Core SVM test function missing edge cases)
    - sklearn.svm.base._sparse_fit (Implementation function called by test)
    """
            
            print("\nGenerated Prompt:")
            print(prompt)
            return prompt
            
        except Exception as e:
            raise Exception(f"Error accessing GitHub repository: {str(e)}")

    def line_level_localization(
        repo_owner: str,
        repo_name: str,
        target_functions: List[str],
        issue_desc: str,
        test_patch: str,
        base_commit_sha: str,
        github_token: str = None, 
        context_window: int = 10
    ) -> str:
        """
        Identifies specific code lines for test insertion using UTBoost's line-level localization
        with GitHub API.
        
        Args:
            repo_owner: GitHub repository owner/organization
            repo_name: GitHub repository name
            target_functions: List of function/class names from previous step
            issue_desc: SWE-Bench issue description
            test_patch: Original test patch content
            github_token: GitHub personal access token (optional, but recommended for rate limits)
            context_window: Number of surrounding lines to include
        
        Returns:
            LLM prompt with line-numbered code context
        """
        
        # Initialize GitHub client
        g = Github(github_token) if github_token else Github()
        
        try:
            # Get repository
            repo = g.get_repo(f"{repo_owner}/{repo_name}")
            
            # Helper function to parse function specification
            def parse_function_spec(func_spec: str) -> tuple[str, str]:
                """Extracts file path and function name from function specification"""
                parts = func_spec.split('.')
                if len(parts) < 2:
                    raise ValueError(f"Invalid function specification: {func_spec}")
                file_path = '/'.join(parts[:-1]) + '.py'
                func_name = parts[-1]
                return file_path, func_name

            # 1. Code Extraction with Line Numbers
            def get_code_with_lines(file_path: str) -> str:
                """Gets file content with line numbers from GitHub"""
                try:
                    #content = repo.get_contents(file_path)
                    content = repo.get_contents(file_path, ref=base_commit_sha)
                    if content.type != "file":
                        return ""
                    file_content = content.decoded_content.decode('utf-8')
                    return "".join([f"{i+1}: {line}" for i, line in enumerate(file_content.split('\n'))])
                except Exception as e:
                    print(f"Error accessing file {file_path}: {str(e)}")
                    return ""

            # 2. Build Code Context Dictionary
            code_context = {}
            for func_spec in target_functions:
                try:
                    file_path, func_name = parse_function_spec(func_spec)
                    code = get_code_with_lines(file_path)
                    if code:
                        code_context[func_spec] = code
                except Exception as e:
                    print(f"Error processing function {func_spec}: {str(e)}")
                    continue

            # 3. Prompt Construction
            prompt = f"""Analyze these code segments to identify exact line ranges for test insertion:

    Issue Description:
    {issue_desc}

    Original Test Patch:
    {test_patch}

    Code Contexts:
    """
            for func_spec, code in code_context.items():
                prompt += f"\n=== {func_spec} ===\n{code}\n"

            prompt += f"""
    Output Requirements:
    1. Specify line ranges as [start_line-end_line]
    2. Prioritize areas with:
    - Conditional logic
    - Error handling
    - Data validation
    3. Include {context_window} lines of surrounding context
    4. Format response as:
    <function_spec>: <line_range>

    Example Response:
    sklearn.svm.tests.test_svm.test_sparse_fit_sv_empty: 693-740
    """
            
            print("\nGenerated Prompt:")
            print(prompt)
            return prompt
            
        except Exception as e:
            raise Exception(f"Error accessing GitHub repository: {str(e)}")

    def file_level_localization(
        repo_owner: str,
        repo_name: str,
        issue_description: str,
        test_patch: str,
        github_token: str = None,
        n: int = 3
    ) -> str:
        """
        Implements UTBoost's file-level localization to identify Top-N files
        for test case additions using GitHub API.
        
        Args:
            repo_owner: GitHub repository owner/organization
            repo_name: GitHub repository name
            issue_description: SWE-Bench issue description
            test_patch: Original test patch content
            github_token: GitHub personal access token (optional, but recommended for rate limits)
            n: Number of top files to identify
        
        Returns:
            LLM prompt with structured codebase and localization instructions
        """
        
        # Initialize GitHub client
        g = Github(github_token) if github_token else Github()
        
        try:
            # Get repository
            repo = g.get_repo(f"{repo_owner}/{repo_name}")
            
            # 1. Codebase Tree Construction
            def build_tree(repo: Repository, path: str = "", indent: int = 0) -> str:
                """Builds vertical-aligned tree representation using GitHub API"""
                tree_str = ""
                try:
                    #contents = repo.get_contents(path)
                    contents = repo.get_contents(path, ref=base_commit_sha)
                    for content in sorted(contents, key=lambda x: x.name):
                        if content.type == "dir":
                            tree_str += "│   " * indent + f"├── {content.name}/\n"
                            tree_str += build_tree(repo, content.path, indent + 1)
                        else:
                            tree_str += "│   " * indent + f"├── {content.name}\n"
                except Exception as e:
                    print(f"Error accessing path {path}: {str(e)}")
                return tree_str

            codebase_tree = build_tree(repo)

            # 2. LLM Prompt Construction
            prompt = f"""Analyze this software repository and identify the {n} files most likely 
    to require test case additions based on the issue description and existing test patch.

    Repository Structure:
    {codebase_tree}

    Issue Description:
    {issue_description}

    Existing Test Patch:
    {test_patch}

    Output Requirements:
    1. List {n} full file paths from the repository structure
    2. Order by relevance to the issue
    3. Format as bullet points with explanations
    4. Focus on test files and code under test

    Example Response:
    - sklearn/svm/tests/test_svm.py (Contains SVM test cases similar to the patch)
    - sklearn/svm/base.py (Implements core SVM functionality referenced in issue)
    """

            print("\nGenerated Prompt:")
            print(prompt)
            return prompt
            
        except Exception as e:
            raise Exception(f"Error accessing GitHub repository: {str(e)}")
    

