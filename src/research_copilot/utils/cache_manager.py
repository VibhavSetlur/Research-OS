#!/usr/bin/env python3
"""
Research Copilot Cache Manager
Manages SQLite database caching for searches, API calls, abstracts, stats, and LLM calls.
Tracks cache hit/miss statistics in state.json atomically.
"""

import os
import sys
import json
import sqlite3
import hashlib
import time
import argparse
from pathlib import Path
from typing import Any, Optional, Dict, Tuple, List


# Simple file lock for state.json
class FileLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.fd = None

    def acquire(self):
        start_time = time.time()
        while True:
            try:
                if sys.platform == 'win32':
                    if self.lock_path.exists():
                        raise OSError("Lock file exists")
                    self.lock_path.write_text(str(os.getpid()))
                else:
                    self.fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.write(self.fd, str(os.getpid()).encode())
                return True
            except (OSError, FileExistsError):
                if time.time() - start_time > 10:
                    raise TimeoutError(f"Could not acquire lock on {self.lock_path}")
                time.sleep(0.05)

    def release(self):
        try:
            if sys.platform == 'win32':
                if self.lock_path.exists():
                    self.lock_path.unlink()
            else:
                if self.fd is not None:
                    os.close(self.fd)
                    self.fd = None
                if self.lock_path.exists():
                    self.lock_path.unlink()
        except OSError:
            pass


class ResearchCache:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            # Locate project root
            current = Path.cwd()
            root = None
            for p in [current] + list(current.parents):
                if (p / ".research").exists():
                    root = p
                    break
            if not root:
                root = current
            self.db_path = root / ".research" / "cache" / "research_cache.db"
            self.state_path = root / ".research" / "cache" / "state.json"
        else:
            self.db_path = db_path
            self.state_path = db_path.parent / "state.json"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite tables if they do not exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Table 1: web_searches
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS web_searches (
                query_hash TEXT PRIMARY KEY,
                query TEXT,
                results TEXT,
                timestamp TEXT,
                expires_at TEXT
            )
        """)

        # Table 2: api_calls
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_calls (
                endpoint_params_hash TEXT PRIMARY KEY,
                endpoint TEXT,
                params TEXT,
                response TEXT,
                timestamp TEXT
            )
        """)

        # Table 3: paper_abstracts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_abstracts (
                doi TEXT PRIMARY KEY,
                abstract TEXT,
                title TEXT,
                authors TEXT,
                verified_at TEXT
            )
        """)

        # Table 4: computed_stats
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS computed_stats (
                data_op_hash TEXT PRIMARY KEY,
                data_hash TEXT,
                operation TEXT,
                result TEXT,
                timestamp TEXT
            )
        """)

        # Table 5: llm_calls
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_calls (
                prompt_hash TEXT PRIMARY KEY,
                prompt TEXT,
                response TEXT,
                model TEXT,
                timestamp TEXT
            )
        """)

        conn.commit()
        conn.close()

    def _update_state_ledger(self, hit: bool):
        """Update cache hit/miss count in state.json atomically."""
        if not self.state_path.exists():
            return

        lock_path = self.state_path.with_suffix(".lock")
        lock = FileLock(lock_path)
        try:
            lock.acquire()
            with open(self.state_path, "r") as f:
                state_data = json.load(f)

            if "cache_metrics" not in state_data:
                state_data["cache_metrics"] = {"hits": 0, "misses": 0}

            if hit:
                state_data["cache_metrics"]["hits"] += 1
            else:
                state_data["cache_metrics"]["misses"] += 1

            with open(self.state_path, "w") as f:
                json.dump(state_data, f, indent=2)
        except Exception:
            pass  # Suppress errors to prevent blocking execution
        finally:
            lock.release()

    def get_hash(self, text: str) -> str:
        """Helper to MD5 hash query/params/prompts."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    # --- Web Searches Caching ---
    def get_web_search(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch cached web search results if not expired."""
        query_hash = self.get_hash(query.strip().lower())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT results, expires_at FROM web_searches WHERE query_hash = ?", 
            (query_hash,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            results_json, expires_at_str = row
            # Check expiration
            expires_at = float(expires_at_str)
            if time.time() < expires_at:
                self._update_state_ledger(hit=True)
                return json.loads(results_json)
            else:
                # Clean up expired entry
                self.delete_web_search(query)
        
        self._update_state_ledger(hit=False)
        return None

    def set_web_search(self, query: str, results: List[Dict[str, Any]], ttl_days: float = 1.0):
        """Cache web search results with a custom TTL in days."""
        query_hash = self.get_hash(query.strip().lower())
        results_json = json.dumps(results)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires_at = time.time() + (ttl_days * 86400)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO web_searches (query_hash, query, results, timestamp, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (query_hash, query, results_json, timestamp, str(expires_at)))
        conn.commit()
        conn.close()

    def delete_web_search(self, query: str):
        query_hash = self.get_hash(query.strip().lower())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM web_searches WHERE query_hash = ?", (query_hash,))
        conn.commit()
        conn.close()

    # --- API Calls Caching ---
    def get_api_call(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        params_str = json.dumps(params, sort_keys=True)
        key = self.get_hash(f"{endpoint}:{params_str}")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM api_calls WHERE endpoint_params_hash = ?", (key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            self._update_state_ledger(hit=True)
            return json.loads(row[0])
        
        self._update_state_ledger(hit=False)
        return None

    def set_api_call(self, endpoint: str, params: Dict[str, Any], response: Dict[str, Any]):
        params_str = json.dumps(params, sort_keys=True)
        key = self.get_hash(f"{endpoint}:{params_str}")
        response_json = json.dumps(response)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO api_calls (endpoint_params_hash, endpoint, params, response, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (key, endpoint, params_str, response_json, timestamp))
        conn.commit()
        conn.close()

    # --- Paper Abstracts Caching (Permanent) ---
    def get_paper_abstract(self, doi: str) -> Optional[Dict[str, str]]:
        doi_clean = doi.strip().lower()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT abstract, title, authors FROM paper_abstracts WHERE doi = ?", 
            (doi_clean,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            self._update_state_ledger(hit=True)
            return {"abstract": row[0], "title": row[1], "authors": row[2]}
        
        self._update_state_ledger(hit=False)
        return None

    def set_paper_abstract(self, doi: str, abstract: str, title: str, authors: str):
        doi_clean = doi.strip().lower()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO paper_abstracts (doi, abstract, title, authors, verified_at)
            VALUES (?, ?, ?, ?, ?)
        """, (doi_clean, abstract, title, authors, timestamp))
        conn.commit()
        conn.close()

    # --- Computed Statistics Caching (Permanent unless data changes) ---
    def get_computed_stats(self, data_hash: str, operation: str) -> Optional[Dict[str, Any]]:
        key = self.get_hash(f"{data_hash}:{operation}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT result FROM computed_stats WHERE data_op_hash = ?", (key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            self._update_state_ledger(hit=True)
            return json.loads(row[0])
        
        self._update_state_ledger(hit=False)
        return None

    def set_computed_stats(self, data_hash: str, operation: str, result: Dict[str, Any]):
        key = self.get_hash(f"{data_hash}:{operation}")
        result_json = json.dumps(result)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO computed_stats (data_op_hash, data_hash, operation, result, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (key, data_hash, operation, result_json, timestamp))
        conn.commit()
        conn.close()

    # --- LLM Sub-calls Caching (Permanent) ---
    def get_llm_call(self, prompt: str, model: str) -> Optional[str]:
        key = self.get_hash(f"{model}:{prompt}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM llm_calls WHERE prompt_hash = ?", (key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            self._update_state_ledger(hit=True)
            return row[0]
        
        self._update_state_ledger(hit=False)
        return None

    def set_llm_call(self, prompt: str, model: str, response: str):
        key = self.get_hash(f"{model}:{prompt}")
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO llm_calls (prompt_hash, prompt, response, model, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (key, prompt, response, model, timestamp))
        conn.commit()
        conn.close()

    # --- Database Operations ---
    def clear(self):
        """Empty all tables in the cache database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM web_searches")
        cursor.execute("DELETE FROM api_calls")
        cursor.execute("DELETE FROM paper_abstracts")
        cursor.execute("DELETE FROM computed_stats")
        cursor.execute("DELETE FROM llm_calls")
        conn.commit()
        conn.close()

    def get_stats(self) -> Dict[str, int]:
        """Get row count for each cache table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        for table in ["web_searches", "api_calls", "paper_abstracts", "computed_stats", "llm_calls"]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = cursor.fetchone()[0]
            
        conn.close()
        return stats


def main():
    parser = argparse.ArgumentParser(description="Research Copilot Cache Controller")
    parser.add_argument("--clear", action="store_true", help="Clear all cache database entries")
    parser.add_argument("--stats", action="store_true", help="Show cache statistics and metrics")
    args = parser.parse_args()

    cache = ResearchCache()

    if args.clear:
        cache.clear()
        print("Successfully cleared all cache databases.")
        sys.exit(0)

    if args.stats:
        stats = cache.get_stats()
        print("=" * 60)
        print("CACHE DATABASE STATISTICS")
        print("=" * 60)
        for table, count in stats.items():
            print(f"  {table.ljust(20)}: {count} entries")
        print("=" * 60)

        # Print metrics from state.json
        if cache.state_path.exists():
            try:
                with open(cache.state_path, "r") as f:
                    state_data = json.load(f)
                metrics = state_data.get("cache_metrics", {"hits": 0, "misses": 0})
                total = metrics["hits"] + metrics["misses"]
                rate = (metrics["hits"] / total * 100) if total > 0 else 0
                print(f"  Ledger Hits         : {metrics['hits']}")
                print(f"  Ledger Misses       : {metrics['misses']}")
                print(f"  Ledger Total        : {total}")
                print(f"  Ledger Hit Rate     : {rate:.1f}%")
                print("=" * 60)
            except Exception as e:
                print(f"Error loading state.json: {e}")
        else:
            print("  state.json ledger not found. Run active project pipeline first.")
            print("=" * 60)
        sys.exit(0)

    parser.print_help()

def setup_vss_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        import sqlite_vss
        conn.enable_load_extension(True)
        sqlite_vss.load(conn)
    except Exception:
        pass
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            content TEXT,
            embedding JSON
        )
    ''')
    conn.commit()
    return conn

def ingest_file(filepath: Path, db_path: Path):
    print(f"Ingesting {filepath}...")
    content = ""
    if filepath.suffix == '.csv':
        try:
            content = filepath.read_text()
        except UnicodeDecodeError:
            pass
    elif filepath.suffix == '.pdf':
        try:
            import PyPDF2
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                content = " ".join([p.extract_text() for p in reader.pages if p.extract_text()])
        except ImportError:
            content = "PyPDF2 not installed"
    else:
        try:
            content = filepath.read_text()
        except UnicodeDecodeError:
            content = "Binary file"

    print("Generating embeddings...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embedding = model.encode(content[:5000]).tolist()
    except Exception:
        print("SentenceTransformer not found, using dummy embeddings")
        embedding = [0.0] * 384
    
    conn = setup_vss_db(db_path)
    conn.execute('INSERT INTO documents (filename, content, embedding) VALUES (?, ?, ?)',
                 (filepath.name, content[:5000], json.dumps(embedding)))
    conn.commit()
    print(f"Successfully ingested {filepath.name} into vector database.")

def cmd_ingest(args):
    filepath = Path(args.file)
    if not filepath.exists():
        print("File not found")
        return
    from research_copilot.utils.common import find_project_root
    root = find_project_root()
    if not root:
        print("Not in a project root")
        return
    db_path = root / ".research" / "cache" / "vss.sqlite"
    ingest_file(filepath, db_path)



if __name__ == "__main__":
    main()
