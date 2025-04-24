import json
import os
from typing import Dict, List
from openai import OpenAI
from UTBoost_experiment.codebase_analyzer import CodebaseAnalyzer

class ContextGenerator:
    def __init__(self, github_token: str = None, openai_api_key: str = None):
        """
        Initialize the context generator with necessary API keys.
        
        Args:
            github_token: GitHub personal access token
            openai_api_key: OpenAI API key
        """
        self.analyzer = CodebaseAnalyzer()
        self.github_token = github_token
        self.client = OpenAI(api_key=openai_api_key) if openai_api_key else None
        
    def load_task(self, task_file: str) -> Dict:
        """
        Load task information from passed_agent_passes.json.
        
        Args:
            task_file: Path to the JSON file containing task information or instance ID
            
        Returns:
            Dictionary containing task information
        """
        # If task_file is an instance ID, construct the path to the JSON file
        if not task_file.endswith('.json'):
            task_file = f"UTBoost_experiment/tasks/{task_file}/passed_agent_passes.json"
            
        with open(task_file, 'r') as f:
            tasks = json.load(f)
            
        # If tasks is a list, take the first task
        if isinstance(tasks, list):
            if not tasks:
                raise ValueError("No tasks found in the file")
            return tasks[0]
            
        # If it's a single task object, return it
        return tasks
            
    def derive_repo_info(self, task_info: Dict) -> Dict:
        """
        Derive repository information from task info.
        
        Args:
            task_info: Dictionary containing task information
            
        Returns:
            Dictionary containing repository information
        """
        return self.analyzer.derive_repo_info(task_info)
        
    def get_llm_response(self, prompt: str, model: str = "gpt-4-turbo-preview") -> str:
        """
        Get response from OpenAI's LLM.
        
        Args:
            prompt: The prompt to send to the LLM
            model: The OpenAI model to use (default: gpt-4-turbo-preview with 128k context window)
            
        Returns:
            The LLM's response
        """
        if not self.client:
            raise ValueError("OpenAI API key not provided")
            
        # Calculate token count (rough estimation)
        # Average of 4 characters per token for English text
        estimated_tokens = len(prompt) // 4
        
        # Maximum tokens for the model (leaving room for response)
        max_tokens = 120000  # Slightly below the 128k limit to be safe
        
        if estimated_tokens > max_tokens:
            print(f"\nWarning: Prompt exceeds token limit ({estimated_tokens} tokens)")
            print("Truncating prompt to fit within limits...")
            
            # Truncate the prompt while trying to maintain structure
            truncated_prompt = prompt[:max_tokens * 4]  # Convert tokens back to characters
            
            # Try to end at a reasonable point (e.g., after a complete sentence)
            last_period = truncated_prompt.rfind('.')
            if last_period != -1:
                truncated_prompt = truncated_prompt[:last_period + 1]
            
            print(f"Truncated to approximately {len(truncated_prompt) // 4} tokens")
            prompt = truncated_prompt
            
        print("\n=== Sending prompt to LLM ===")
        print(prompt)
        print("===========================\n")
            
        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
        
    def extract_top_files(self, llm_response: str) -> List[str]:
        """
        Extract top files from LLM response.
        
        Args:
            llm_response: Response from file level localization
            
        Returns:
            List of top file paths
        """
        # This is a simple implementation - you might want to make it more robust
        files = []
        for line in llm_response.split('\n'):
            if line.startswith('- '):
                file_path = line.split('(')[0].strip('- ').strip()
                files.append(file_path)
        return files
        
    def process_task(self, task_data: Dict) -> Dict:
        """
        Process a single task through the complete workflow.
        
        Args:
            task_data: Dictionary containing task information
            
        Returns:
            Dictionary containing all generated context and test case
        """
        # 1. Derive repository information
        repo_info = self.derive_repo_info(task_data)
        
        # Extract issue description from model_patch if not provided
        issue_description = task_data.get("issue_description", "")
        if not issue_description and "model_patch" in task_data:
            # Try to extract issue description from the patch
            patch = task_data["model_patch"]
            # Look for a comment or description in the patch
            import re
            comment_match = re.search(r'#\s*(.*?)(?:\n|$)', patch)
            if comment_match:
                issue_description = comment_match.group(1)
            else:
                # If no comment found, use the first few lines of the patch
                issue_description = "\n".join(patch.split('\n')[:5])
        
        # 2. Create and process file level localization
        file_prompt = CodebaseAnalyzer.file_level_localization(
            repo_owner=repo_info["repo_owner"],
            repo_name=repo_info["repo_name"],
            issue_description=issue_description,
            test_patch=task_data.get("model_patch", ""),
            github_token=self.github_token
        )
        file_response = self.get_llm_response(file_prompt)
        top_files = self.extract_top_files(file_response)
        
        # 3. Create and process function class localization
        func_prompt = CodebaseAnalyzer.function_class_localization(
            repo_owner=repo_info["repo_owner"],
            repo_name=repo_info["repo_name"],
            top_files=top_files,
            issue_desc=issue_description,
            test_patch=task_data.get("model_patch", ""),
            github_token=self.github_token
        )
        func_response = self.get_llm_response(func_prompt)
        
        # 4. Create and process line level localization
        line_prompt = CodebaseAnalyzer.line_level_localization(
            repo_owner=repo_info["repo_owner"],
            repo_name=repo_info["repo_name"],
            target_functions=[func.strip('- ') for func in func_response.split('\n') if func.startswith('- ')],
            issue_desc=issue_description,
            test_patch=task_data.get("model_patch", ""),
            github_token=self.github_token
        )
        line_response = self.get_llm_response(line_prompt)
        
        # 5. Generate test case
        test_case_prompt = f"""Based on the following information, generate a test case:

Repository Information:
{repo_info}

File Level Analysis:
{file_response}

Function/Class Analysis:
{func_response}

Line Level Analysis:
{line_response}

Task Information:
{task_data}

Original Patch:
{task_data.get('model_patch', '')}

Generate a comprehensive test case that:
1. Tests the identified functionality
2. Includes necessary imports
3. Follows the project's testing conventions
4. Handles edge cases
5. Includes proper documentation
"""
        test_case = self.get_llm_response(test_case_prompt)
        
        return {
            "repository_info": repo_info,
            "file_level_analysis": file_response,
            "function_class_analysis": func_response,
            "line_level_analysis": line_response,
            "test_case": test_case
        }

def select_task(task_file: str) -> Dict:
    """
    Load tasks and let user select one to process.
    
    Args:
        task_file: Path to the JSON file containing tasks
        
    Returns:
        Selected task information
    """
    with open(task_file, 'r') as f:
        tasks = json.load(f)
        
    if not tasks:
        raise ValueError("No tasks found in the file")
        
    # If tasks is a list, show options
    if isinstance(tasks, list):
        print("\nAvailable tasks:")
        for i, task in enumerate(tasks, 1):
            print(f"{i}. {task.get('task_id', 'Unknown Task')}")
            
        while True:
            try:
                choice = int(input("\nSelect a task number to process: "))
                if 1 <= choice <= len(tasks):
                    return tasks[choice - 1]
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
    else:
        # If it's a single task object, return it
        return tasks

def main():
    # Get API keys from environment variables
    github_token = os.getenv('GITHUB_TOKEN')
    openai_api_key = os.getenv('OPENAI_API_KEY')
    
    if not github_token or not openai_api_key:
        print("""
        Please set your API keys as environment variables:
        
        1. For temporary use in current session:
           export GITHUB_TOKEN='your_github_token'
           export OPENAI_API_KEY='your_openai_api_key'
        
        2. For permanent use, add to ~/.zshrc:
           echo 'export GITHUB_TOKEN="your_github_token"' >> ~/.zshrc
           echo 'export OPENAI_API_KEY="your_openai_api_key"' >> ~/.zshrc
           source ~/.zshrc
        
        3. Or use a password manager/secure note to store the keys
           and set them as environment variables when needed.
        """)
        return
    
    # Initialize context generator
    generator = ContextGenerator(github_token=github_token, openai_api_key=openai_api_key)
    
    try:
        # Get instance ID from command line or use default
        import sys
        if len(sys.argv) > 1:
            instance_id = sys.argv[1]
        else:
            instance_id = "sympy__sympy-20916"  # Default instance ID
            
        print(f"\nProcessing instance: {instance_id}")
        
        # Load and process the task
        task_data = generator.load_task(instance_id)
        print(f"\nProcessing task ID: {instance_id}")
        
        # Print task data structure for debugging
        print("\nTask data structure:")
        print(json.dumps(task_data, indent=2))
        
        result = generator.process_task(task_data)
        
        # Save results with instance ID in filename
        output_file = f"task_analysis_results_{instance_id}.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nAnalysis complete. Results saved to {output_file}")
        
    except Exception as e:
        print(f"\nError processing task: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 