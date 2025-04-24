import json
import os

def calculate_success_rate(test_results_dir):
    total_instances = 0
    total_completed = 0

    # Iterate over each JSON file in the test_results directory
    for filename in os.listdir(test_results_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(test_results_dir, filename)
            with open(file_path, 'r') as file:
                data = json.load(file)
                file_total_instances = data.get("total_instances", 0)
                file_completed_instances = len(data.get("completed_ids", []))
                print(f"File: {filename}, Total Instances: {file_total_instances}, Completed Instances: {file_completed_instances}")
                total_instances += file_total_instances
                total_completed += file_completed_instances

    # Calculate the success rate
    success_rate = (total_completed / total_instances) * 100 if total_instances > 0 else 0
    print(f"Total Instances Across All Files: {total_instances}")
    print(f"Total Completed Instances Across All Files: {total_completed}")
    return success_rate

def calculate_original_pass_rate(tasks_dir, task_list):
    total_tasks = len(task_list)  # Total number of tasks in the list
    unique_patches = set()  # Use a set to avoid double counting patches

    # Iterate over the list of tasks
    for task in task_list:
        passed_patches_file = os.path.join(tasks_dir, task, "passed_agent_passes.json")
        if os.path.exists(passed_patches_file):
            with open(passed_patches_file, 'r') as file:
                passed_patches = json.load(file)
                task_passed_patches = len(passed_patches)
                print(f"Task: {task}, Passed Patches: {task_passed_patches}")
                for patch in passed_patches:
                    unique_patches.add(patch["model_patch"])  # Add unique patches

    total_passed_patches = len(unique_patches)
    print(f"Unique Patches Across All Tasks: {total_passed_patches}")

    # Calculate the original pass rate
    original_pass_rate = (total_passed_patches / (total_tasks * 20)) * 100 if total_tasks > 0 else 0
    return original_pass_rate

def main():
    test_results_dir = "/Users/sohamrajpure/Documents/research/UTBoost_experiment/test_results"
    tasks_dir = "/Users/sohamrajpure/Documents/research/UTBoost_experiment/tasks"
    task_list = [
        "astropy__astropy-7166",
        "astropy__astropy-12907",
        "astropy__astropy-14096",
        "astropy__astropy-14309",
        "astropy__astropy-20916",
        "sympy__sympy-20916"
    ]   
    # Calculate success rate from test results
    success_rate = calculate_success_rate(test_results_dir)
    print(f"Overall Success Rate: {success_rate:.2f}%")

    # Calculate original pass rate from passed patches
    original_pass_rate = calculate_original_pass_rate(tasks_dir, task_list)
    print(f"Original Pass Rate: {original_pass_rate:.2f}%")

if __name__ == "__main__":
    main()
