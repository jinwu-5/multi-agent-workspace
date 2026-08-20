"""
State management for testing and development
Saves workflow context to avoid repeated API calls
"""

import json
import os
from datetime import datetime


class StateManager:
    """Save and load workflow context for efficient testing"""
    
    def __init__(self, state_dir: str = ".workflow_states"):
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
    
    def save_context(self, context, name: str = None) -> str:
        """Save workflow context to JSON file"""
        if name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"context_{context.work_item_id}_{timestamp}"
        
        filepath = os.path.join(self.state_dir, f"{name}.json")
        
        # Serialize context
        state = {
            "saved_at": datetime.now().isoformat(),
            "work_item": {
                "id": context.work_item_id,
                "title": context.work_item_title,
                "description": context.work_item_description,
                "acceptance_criteria": context.acceptance_criteria,
            },
            "git": {
                "branch_name": context.branch_name,
                "repository_path": context.repository_path,
            },
            "execution_plan": context.execution_plan,
            "implementation": {
                "files": context.implementation_files,
                "relevant_files": context.relevant_files,
                "code_patterns": context.code_patterns,
            },
            "testing": {
                "test_files": context.test_files,
                "test_results": context.test_results,
            },
            "pr": {
                "pr_id": context.pr_id,
                "pr_url": context.pr_url,
            },
            "history": context.agent_history,
            "errors": context.errors,
            "current_state": context.current_state.value,
        }
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        
        print(f"✓ State saved: {filepath}")
        return filepath
    
    def load_context(self, name: str):
        """Load workflow context from JSON file"""
        from core import WorkflowContext, AgentState
        
        filepath = os.path.join(self.state_dir, f"{name}.json")
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"State file not found: {filepath}")
        
        with open(filepath, 'r') as f:
            state = json.load(f)
        
        # Reconstruct context
        context = WorkflowContext()
        
        # Work item
        context.work_item_id = state["work_item"]["id"]
        context.work_item_title = state["work_item"]["title"]
        context.work_item_description = state["work_item"]["description"]
        context.acceptance_criteria = state["work_item"]["acceptance_criteria"]
        
        # Git
        context.branch_name = state["git"]["branch_name"]
        context.repository_path = state["git"]["repository_path"]
        
        # Execution plan
        context.execution_plan = state["execution_plan"]
        
        # Implementation
        context.implementation_files = state["implementation"]["files"]
        context.relevant_files = state["implementation"]["relevant_files"]
        context.code_patterns = state["implementation"]["code_patterns"]
        
        # Testing
        context.test_files = state["testing"]["test_files"]
        context.test_results = state["testing"]["test_results"]
        
        # PR
        context.pr_id = state["pr"]["pr_id"]
        context.pr_url = state["pr"]["pr_url"]
        
        # History
        context.agent_history = state["history"]
        context.errors = state["errors"]
        context.current_state = AgentState(state["current_state"])
        
        print(f"✓ State loaded: {filepath}")
        print(f"  Work Item: {context.work_item_title}")
        print(f"  Branch: {context.branch_name}")
        print(f"  State: {context.current_state.value}")
        
        return context
    
    def list_saved_states(self):
        """List all saved states"""
        states = []
        for file in os.listdir(self.state_dir):
            if file.endswith('.json'):
                filepath = os.path.join(self.state_dir, file)
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    states.append({
                        'filename': file.replace('.json', ''),
                        'saved_at': data.get('saved_at'),
                        'work_item': data['work_item']['title'],
                        'state': data['current_state']
                    })
        return states
    
    def delete_state(self, name: str):
        """Delete a saved state"""
        filepath = os.path.join(self.state_dir, f"{name}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"✓ Deleted: {filepath}")
        else:
            print(f"✗ Not found: {filepath}")
