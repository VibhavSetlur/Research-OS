with open("tests/test_core.py", "r") as f:
    content = f.read()

content = content.replace(
    'assert (root / "workspace" / "01_experiment_baseline").exists()',
    'assert not (root / "workspace" / "01_experiment_baseline").exists()'
)
content = content.replace('"02_"', '"01_"')
content = content.replace('"02_first"', '"01_first"')
content = content.replace('"03_second"', '"02_second"')
content = content.replace('"02_test_path"', '"01_test_path"')
content = content.replace('"03_test_path"', '"02_test_path"')

with open("tests/test_core.py", "w") as f:
    f.write(content)
