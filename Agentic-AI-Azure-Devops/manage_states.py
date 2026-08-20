"""
View and manage saved workflow states
"""

from utils import StateManager
import sys


def main():
    state_mgr = StateManager()
    
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        print("\nSaved Workflow States:")
        print("="*60)
        states = state_mgr.list_saved_states()
        if not states:
            print("No saved states found.")
        else:
            for state in states:
                print(f"\n{state['filename']}")
                print(f"  Saved: {state['saved_at']}")
                print(f"  Work Item: {state['work_item']}")
                print(f"  State: {state['state']}")
    
    elif len(sys.argv) > 2 and sys.argv[1] == "delete":
        state_mgr.delete_state(sys.argv[2])
    
    else:
        print("Usage:")
        print("  python manage_states.py list")
        print("  python manage_states.py delete <state_name>")


if __name__ == "__main__":
    main()
