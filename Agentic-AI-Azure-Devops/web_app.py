"""
Web UI for Agentic AI Azure DevOps
Provides a clean interface to run workflows on work items
"""

import asyncio
import sys
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from openai import AzureOpenAI
from config import SystemConfig
from core import MCPConnectionManager, WorkflowContext
from agents import OrchestratorAgent, DevOpsAgent, CodeAgent, TestAgent, ValidationAgent
from services import CodebaseRAG
from utils import StateManager
import threading
from queue import Queue

app = Flask(__name__)
CORS(app)

# Store active workflows
active_workflows = {}
workflow_outputs = {}

class OutputCapture:
    """Capture print statements to a queue"""
    def __init__(self, queue):
        self.queue = queue
        self.terminal = sys.stdout

    def write(self, message):
        if message and message.strip():
            self.queue.put({
                'type': 'output',
                'message': message,
                'timestamp': datetime.now().isoformat()
            })
        self.terminal.write(message)

    def flush(self):
        self.terminal.flush()


async def run_workflow_async(work_item_id: str, force_reindex: bool, output_queue: Queue):
    """Run the complete workflow with output capture"""
    try:
        # Redirect stdout to capture print statements
        old_stdout = sys.stdout
        sys.stdout = OutputCapture(output_queue)

        output_queue.put({
            'type': 'phase',
            'phase': 'initialization',
            'message': 'Starting workflow initialization...'
        })

        config = SystemConfig()
        state_mgr = StateManager()
        mcp_manager = MCPConnectionManager()

        ai_client = AzureOpenAI(
            azure_endpoint=config.azure_endpoint,
            api_key=config.azure_key,
            api_version=config.api_version
        )

        # Initialize RAG
        output_queue.put({
            'type': 'status',
            'message': f'Initializing RAG system (reindex={force_reindex})...'
        })

        rag = CodebaseRAG(
            config.repository_path,
            ai_client,
            embedding_deployment=config.embedding_deployment_name
        )
        rag.index_repository(force_reindex=force_reindex)

        # Show project analysis
        project_info = rag.analyze_project()
        output_queue.put({
            'type': 'project_info',
            'info': project_info
        })

        await mcp_manager.start_azure_devops_mcp(
            config.organization_url,
            config.pat_token,
            config.default_project
        )
        await mcp_manager.start_filesystem_mcp(config.repository_path)

        # Initialize agents
        orchestrator = OrchestratorAgent(
            ai_client,
            config.deployment_name,
            mcp_manager,
            rag
        )
        orchestrator.refresh_project_context()
        devops_agent = DevOpsAgent(ai_client, config.deployment_name, mcp_manager, config.repository_path, config.repository_id)
        code_agent = CodeAgent(ai_client, config.deployment_name, mcp_manager, rag, config.repository_path)
        test_agent = TestAgent(ai_client, config.deployment_name, mcp_manager, rag, config.repository_path)
        validation_agent = ValidationAgent(ai_client, config.deployment_name)

        # Create context
        context = WorkflowContext()
        context.work_item_id = work_item_id
        context.repository_path = config.repository_path

        # PHASE 1: Planning
        output_queue.put({
            'type': 'phase',
            'phase': 'planning',
            'message': 'PHASE 1: PLANNING'
        })

        if not await orchestrator.execute(context):
            output_queue.put({'type': 'error', 'message': 'Planning failed'})
            await mcp_manager.cleanup()
            return
        state_mgr.save_context(context, "phase1_planning")

        # PHASE 2: Branch Creation
        output_queue.put({
            'type': 'phase',
            'phase': 'branch',
            'message': 'PHASE 2: BRANCH CREATION'
        })

        if not await devops_agent.create_feature_branch(context):
            output_queue.put({'type': 'error', 'message': 'Branch creation failed'})
            await mcp_manager.cleanup()
            return
        state_mgr.save_context(context, "phase2_branch")

        # PHASE 3: Implementation
        output_queue.put({
            'type': 'phase',
            'phase': 'implementation',
            'message': 'PHASE 3: IMPLEMENTATION'
        })

        plan = context.execution_plan.get("implementation", {})
        steps = plan.get("implementation_steps", [])
        code_steps = [s for s in steps if s.get("agent") == "CodeAgent"]

        for i, step in enumerate(code_steps, 1):
            output_queue.put({
                'type': 'step',
                'step': i,
                'total': len(code_steps),
                'description': step.get('description', 'Unknown step')
            })
            if not await code_agent.execute_step(context, step):
                output_queue.put({'type': 'error', 'message': f'Step {i} failed'})
                break

        state_mgr.save_context(context, "phase3_implementation")

        # PHASE 4: Testing
        output_queue.put({
            'type': 'phase',
            'phase': 'testing',
            'message': 'PHASE 4: TESTING'
        })

        test_steps = [s for s in steps if s.get("agent") == "TestAgent"]
        for i, step in enumerate(test_steps, 1):
            output_queue.put({
                'type': 'step',
                'step': i,
                'total': len(test_steps),
                'description': step.get('description', 'Unknown test step')
            })
            if not await test_agent.execute_step(context, step):
                output_queue.put({'type': 'error', 'message': f'Test step {i} failed'})
                break

        await test_agent.run_tests(context)
        state_mgr.save_context(context, "phase4_testing")

        # PHASE 4.5: Validation
        output_queue.put({
            'type': 'phase',
            'phase': 'validation',
            'message': 'PHASE 4.5: VALIDATION'
        })

        if not await validation_agent.execute(context):
            output_queue.put({'type': 'error', 'message': 'Validation failed - acceptance criteria not met'})
            await mcp_manager.cleanup()
            return
        state_mgr.save_context(context, "phase4.5_validation")

        # PHASE 5: Commit & Push
        output_queue.put({
            'type': 'phase',
            'phase': 'commit',
            'message': 'PHASE 5: COMMIT & PUSH'
        })

        commit_message = f"feat: {context.work_item_title}\n\nImplements work item #{context.work_item_id}"
        if await devops_agent.commit_changes(context, commit_message):
            output_queue.put({'type': 'status', 'message': 'Changes committed'})

            if await devops_agent.push_to_remote(context):
                output_queue.put({'type': 'status', 'message': 'Pushed to remote'})
            else:
                output_queue.put({'type': 'error', 'message': 'Push failed'})
                await mcp_manager.cleanup()
                return
        else:
            output_queue.put({'type': 'error', 'message': 'Commit failed'})
            await mcp_manager.cleanup()
            return

        state_mgr.save_context(context, "phase5_commit")

        # PHASE 6: Create PR
        output_queue.put({
            'type': 'phase',
            'phase': 'pr',
            'message': 'PHASE 6: PULL REQUEST'
        })

        if await devops_agent.create_pull_request(context):
            output_queue.put({
                'type': 'status',
                'message': f'Pull Request created: {context.pr_url}'
            })
        else:
            output_queue.put({'type': 'error', 'message': 'PR creation failed'})
            await mcp_manager.cleanup()
            return

        state_mgr.save_context(context, "phase6_complete")

        # Final Summary
        output_queue.put({
            'type': 'complete',
            'summary': {
                'work_item_id': context.work_item_id,
                'work_item_title': context.work_item_title,
                'branch_name': context.branch_name,
                'implementation_files': list(context.implementation_files.keys()),
                'test_files': context.test_files,
                'pr_url': context.pr_url
            }
        })

        await mcp_manager.cleanup()

    except Exception as e:
        output_queue.put({
            'type': 'error',
            'message': f'Workflow failed: {str(e)}'
        })
    finally:
        sys.stdout = old_stdout
        output_queue.put({'type': 'done'})


def run_workflow_thread(work_item_id: str, force_reindex: bool, output_queue: Queue):
    """Run workflow in a separate thread"""
    asyncio.run(run_workflow_async(work_item_id, force_reindex, output_queue))


@app.route('/')
def index():
    """Serve the main UI"""
    return render_template('index.html')


@app.route('/api/start', methods=['POST'])
def start_workflow():
    """Start a new workflow"""
    data = request.json
    work_item_id = data.get('work_item_id', '').strip()
    force_reindex = data.get('force_reindex', False)

    if not work_item_id:
        return jsonify({'error': 'Work item ID is required'}), 400

    if work_item_id in active_workflows:
        return jsonify({'error': 'Workflow already running for this work item'}), 400

    # Create output queue
    output_queue = Queue()
    workflow_outputs[work_item_id] = output_queue

    # Start workflow in background thread
    thread = threading.Thread(
        target=run_workflow_thread,
        args=(work_item_id, force_reindex, output_queue)
    )
    thread.daemon = True
    thread.start()

    active_workflows[work_item_id] = thread

    return jsonify({
        'success': True,
        'work_item_id': work_item_id,
        'message': 'Workflow started'
    })


@app.route('/api/stream/<work_item_id>')
def stream_output(work_item_id):
    """Stream workflow output in real-time"""
    if work_item_id not in workflow_outputs:
        return jsonify({'error': 'No workflow found'}), 404

    output_queue = workflow_outputs[work_item_id]

    def generate():
        while True:
            try:
                msg = output_queue.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"

                if msg.get('type') == 'done':
                    # Cleanup
                    if work_item_id in active_workflows:
                        del active_workflows[work_item_id]
                    if work_item_id in workflow_outputs:
                        del workflow_outputs[work_item_id]
                    break
            except:
                # Timeout - send keepalive
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/status')
def get_status():
    """Get status of all workflows"""
    return jsonify({
        'active_workflows': list(active_workflows.keys())
    })


if __name__ == '__main__':
    print("="*60)
    print("Agentic AI Azure DevOps - Web UI")
    print("="*60)
    print("Starting web server on http://localhost:5001")
    print("Press Ctrl+C to stop")
    print("="*60)
    app.run(debug=False, host='0.0.0.0', port=5001, threaded=True)
