"""
Complete end-to-end workflow with --reindex support
"""

import asyncio
import os
import sys
from openai import AzureOpenAI
from config import SystemConfig
from core import MCPConnectionManager, WorkflowContext
from agents import OrchestratorAgent, DevOpsAgent, CodeAgent, TestAgent, ValidationAgent
from services import CodebaseRAG
from utils import StateManager


async def main():
    # Check for --reindex flag
    force_reindex = '--reindex' in sys.argv
    
    print("="*60)
    print("COMPLETE WORKFLOW - ORCHESTRATE TO PR")
    if force_reindex:
        print("(FORCE REINDEX MODE)")
    print("="*60)
    
    config = SystemConfig()
    state_mgr = StateManager()
    mcp_manager = MCPConnectionManager()
    
    ai_client = AzureOpenAI(
        azure_endpoint=config.azure_endpoint,
        api_key=config.azure_key,
        api_version=config.api_version
    )
    
    # Initialize RAG (will use cache unless --reindex)
    rag = CodebaseRAG(
        config.repository_path,
        ai_client,
        embedding_deployment=config.embedding_deployment_name
    )
    rag.index_repository(force_reindex=force_reindex)
    
    # Show project analysis
    project_info = rag.analyze_project()
    print(f"\n[Project Analysis]")
    print(f"  Language: {project_info['primary_language']}")
    print(f"  Frameworks: {', '.join(project_info['frameworks']) or 'None detected'}")
    print(f"  Files: {project_info['total_files']}")
    
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
    context.work_item_id = input("\nEnter Work Item ID: ") or "9"
    context.repository_path = config.repository_path
    
    # PHASE 1: Planning
    print("\n" + "="*60)
    print("PHASE 1: PLANNING")
    print("="*60)
    if not await orchestrator.execute(context):
        print("✗ Planning failed")
        await mcp_manager.cleanup()
        return
    state_mgr.save_context(context, "phase1_planning")
    
    # PHASE 2: Branch Creation
    print("\n" + "="*60)
    print("PHASE 2: BRANCH CREATION")
    print("="*60)

    if not await devops_agent.create_feature_branch(context):
        print("✗ Branch creation failed")
        await mcp_manager.cleanup()
        return
    state_mgr.save_context(context, "phase2_branch")
    
    # PHASE 3: Implementation
    print("\n" + "="*60)
    print("PHASE 3: IMPLEMENTATION")
    print("="*60)
    
    plan = context.execution_plan.get("implementation", {})
    steps = plan.get("implementation_steps", [])
    code_steps = [s for s in steps if s.get("agent") == "CodeAgent"]
    
    print(f"Executing {len(code_steps)} implementation steps...")
    for i, step in enumerate(code_steps, 1):
        print(f"\n[{i}/{len(code_steps)}] {step.get('description')[:80]}...")
        if not await code_agent.execute_step(context, step):
            print(f"✗ Step {i} failed")
            break
    
    state_mgr.save_context(context, "phase3_implementation")
    
    # PHASE 4: Testing
    print("\n" + "="*60)
    print("PHASE 4: TESTING")
    print("="*60)
    
    test_steps = [s for s in steps if s.get("agent") == "TestAgent"]
    print(f"Executing {len(test_steps)} test steps...")
    for i, step in enumerate(test_steps, 1):
        print(f"\n[{i}/{len(test_steps)}] {step.get('description')[:80]}...")
        if not await test_agent.execute_step(context, step):
            print(f"✗ Test step {i} failed")
            break
    
    await test_agent.run_tests(context)
    state_mgr.save_context(context, "phase4_testing")

    # PHASE 4.5: Validation (after testing, before commit)
    print("\n" + "="*60)
    print("PHASE 4.5: VALIDATION")
    print("="*60)

    if not await validation_agent.execute(context):
        print("✗ Validation failed - acceptance criteria not met")
        print("  Review the validation results above and fix the implementation")
        await mcp_manager.cleanup()
        return
    state_mgr.save_context(context, "phase4.5_validation")

    # PHASE 5: Commit & Push
    print("\n" + "="*60)
    print("PHASE 5: COMMIT & PUSH")
    print("="*60)
    
    commit_message = f"feat: {context.work_item_title}\n\nImplements work item #{context.work_item_id}"
    if await devops_agent.commit_changes(context, commit_message):
        print("✓ Changes committed")

        # Automatically push to remote
        if await devops_agent.push_to_remote(context):
            print("✓ Pushed to remote")
        else:
            print("✗ Push failed - check errors above")
            await mcp_manager.cleanup()
            return
    else:
        print("✗ Commit failed")
        await mcp_manager.cleanup()
        return

    state_mgr.save_context(context, "phase5_commit")

    # PHASE 6: Create PR
    print("\n" + "="*60)
    print("PHASE 6: PULL REQUEST")
    print("="*60)

    # Automatically create pull request
    if await devops_agent.create_pull_request(context):
        print("✓ Pull Request created")
        print(f"  PR URL: {context.pr_url}")
    else:
        print("✗ PR creation failed - check errors above")
        await mcp_manager.cleanup()
        return
    
    state_mgr.save_context(context, "phase6_complete")
    
    # Final Summary
    print("\n" + "="*60)
    print("WORKFLOW COMPLETE")
    print("="*60)
    print(f"Work Item: {context.work_item_title}")
    print(f"Branch: {context.branch_name}")
    print(f"Files Created: {len(context.implementation_files)}")
    for file in context.implementation_files.keys():
        print(f"  - {file}")
    print(f"Tests Created: {len(context.test_files)}")
    for test in context.test_files:
        print(f"  - {test}")
    if context.pr_url:
        print(f"PR: {context.pr_url}")
    print("="*60)
    
    await mcp_manager.cleanup()


if __name__ == "__main__":
    if '--help' in sys.argv:
        print("Usage: python run_complete_workflow.py [--reindex]")
        print("  --reindex: Force rebuild of code embeddings cache")
        sys.exit(0)
    
    asyncio.run(main())
