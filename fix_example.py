import re

with open("docs/tutorials/EXAMPLE_WALKTHROUGH.md", "r") as f:
    content = f.read()

content = content.replace(
    "11. **Agent**: Writes a Python script `workspace/01_experiment_baseline/scripts/01_eda.py` to analyze the sampled data.",
    "11. **Agent**: Calls `sys.path.create` to create the first experiment path (`01_baseline_eda`). Writes a Python script `workspace/01_baseline_eda/scripts/01_eda.py` to analyze the sampled data."
)
content = content.replace("workspace/01_experiment_baseline", "workspace/01_baseline_eda")

with open("docs/tutorials/EXAMPLE_WALKTHROUGH.md", "w") as f:
    f.write(content)
