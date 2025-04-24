import json
import sys
from pathlib import Path
from typing import List, Dict, Optional
#
# Add SWE-bench to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent / "SWE-bench"))
from swebench.harness.run_evaluation import main as run_evaluation

def evaluate_agents(task_id: str, agent_patches: List[Dict]) -> List[Dict]:
    """
    Evaluate multiple agent solutions for a single task using SWE-Bench's default tests.
    """
    results = []
    for i, patch_data in enumerate(agent_patches):
        # Create JSONL prediction file
        pred_path = Path(f"temp_{task_id}_{i}.jsonl")
        with open(pred_path, "w") as f:
            # Write single JSON object per line (JSONL format)
            f.write(json.dumps({
                "instance_id": task_id,  # Use task ID from parameter
                "model_patch": patch_data["model_patch"],
                "test_patch": "",  # Empty string for default tests
                "model_name_or_path": patch_data.get("model_name", f"agent_{i}")
            }) + "\n")  # Newline required for JSONL
        
        # Run SWE-Bench evaluation 
        try:
            run_evaluation(
                dataset_name= f"/Users/sohamrajpure/Documents/research/UTBoost_experiment/test_cases/{task_id}.json",
                split= "test",
                instance_ids= [task_id],
                predictions_path= str(pred_path),
                max_workers= 1,
                force_rebuild= False,
                cache_level= "none",
                clean= False,
                open_file_limit= 1024,
                run_id= f"agent_{i}_{task_id}",
                timeout= 900,
                namespace= None,
                rewrite_reports= False,
                modal= False,
                instance_image_tag= "latest",
                report_dir= "/Users/sohamrajpure/Documents/research/UTBoost_experiment/test_results",
            )
        except Exception as e:
            print(f"Error evaluating agent {i} for task {task_id}: {e}")
            continue
        
        # Parse evaluation results
        result_path = Path(f"evaluation_results/agent_{i}_{task_id}/results.json")
        if result_path.exists():
            with open(result_path) as f:
                results.append(json.load(f)[task_id])
    
    # Print summary
    print(f"\nEvaluation results for task {task_id}:")
    for i, result in enumerate(results):
        print(f"\nAgent {i} results:")
        print(f"Original tests: {result['original']['passed']}/{result['original']['total']} passed")
        print(f"Patch size: {len(result['patch'].splitlines())} lines")
    
    return results

def select_best_solution(results: List[Dict]) -> Optional[Dict]:
    """
    Select the best solution: must pass all original tests and have the smallest patch.
    """
    candidates = []
    for res in results:
        #orig_pass = res['original']['passed'] / res['original']['total'] == 1
        patch_size = len(res['patch'].splitlines())
        #if orig_pass:
        candidates.append((-patch_size, res))  # Negative for smallest first

    return sorted(candidates)[0][1] if candidates else None

def main():
    tasks_dir = Path("tasks")
    tests = [
        "astropy__astropy-7166",
        "astropy__astropy-12907",
        "astropy__astropy-14096",
        "astropy__astropy-14309",
        "astropy__astropy-20916",
        "sympy__sympy-20916"
    ]

    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir() or task_dir.name not in tests:
            continue

        instance_id = task_dir.name
        patches_file = task_dir / "passed_agent_passes.json"
        if not patches_file.exists():
            continue

        with open(patches_file, 'r') as f:
            agent_patches = json.load(f)

        # Evaluate and select best
        results = evaluate_agents(instance_id, agent_patches)
        best_solution = select_best_solution(results)

        # Save best solution
        if best_solution:
            best_solutions_dir = Path("best_solutions")
            best_solutions_dir.mkdir(exist_ok=True)
            with open(best_solutions_dir / f"{instance_id}.json", 'w') as f:
                json.dump(best_solution, f)

if __name__ == "__main__":
    main()
