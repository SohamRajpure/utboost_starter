import os
import json
from pathlib import Path
import re
from datasets import load_dataset

# After generating UTBoost tests, append to existing test suite
def pull_test_case(instance_id):

    context_file = f"context_results/{instance_id}.json"
    
    with open(context_file, 'r') as f:
        data = json.load(f)
        test_case = data.get('test_case', '')
        # Extract the Python code block from the test case
        match = re.search(r'```python\n(.*?)```', test_case, re.DOTALL)
        if match:
            return match.group(1).strip()
        return test_case
    
# Load SWE-bench Lite dataset
dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")

# Run the function for each instance_id in the context_results directory
for file in os.listdir("context_results"):
    curr_instance_id = file.split(".")[0]
    test_case = pull_test_case(curr_instance_id)
    print(curr_instance_id)
    instance = next(x for x in dataset if x["instance_id"] == curr_instance_id)

    #Create a {instance_id}.json file under the UTBoost_experiment/test_cases directory for every test case pulled 
    os.makedirs(f"test_cases", exist_ok=True)
    with open(f"test_cases/{curr_instance_id}.json", "w") as f:
        instance["test_patch"] = test_case
        json.dump(instance, f)  # SERIALIZE DICT TO JSON




