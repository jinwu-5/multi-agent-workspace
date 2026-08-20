import json
from typing import Any, Dict, List

import git
from git.remote import PushInfo

from core import AgentState, BaseAgent, WorkflowContext


class DevOpsAgent(BaseAgent):
    """
    DevOps Agent - Manages Git and Azure DevOps operations

    Responsibilities:
    1. Create and manage Git branches
    2. Commit code changes
    3. Push to remote repository
    4. Create pull requests
    5. Link commits to work items
    """

    def __init__(self, ai_client, deployment_name, mcp_manager, repo_path: str, repository_id: str = None):
        super().__init__("DevOps", ai_client, deployment_name)
        self.mcp_manager = mcp_manager
        self.repo_path = repo_path
        self.repo = None
        self.repository_id = repository_id
    
    async def execute(self, context: WorkflowContext) -> bool:
        """Main execution - not used directly, agents call specific methods"""
        return True
    
    def initialize_repo(self) -> bool:
        """Initialize Git repository"""
        try:
            self.repo = git.Repo(self.repo_path)
            print(f"[{self.name}] Git repo initialized: {self.repo_path}")
            return True
        except git.InvalidGitRepositoryError:
            print(f"[{self.name}] Not a git repository: {self.repo_path}")
            print(f"[{self.name}] Run 'git init' in your project directory first")
            return False
        except Exception as e:
            print(f"[{self.name}] Failed to initialize repo: {e}")
            return False
    
    async def create_feature_branch(self, context: WorkflowContext) -> bool:
        """Create a new feature branch for the work item"""
        self.log(context, "Creating feature branch", context.branch_name)
        context.current_state = AgentState.CREATING_BRANCH
        
        try:
            if not self.repo:
                if not self.initialize_repo():
                    return False
            
            # Check if branch already exists
            existing_branches = [b.name for b in self.repo.branches]
            
            if context.branch_name in existing_branches:
                self.log(context, "Branch exists", f"Checking out {context.branch_name}")
                self.repo.git.checkout(context.branch_name)
            else:
                # Create new branch from current HEAD
                self.repo.git.checkout('-b', context.branch_name)
                self.log(context, "Branch created", context.branch_name, True)
            
            return True
            
        except Exception as e:
            self.log(context, "Failed to create branch", str(e), False)
            context.add_error(f"Branch creation failed: {e}")
            return False
    
    async def commit_changes(self, context: WorkflowContext, 
                            commit_message: str = None) -> bool:
        """Commit all staged changes"""
        self.log(context, "Committing changes", "Staging files")
        context.current_state = AgentState.COMMITTING
        
        try:
            if not self.repo:
                if not self.initialize_repo():
                    return False
            
            # Get list of changed files
            changed_files = [item.a_path for item in self.repo.index.diff(None)]
            untracked_files = self.repo.untracked_files
            
            if not changed_files and not untracked_files:
                self.log(context, "No changes to commit", "Working tree clean")
                return True
            
            # Stage all changes
            self.repo.git.add(A=True)
            
            # Generate commit message if not provided
            if not commit_message:
                commit_message = await self._generate_commit_message(
                    context, 
                    changed_files + untracked_files
                )
            
            # Commit with work item reference
            full_message = f"{commit_message}\n\nWork Item: #{context.work_item_id}"
            self.repo.index.commit(full_message)
            
            self.log(context, "Changes committed", 
                    f"{len(changed_files)} modified, {len(untracked_files)} new")
            
            return True
            
        except Exception as e:
            self.log(context, "Failed to commit", str(e), False)
            context.add_error(f"Commit failed: {e}")
            return False
    
    async def _generate_commit_message(self, context: WorkflowContext,
                                      files: List[str]) -> str:
        """Use AI to generate a descriptive commit message"""

        system_prompt = """You are a Git commit message expert.
            Generate clear, concise commit messages following conventional commits format.

            Format: <type>: <description>

            Types: feat, fix, refactor, docs, test, style, chore

            Keep messages under 72 characters for the subject line."""

        file_list = "\n".join([f"- {f}" for f in files[:10]])
        if len(files) > 10:
            file_list += f"\n... and {len(files) - 10} more files"

        user_prompt = f"""Generate a commit message for:

            Work Item: {context.work_item_title}

            Files changed:
            {file_list}

            Description: {context.work_item_description[:200]}

            Respond with just the commit message, no explanation."""

        try:
            response = await self.call_ai(system_prompt, user_prompt, temperature=0.3)
            # Extract just the message (remove any markdown or extra text)
            commit_msg = response.strip().split('\n')[0]
            return commit_msg
        except:
            # Fallback message
            return f"feat: implement {context.work_item_title}"

    async def _generate_testing_steps(self, context: WorkflowContext,
                                     implementation_steps: List[Dict]) -> str:
        """Use AI to generate specific, actionable manual testing steps"""

        system_prompt = """You are a QA engineer writing manual testing instructions for code reviewers.

            Generate specific, actionable testing steps based on what was actually implemented.
            
            Format as a numbered list:
            1. First specific action to test
            2. Second specific action to test
            ...
            
            Focus on:
            - User-facing functionality (what the user sees/does)
            - Expected behavior (what should happen)
            - Edge cases and error scenarios
            - Integration points
            
            Be specific and concrete - NOT generic."""

        # Build context about what was implemented
        impl_summary = ""
        for i, step in enumerate(implementation_steps, 1):
            impl_summary += f"{i}. {step.get('description', 'N/A')}\n"

        # Include acceptance criteria
        criteria_text = "\n".join(f"- {c}" for c in context.acceptance_criteria[:5])

        user_prompt = f"""Generate manual testing steps for this implementation:

            Work Item: {context.work_item_title}
            
            Description: {context.work_item_description[:300]}
            
            Acceptance Criteria:
            {criteria_text}
            
            Implementation Steps:
            {impl_summary}
            
            Files Changed:
            {chr(10).join(f'- {f}' for f in list(context.implementation_files.keys())[:5])}
            
            Generate 4-6 specific testing steps that a reviewer can follow.
            Include the actual UI elements, expected behaviors, and edge cases to test.
            
            Respond with ONLY the numbered testing steps, no introduction or conclusion."""

        try:
            response = await self.call_ai(system_prompt, user_prompt,
                                         temperature=0.2, max_tokens=800)
            # Clean up the response
            testing_steps = response.strip()

            # Ensure it starts with a number
            if not testing_steps[0].isdigit():
                lines = testing_steps.split('\n')
                testing_steps = '\n'.join(line for line in lines if line.strip() and (line.strip()[0].isdigit() or line.strip().startswith('-')))

            return testing_steps + "\n"
        except Exception as e:
            # Fallback to basic steps
            return f"1. Pull the branch: `git checkout {context.branch_name}`\n2. Review the changes in the modified files\n3. Test the functionality described in the work item\n4. Verify acceptance criteria are met\n"
    
    async def push_to_remote(self, context: WorkflowContext,
                            remote_name: str = "origin") -> bool:
        """Push the feature branch to remote repository"""
        self.log(context, "Pushing to remote", f"{remote_name}/{context.branch_name}")

        try:
            if not self.repo:
                if not self.initialize_repo():
                    return False

            # Get remote
            remote = self.repo.remote(remote_name)
            print(f"[{self.name}] Remote URL: {remote.url}")

            # Push branch
            print(f"[{self.name}] Executing push...")
            push_info_list = remote.push(context.branch_name)
            print(f"[{self.name}] Push returned {len(push_info_list)} info objects")

            # Check if push was successful
            if push_info_list:
                # Get first push info
                info = push_info_list[0]
                print(f"[{self.name}] Push flags: {info.flags}")
                print(f"[{self.name}] Push summary: {info.summary}")

                # Check for errors in push
                if info.flags & PushInfo.ERROR:
                    self.log(context, "Push failed", f"Error: {info.summary}", False)
                    return False
                elif info.flags & (PushInfo.NEW_HEAD | PushInfo.FAST_FORWARD | PushInfo.FORCED_UPDATE | PushInfo.UP_TO_DATE):
                    # Success cases
                    self.log(context, "Pushed to remote",
                            f"{remote_name}/{context.branch_name}", True)
                    return True
                else:
                    self.log(context, "Push uncertain", f"Flags: {info.flags}, Summary: {info.summary}", False)
                    return False
            else:
                self.log(context, "Push failed", "No push info returned", False)
                return False

        except git.GitCommandError as e:
            # Branch might not have remote tracking yet
            if "has no upstream branch" in str(e):
                try:
                    # Set upstream and push
                    self.repo.git.push('--set-upstream', remote_name, context.branch_name)
                    self.log(context, "Pushed with upstream",
                            f"{remote_name}/{context.branch_name}", True)
                    return True
                except Exception as e2:
                    self.log(context, "Failed to push with upstream", str(e2), False)
                    return False
            else:
                self.log(context, "Push failed", str(e), False)
                return False
        except Exception as e:
            self.log(context, "Failed to push", str(e), False)
            context.add_error(f"Push failed: {e}")
            return False
    
    async def create_pull_request(self, context: WorkflowContext) -> bool:
        """Create a pull request in Azure DevOps"""
        self.log(context, "Creating pull request", "Preparing PR")
        context.current_state = AgentState.CREATING_PR

        try:
            # Build comprehensive PR description
            plan = context.execution_plan.get("implementation", {})

            # Start with work item description
            pr_description = f"## Summary\n{context.work_item_description}\n\n"

            # Add implementation details
            steps = plan.get("implementation_steps", [])
            if steps:
                pr_description += "## Implementation\n"
                for i, step in enumerate(steps, 1):
                    pr_description += f"{i}. {step.get('description', 'N/A')}\n"
                pr_description += "\n"

            # Add files changed
            if context.implementation_files:
                pr_description += "## Files Changed\n"
                for file_path in context.implementation_files.keys():
                    pr_description += f"- `{file_path}`\n"
                pr_description += "\n"

            # Add test information
            test_steps = [s for s in steps if s.get("agent") == "TestAgent"]
            if test_steps or context.test_files:
                pr_description += "## Testing\n"

                # Add test files
                if context.test_files:
                    pr_description += "**Test Files:**\n"
                    for test_file in context.test_files:
                        pr_description += f"- `{test_file}`\n"
                    pr_description += "\n"

                # Add test steps from execution plan
                if test_steps:
                    pr_description += "**Test Coverage:**\n"
                    for step in test_steps:
                        pr_description += f"- {step.get('description', 'N/A')}\n"
                    pr_description += "\n"

            # Add manual testing steps - use AI to generate specific, actionable steps
            pr_description += "## Manual Testing Steps\n"

            # Check if there's a predefined test plan
            test_plan = plan.get("test_plan", "")
            if test_plan:
                pr_description += f"{test_plan}\n"
            else:
                # Use AI to generate specific testing steps based on what was implemented
                testing_steps = await self._generate_testing_steps(context, steps)
                pr_description += testing_steps

            # Generate PR title
            pr_title = f"{context.work_item_title} (Work Item #{context.work_item_id})"

            print(f"[{self.name}] PR Title: {pr_title}")
            print(f"[{self.name}] Source: refs/heads/{context.branch_name}")
            print(f"[{self.name}] Target: refs/heads/main")
            print(f"[{self.name}] Work Item: {context.work_item_id}")

            # Build parameters for PR creation
            pr_params = {
                "title": pr_title,
                "description": pr_description,
                "sourceRefName": f"refs/heads/{context.branch_name}",
                "targetRefName": "refs/heads/main",  # or master
                "workItemRefs": [int(context.work_item_id)]
            }

            # Add repository ID if available
            if self.repository_id:
                pr_params["repositoryId"] = self.repository_id

            # Call Azure DevOps MCP to create PR
            result = await self.mcp_manager.call_tool(
                "azure_devops",
                "create_pull_request",
                pr_params
            )

            # Suppress verbose MCP output - just log success/failure below

            if "result" in result:
                # Parse PR response - MCP returns data in content array
                mcp_result = result["result"]

                # Check if result has content array (MCP format)
                if "content" in mcp_result and isinstance(mcp_result["content"], list):
                    if len(mcp_result["content"]) > 0:
                        content_item = mcp_result["content"][0]
                        if content_item.get("type") == "text":
                            text_content = content_item["text"]

                            # Check if it's an error message
                            if text_content.startswith("Error:"):
                                error_msg = text_content.replace("Error: ", "")
                                self.log(context, "PR creation failed", error_msg, False)
                                context.add_error(f"PR creation failed: {error_msg}")
                                return False

                            # Parse JSON from text content
                            import json
                            try:
                                pr_data = json.loads(text_content)
                            except json.JSONDecodeError as e:
                                self.log(context, "Failed to parse PR response", str(e), False)
                                context.add_error(f"Failed to parse PR response: {e}")
                                return False
                        else:
                            pr_data = mcp_result
                    else:
                        pr_data = mcp_result
                else:
                    # Direct result format
                    pr_data = mcp_result

                pr_id = pr_data.get("pullRequestId")
                pr_url = pr_data.get("url", "")

                # Validate that PR was actually created
                if not pr_id:
                    self.log(context, "PR creation failed", "No PR ID returned", False)
                    context.add_error("PR creation failed: No PR ID in response")
                    return False

                context.pr_id = str(pr_id)
                context.pr_url = pr_url

                self.log(context, "Pull request created",
                        f"PR #{context.pr_id}", True)

                print(f"\n{'='*60}")
                print("PULL REQUEST CREATED")
                print('='*60)
                print(f"PR ID: {context.pr_id}")
                print(f"Title: {pr_title}")
                print(f"Branch: {context.branch_name} → main")
                print(f"URL: {context.pr_url}")
                print('='*60 + '\n')

                return True
            else:
                error = result.get("error", "Unknown error")
                self.log(context, "PR creation failed", str(error), False)
                context.add_error(f"PR creation failed: {error}")
                return False
            
        except Exception as e:
            self.log(context, "Failed to create PR", str(e), False)
            context.add_error(f"PR creation failed: {e}")
            return False
    
    def get_current_branch(self) -> str:
        """Get the current branch name"""
        if not self.repo:
            self.initialize_repo()
        
        if self.repo:
            return self.repo.active_branch.name
        return "unknown"
    
    def get_repo_status(self) -> Dict[str, Any]:
        """Get repository status"""
        if not self.repo:
            self.initialize_repo()
        
        if not self.repo:
            return {"error": "Repository not initialized"}
        
        return {
            "branch": self.repo.active_branch.name,
            "is_dirty": self.repo.is_dirty(),
            "untracked_files": self.repo.untracked_files,
            "changed_files": [item.a_path for item in self.repo.index.diff(None)]
        }
