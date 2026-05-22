import logging
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger("research.tools.branch")

def switch_branch(branch_id: str, root: Path) -> Dict[str, Any]:
    try:
        from research_os.state.state_ledger import StateLedger
        ledger = StateLedger(root)
        result = ledger.switch_branch(branch_id)
        return result
    except Exception as e:
        logger.error(f"Switch branch failed: {e}")
        return {"status": "error", "message": str(e)}

def merge_branches(source: str, target: str, message: str, root: Path) -> Dict[str, Any]:
    try:
        from research_os.state.state_ledger import StateLedger
        ledger = StateLedger(root)
        result = ledger.merge_branch(source, target, message)
        return result
    except Exception as e:
        logger.error(f"Merge branch failed: {e}")
        return {"status": "error", "message": str(e)}

def list_branches(root: Path) -> Dict[str, Any]:
    try:
        from research_os.project_ops import load_state
        state = load_state(root)
        return {"status": "success", "branches": list(state.get("branches", {}).keys()), "current_branch": state.get("current_branch")}
    except Exception as e:
        logger.error(f"List branches failed: {e}")
        return {"status": "error", "message": str(e)}
