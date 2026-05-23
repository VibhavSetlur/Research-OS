import glob

files = [
    "templates/AGENTS.md",
    "templates/.cursor/rules/research-os.mdc",
    "templates/.claude/rules/research-os.md",
    "templates/.antigravity/rules/research-os.md"
]

old_text = "5. **Experiment Paths**: Use `sys.path.create` for new steps. Use `sys.path.abandon` for dead ends (preserves files)."
new_text = "5. **Experiment Paths**: Use `sys.path.create` for new steps. Use `sys.path.abandon` for dead ends (preserves files). The workspace does not contain a pre-built 01_ experiment folder. After understanding the data and research question, you must create the first experiment path using sys.path.create."

for f in files:
    try:
        with open(f, "r") as file:
            content = file.read()
        content = content.replace(old_text, new_text)
        with open(f, "w") as file:
            file.write(content)
    except FileNotFoundError:
        pass
