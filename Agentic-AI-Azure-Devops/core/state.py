from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any


class AgentState(Enum):
    """States in the multi-agent workflow"""
    INITIALIZED = "initialized"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    CREATING_BRANCH = "creating_branch"
    SEARCHING_RAG = "searching_rag"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    VALIDATING = "validating"
    COMMITTING = "committing"
    CREATING_PR = "creating_pr"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowContext:
    """Shared context across all agents"""
    # Work Item Information
    work_item_id: str = ""
    work_item_title: str = ""
    work_item_description: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)

    # Workflow State
    current_state: AgentState = AgentState.INITIALIZED
    execution_plan: Dict[str, Any] = field(default_factory=dict)

    # Git Information
    branch_name: str = ""
    repository_path: str = ""

    # Code Context
    relevant_files: List[str] = field(default_factory=list)
    code_patterns: List[Dict] = field(default_factory=list)
    implementation_files: Dict[str, str] = field(default_factory=dict)

    # Test Information
    test_files: List[str] = field(default_factory=list)
    test_results: Dict[str, Any] = field(default_factory=dict)

    # Validation Information
    validation_results: Dict[str, Any] = field(default_factory=dict)

    # PR Information
    pr_url: str = ""
    pr_id: str = ""

    # History & Logs
    agent_history: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add_log(self, agent_name: str, action: str, result: Any, success: bool = True):
        """Add an entry to agent history"""
        self.agent_history.append({
            "agent": agent_name,
            "action": action,
            "result": result,
            "success": success,
            "state": self.current_state.value
        })

    def add_error(self, error: str):
        """Add an error"""
        self.errors.append(error)