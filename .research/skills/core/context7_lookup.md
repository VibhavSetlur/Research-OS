# Skill: Docs-First Code Generation via Context7

## Purpose
Prevents agents from inventing APIs or using deprecated function signatures by enforcing a "docs-first" generation pattern. Any code using scientific or plotting libraries must base its syntax on current documentation retrieved dynamically.

## Mandatory Libraries
Must be used for: `scipy`, `statsmodels`, `pandas`, `sklearn`, `lifelines`, `pymc`, `networkx`, `geopandas`, `altair`, `bokeh`, `panel`, `holoviews`, `dash`, `plotly`.

## Protocol

1. **Resolve Library ID:**
   Before querying documentation, resolve the standard library name to its unique Context7 ID.
   ```bash
   python .research/scripts/utils/context7_lookup.py resolve <library_name>
   ```

2. **Query Documentation:**
   Using the resolved ID, query the specific topic or function name to fetch the current API signature, parameters, and example usage.
   ```bash
   python .research/scripts/utils/context7_lookup.py docs <library_id> <topic_or_function>
   ```

3. **Incorporate in Generation:**
   Construct imports and calls strictly adhering to the returned signatures. Never rely on base training weights for library syntax.

4. **Cache Integration:**
   All documentation searches are cached in the research SQLite database (`.research/cache/research_cache.db`) with a TTL of 30 days to avoid redundant lookups.
