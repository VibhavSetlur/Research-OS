# Cache & Memoization Manager

## Purpose
Enables persistent local caching of web search queries, API calls, paper abstracts, computed statistics, and deterministic LLM sub-calls using a SQLite database. This reduces external API costs, avoids redundant computational steps, and guarantees reproducibility.

## Protocol

### Cache Database Structure
All cached objects are stored in `.research/cache/research_cache.db`.

| Table | Key | Value Schema | TTL / Expiration |
|---|---|---|---|
| **`web_searches`** | `query_hash` (md5 of query) | `{results: [...], timestamp: ISO8601, expires_at: ISO8601}` | 7 days for papers, 1 day for news/general |
| **`api_calls`** | `endpoint_params_hash` | `{response: {...}, timestamp: ISO8601}` | 30 days default (customizable) |
| **`paper_abstracts`** | `doi` (normalized) | `{abstract: "...", title: "...", authors: "...", verified_at: ISO8601}` | Permanent (no expiration) |
| **`computed_stats`** | `data_op_hash` (data hash + operation string) | `{result: {...}, timestamp: ISO8601}` | Permanent / changes if data hash changes |
| **`llm_calls`** | `prompt_hash` | `{response: "...", model: "...", timestamp: ISO8601}` | Permanent (for deterministic prompt/settings) |

### Cache Hit / Miss Workflow
1. **Compute Hash:** Construct the key using a cryptographic hash (MD5 or SHA-256) of the input parameters or content.
2. **Lookup:** Search the target table for the computed key.
3. **Validate Expiration:** 
   - If key exists and `expires_at` (if present) is in the future, return cached content. Increment `cache_hits` in the state ledger (`state.json`).
   - If key exists but is expired, delete the key. Proceed to step 4.
4. **Cache Miss:** Execute the action (web search, compute, API request).
5. **Write Back:** Store the new result, timestamp, and expiration in the database. Increment `cache_misses` in `state.json`.

### CLI Reference
```bash
python .research/scripts/utils/cache_manager.py --clear
python .research/scripts/utils/cache_manager.py --stats
```
