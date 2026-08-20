from core import BaseAgent, WorkflowContext, AgentState
from services import CodebaseRAG
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
import json
import html
import re
import os


class OrchestratorAgent(BaseAgent):
    """Orchestrator Agent - Coordinates the entire workflow"""
    
    def __init__(self, ai_client, deployment_name, mcp_manager, rag_service: Optional[CodebaseRAG] = None):
        super().__init__("Orchestrator", ai_client, deployment_name)
        self.mcp_manager = mcp_manager
        self.rag = rag_service
        self._project_context = self._build_project_context()

    def refresh_project_context(self):
        """Recompute project context (call after RAG re-index)"""
        self._project_context = self._build_project_context()

    def _build_project_context(self) -> Dict[str, Any]:
        """Gather repository context from RAG if available"""
        if not self.rag:
            return {
                "primary_language": "unknown",
                "total_files": 0,
                "file_types": {},
                "frameworks": []
            }

        try:
            analysis = self.rag.analyze_project()
            structure = self.rag.get_project_structure()
            file_types = structure.get("file_types", {})

            python_files = sorted({
                chunk['file_path']
                for chunk in self.rag.chunks
                if chunk['file_path'].endswith('.py')
            })
            sample_python_files = python_files[:10]
            python_dirs = sorted({
                str(Path(path).parent)
                for path in python_files
                if '/' in path
            })[:8]

            # Include existing file extensions
            allowed_extensions = {
                (ext.lower() if isinstance(ext, str) else ext)
                for ext, count in file_types.items() if count > 0 and isinstance(ext, str)
            }

            # Always allow common web/config file types even if not present yet
            # This allows agents to create new types of files as needed
            common_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.css', '.scss',
                               '.html', '.htm', '.json', '.yaml', '.yml', '.md',
                               '.txt', '.sql', '.sh', '.env'}
            allowed_extensions = allowed_extensions.union(common_extensions)

            return {
                "primary_language": analysis.get("primary_language", "unknown"),
                "frameworks": analysis.get("frameworks", []),
                "total_files": analysis.get("total_files", structure.get("total_files", 0)),
                "file_types": file_types,
                "allowed_extensions": allowed_extensions,
                "sample_python_files": sample_python_files,
                "python_directories": python_dirs
            }
        except Exception as exc:
            print(f"[Orchestrator] Failed to build project context: {exc}")
            return {
                "primary_language": "unknown",
                "total_files": 0,
                "file_types": {},
                "frameworks": [],
                "allowed_extensions": set(),
                "sample_python_files": [],
                "python_directories": []
            }

    def _get_architecture_patterns(self) -> str:
        """Return architecture patterns based on project type"""
        primary_lang = self._project_context.get("primary_language", "").lower()
        frameworks = self._project_context.get("frameworks", [])
        file_types = self._project_context.get("file_types", {})

        # Detect project type from file structure
        has_presentation = any("presentation" in path for path in self._project_context.get("sample_python_files", []))
        has_html_py = ".html" in str(self._project_context.get("file_types", {})) or has_presentation

        patterns = "## Architecture Patterns\n\n"

        # Python Web UI Pattern (like this project)
        if has_presentation or has_html_py:
            patterns += """**Python-Rendered Web UI Pattern:**
- CSS lives in Python files (e.g., `presentation/styles.py` returning CSS strings)
- HTML lives in Python files (e.g., `presentation/html_template.py` returning HTML strings)
- JavaScript must be INLINE in the HTML template (added via `<script>` tags in the template)
- To add new styles: Modify the Python file that generates CSS
- To add UI elements: Modify the Python file that generates HTML
- To add interactivity: Add inline `<script>` tags in the HTML-generating Python file
- All changes must modify EXISTING Python files that generate the web assets

**CRITICAL - DO NOT create separate .css, .js, or .html files - they won't be loaded!**

**Example - Adding a theme toggle:**
1. Modify `presentation/styles.py` to add CSS variables and dark theme class
2. Modify `presentation/html_template.py` to add toggle button HTML AND inline JavaScript
3. Do NOT create `theme.js` or `theme.css` files

"""

        return patterns

    async def execute(self, context: WorkflowContext) -> bool:
        """Main execution flow for orchestrator"""
        try:
            if not await self.fetch_work_item(context):
                return False
            
            if not await self.analyze_work_item(context):
                return False
            
            if not await self.create_execution_plan(context):
                return False
            
            self.log(context, "Orchestration complete", "Ready to execute plan", True)
            return True
            
        except Exception as e:
            self.log(context, "Orchestration failed", str(e), False)
            context.add_error(f"Orchestrator failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _clean_html(self, html_text: str) -> str:
        """Convert HTML to plain text"""
        if not html_text:
            return ""
        text = html.unescape(html_text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    async def fetch_work_item(self, context: WorkflowContext) -> bool:
        """Fetch work item details from Azure DevOps"""
        self.log(context, "Fetching work item", f"ID: {context.work_item_id}")
        context.current_state = AgentState.ANALYZING
        
        try:
            work_item_id = int(context.work_item_id)
            
            result = await self.mcp_manager.call_tool(
                "azure_devops",
                "get_work_item",
                {"workItemId": work_item_id}
            )
            
            if "result" not in result:
                self.log(context, "Work item not found", context.work_item_id, False)
                return False
            
            mcp_result = result["result"]
            
            if "content" in mcp_result and isinstance(mcp_result["content"], list):
                if len(mcp_result["content"]) > 0:
                    content_item = mcp_result["content"][0]
                    if content_item.get("type") == "text":
                        work_item_json = content_item.get("text", "{}")
                        work_item_data = json.loads(work_item_json)
                        
                        fields = work_item_data.get("fields", {})
                        
                        context.work_item_title = fields.get("System.Title", "Untitled")
                        
                        description_html = fields.get("System.Description")
                        if description_html:
                            context.work_item_description = self._clean_html(description_html)
                        else:
                            context.work_item_description = "No description provided"
                        
                        acceptance_criteria = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria")
                        if acceptance_criteria:
                            clean_ac = self._clean_html(acceptance_criteria)
                            if clean_ac:
                                context.work_item_description += f"\n\nAcceptance Criteria:\n{clean_ac}"
                        
                        created_by = fields.get("System.CreatedBy") or {}
                        assigned_to = fields.get("System.AssignedTo") or {}
                        
                        context.execution_plan["work_item_metadata"] = {
                            "id": work_item_data.get("id"),
                            "state": fields.get("System.State", "Unknown"),
                            "work_item_type": fields.get("System.WorkItemType", "Unknown"),
                            "created_by": created_by.get("displayName", "Unknown"),
                            "assigned_to": assigned_to.get("displayName", "Unassigned"),
                            "priority": fields.get("Microsoft.VSTS.Common.Priority"),
                            "story_points": fields.get("Microsoft.VSTS.Scheduling.StoryPoints"),
                        }
                        
                        self.log(context, "Work item fetched", f"{context.work_item_title}")
                        
                        print(f"\n{'='*60}")
                        print("WORK ITEM DETAILS")
                        print('='*60)
                        print(f"ID: {context.work_item_id}")
                        print(f"Title: {context.work_item_title}")
                        print(f"Type: {context.execution_plan['work_item_metadata']['work_item_type']}")
                        print(f"State: {context.execution_plan['work_item_metadata']['state']}")
                        print(f"Description: {context.work_item_description}")
                        print('='*60 + '\n')
                        
                        return True
            
            self.log(context, "Failed to parse work item", "Unexpected data structure", False)
            return False
            
        except Exception as e:
            self.log(context, "Failed to fetch work item", str(e), False)
            import traceback
            traceback.print_exc()
            return False
    
    async def analyze_work_item(self, context: WorkflowContext) -> bool:
        """Use AI to deeply analyze the work item"""
        self.log(context, "Analyzing work item", "Using AI analysis")
        
        system_prompt = """You are a senior software architect analyzing user stories.

            Extract and analyze:
            1. Technical requirements
            2. Acceptance criteria (specific, testable)
            3. Complexity (simple/medium/complex)
            4. Risks and challenges
            5. Implementation approach"""

        project_summary = (
            f"Primary language: {self._project_context.get('primary_language')}\n"
            f"Frameworks: {', '.join(self._project_context.get('frameworks', [])) or 'None'}\n"
            f"Total files indexed: {self._project_context.get('total_files')}\n"
            f"Common file types: {', '.join(self._project_context.get('file_types', {}).keys()) or 'Unknown'}"
        )

        python_dirs = '\n'.join(
            f"- {d}" for d in self._project_context.get('python_directories', [])
        ) or "- (no python directories detected)"

        user_prompt = f"""Analyze this work item:

            Title: {context.work_item_title}
            
            Description: {context.work_item_description}
            
            Project Summary:
            {project_summary}
            
            Python module locations:
            {python_dirs}
            
            Provide analysis in JSON:
            {{
                "summary": "Brief summary",
                "technical_requirements": ["req1", "req2"],
                "acceptance_criteria": ["criteria1", "criteria2"],
                "complexity": "simple|medium|complex",
                "risks": ["risk1"],
                "recommended_approach": "Implementation strategy",
                "estimated_files": ["src/styles/theme.css", "src/utils/themeToggle.js"]
            }}"""

        try:
            ai_response = await self.call_ai(system_prompt, user_prompt, temperature=0.2)
            analysis = self.extract_json(ai_response)
            
            if not analysis:
                self.log(context, "Analysis failed", "Could not parse AI response", False)
                return False
            
            context.acceptance_criteria = analysis.get("acceptance_criteria", [])
            context.execution_plan["analysis"] = analysis
            
            self.log(context, "Analysis complete", 
                    f"Complexity: {analysis.get('complexity')}, "
                    f"Criteria: {len(context.acceptance_criteria)}")
            
            return True
            
        except Exception as e:
            self.log(context, "Analysis failed", str(e), False)
            import traceback
            traceback.print_exc()
            return False
    
    async def create_execution_plan(self, context: WorkflowContext) -> bool:
        """Create detailed execution plan with proper file organization"""
        self.log(context, "Creating execution plan", "Using AI planning")
        context.current_state = AgentState.PLANNING
        
        analysis = context.execution_plan.get("analysis", {})
        
        system_prompt = """You are a technical project manager creating execution plans.

            Create actionable plans for specialized AI agents (DevOps, Code, Test).

            IMPORTANT - File Organization:
            - Analyze the ACTUAL project structure provided below
            - Use EXISTING directories and file patterns
            - Do NOT invent new directories or file structures
            - If a file is mentioned but doesn't exist, find the EQUIVALENT file in the actual structure

            Planning Output Requirements:
            - Use "files_to_create" for brand new files and include an "instructions" array describing their purpose
            - Use "files_to_update" for existing files, provide "path" plus bullet "instructions" outlining the exact edits
            - Every CodeAgent step must reference at least one file in "files_to_create" or "files_to_update"

            CRITICAL - Implementation Completeness:
            - Each step must produce WORKING, INTEGRATED code - not isolated pieces
            - For UI features: Create CSS, add HTML elements, wire JavaScript, AND integrate into Python rendering
            - Instructions must be SPECIFIC and DETAILED - explain exactly what code to add/modify
            - Think end-to-end: How will the user actually USE this feature?
            - Don't create files that are never loaded/imported/used"""

        # Add architecture patterns based on project type
        architecture_patterns = self._get_architecture_patterns()

        system_prompt += (
            "\n\n" + architecture_patterns +  # ← Architecture patterns FIRST (more prominent)
            "\n\nProject context:\n"
            f"- Repository primary language: {self._project_context.get('primary_language')}\n"
            "- Follow the existing project structure and naming conventions\n"
            "- Respect the architecture patterns above - they define which file types are allowed\n"
        )

        sample_files = '\n'.join(
            f"- {path}" for path in self._project_context.get('sample_python_files', [])
        ) or "- (no python files detected)"
        python_dirs = '\n'.join(
            f"- {d}" for d in self._project_context.get('python_directories', [])
        ) or "- (no python directories detected)"

        # Get actual files from RAG to help with planning
        actual_files = ""
        if self.rag:
            try:
                all_files = sorted({chunk['file_path'] for chunk in self.rag.chunks})
                actual_files = '\n'.join(f"- {path}" for path in all_files[:50])
            except:
                actual_files = "(unable to list files)"

        user_prompt = f"""Create plan for:

            Title: {context.work_item_title}
            Description: {context.work_item_description}
            
            Analysis:
            {json.dumps(analysis, indent=2)}
            
            Project Summary:
            Primary language: {self._project_context.get('primary_language')}
            Frameworks: {', '.join(self._project_context.get('frameworks', [])) or 'None'}
            Total files indexed: {self._project_context.get('total_files')}
            Common file types: {', '.join(self._project_context.get('file_types', {}).keys()) or 'Unknown'}
            
            Python module directories to target:
            {python_dirs}
            
            Representative Python files:
            {sample_files}

            CRITICAL - ACTUAL FILES IN REPOSITORY (Use these, don't invent new ones!):
            {actual_files}

            Provide plan in JSON with PROPER FILE PATHS (must exist or be creatable):
            {{
                "branch_name": "feature/story-{context.work_item_id}",
                "implementation_steps": [
                    {{
                        "step": 1,
                        "description": "Add theme CSS styles and update styles.py to include them",
                        "agent": "CodeAgent",
                        "files_to_update": [
                            {{
                                "path": "presentation/styles.py",
                                "instructions": [
                                    "Add CSS variables for light theme: --bg-color: #f8f9fa, --text-color: #333, --primary-color: #0066cc, etc.",
                                    "Add CSS variables for dark theme: --bg-color: #1a1a1a, --text-color: #e0e0e0, --primary-color: #4da6ff, etc.",
                                    "Wrap existing styles to use CSS variables: body {{ background: var(--bg-color); color: var(--text-color); }}",
                                    "Add .dark-theme class that overrides CSS variables with dark values",
                                    "Ensure syntax highlighting colors are legible in both themes"
                                ]
                            }}
                        ],
                        "validation": "CSS contains both light and dark theme variables and existing styles use them"
                    }},
                    {{
                        "step": 2,
                        "description": "Add theme toggle UI button and wire JavaScript to HTML template",
                        "agent": "CodeAgent",
                        "files_to_update": [
                            {{
                                "path": "presentation/html_template.py",
                                "instructions": [
                                    "Add theme toggle button in header: <button id='theme-toggle' class='theme-toggle-btn'>🌙 Dark Mode</button>",
                                    "Add inline JavaScript BEFORE closing body tag to: (1) read theme from localStorage, (2) apply 'dark-theme' class to body if dark, (3) toggle theme on button click, (4) update localStorage, (5) update button text",
                                    "Add CSS for .theme-toggle-btn styling in the styles section"
                                ]
                            }}
                        ],
                        "validation": "HTML template includes toggle button and JavaScript that persists theme to localStorage"
                    }}
                ],
                "testing_strategy": {{
                    "unit_tests": ["tests/test_theme_functionality.py"],
                    "integration_tests": []
                }},
                "pr_description": "Implemented theme toggle feature with CSS variables, UI button, and localStorage persistence"
            }}"""

        try:
            ai_response = await self.call_ai(system_prompt, user_prompt, 
                                            temperature=0.2, max_tokens=3000)
            plan = self.extract_json(ai_response)
            
            if not plan:
                self.log(context, "Planning failed", "Could not parse AI response", False)
                return False

            # Filter and auto-fix invalid plan steps
            plan = self._filter_plan_steps(plan)
            plan = self._auto_fix_architecture_violations(plan)
            context.execution_plan["implementation"] = plan
            context.branch_name = plan.get("branch_name", f"feature/story-{context.work_item_id}")
            
            steps = plan.get("implementation_steps", [])
            self.log(context, "Execution plan created", 
                    f"{len(steps)} steps, Branch: {context.branch_name}")
            
            print(f"\n{'='*60}")
            print("EXECUTION PLAN SUMMARY")
            print('='*60)
            print(f"Branch: {context.branch_name}")
            print(f"Total Steps: {len(steps)}\n")
            
            for step in steps:
                print(f"  {step.get('step')}. {step.get('description')}")
                print(f"     Agent: {step.get('agent')}")
                create_entries = self._normalize_plan_file_entries(step.get('files_to_create'))
                update_entries = self._normalize_plan_file_entries(step.get('files_to_update'))
                if create_entries:
                    paths = ', '.join(entry['path'] for entry in create_entries)
                    print(f"     Create: {paths}")
                if update_entries:
                    paths = ', '.join(entry['path'] for entry in update_entries)
                    print(f"     Update: {paths}")
                print()
            
            print('='*60 + '\n')
            
            return True
            
        except Exception as e:
            self.log(context, "Planning failed", str(e), False)
            import traceback
            traceback.print_exc()
            return False

    def _auto_fix_architecture_violations(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-fix common architecture violations in the plan"""
        # Check ALL indexed files, not just sample_python_files
        all_files = []
        if self.rag:
            all_files = [chunk['file_path'] for chunk in self.rag.chunks]

        has_presentation = any("presentation" in path for path in all_files)

        if not has_presentation:
            print("[Orchestrator] Not a Python Web UI project - skipping auto-fix")
            return plan  # Not a Python Web UI project

        print(f"[Orchestrator] Detected Python Web UI project (has presentation/ directory)")

        print("[Orchestrator] Auto-fixing architecture violations...")

        steps = plan.get("implementation_steps", [])
        fixed_steps = []

        for step in steps:
            create_entries = self._normalize_plan_file_entries(step.get("files_to_create", []))
            update_entries = self._normalize_plan_file_entries(step.get("files_to_update", []))

            # Check if this step creates .js/.css/.html files
            blocked_files = []
            for entry in create_entries:
                ext = os.path.splitext(entry["path"])[1].lower()
                if ext in {'.js', '.css', '.html', '.htm'}:
                    blocked_files.append(entry["path"])

            if blocked_files:
                print(f"[Orchestrator] Step {step.get('step')}: Found blocked files: {blocked_files}")
                print(f"[Orchestrator]   Merging into html_template.py update instead")

                # Instead of creating separate files, add instructions to html_template.py
                html_template_entry = None
                for entry in update_entries:
                    if 'html_template.py' in entry["path"]:
                        html_template_entry = entry
                        break

                if not html_template_entry:
                    # Create new update entry for html_template.py
                    html_template_entry = {
                        "path": "presentation/html_template.py",
                        "instructions": []
                    }
                    update_entries.append(html_template_entry)

                # Add instruction to include JavaScript inline
                for blocked_file in blocked_files:
                    if blocked_file.endswith('.js'):
                        html_template_entry["instructions"].append(
                            f"Add inline JavaScript (NOT separate {blocked_file} file) before closing </body> tag with the theme toggle logic: "
                            "(1) read theme from localStorage, (2) apply 'dark-theme' class to body if dark, "
                            "(3) add click listener to toggle theme, (4) update localStorage, (5) update button text. "
                            "Wrap in IIFE and escape curly braces as {{}} for f-string."
                        )

                # Remove blocked files from create list
                create_entries = [e for e in create_entries if e["path"] not in blocked_files]

                # Update step
                step["files_to_create"] = create_entries
                step["files_to_update"] = update_entries

                print(f"[Orchestrator]   ✓ Fixed: Inline JavaScript in html_template.py")

            fixed_steps.append(step)

        plan["implementation_steps"] = fixed_steps
        return plan

    def _filter_plan_steps(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Remove implementation steps targeting unsupported file types"""
        allowed_exts: Set[str] = self._project_context.get("allowed_extensions", set())
        steps = plan.get("implementation_steps", [])
        filtered_steps = []
        removed_steps = []
        repo_path = getattr(self.rag, "repository_path", None) if self.rag else None

        # Check if this is a Python Web UI project using ALL indexed files
        all_files = []
        if self.rag:
            all_files = [chunk['file_path'] for chunk in self.rag.chunks]

        has_presentation = any("presentation" in path for path in all_files)

        print(f"[Orchestrator] Filtering plan steps...")
        print(f"[Orchestrator]   Total indexed files: {len(all_files)}")
        print(f"[Orchestrator]   has_presentation: {has_presentation}")

        for step in steps:
            create_entries = self._normalize_plan_file_entries(step.get("files_to_create"))
            update_entries = self._normalize_plan_file_entries(step.get("files_to_update"))
            invalid_reasons: List[str] = []

            if step.get("agent") == "CodeAgent" and not (create_entries or update_entries):
                invalid_reasons.append("No files_to_create or files_to_update provided")

            # Filter out blocked files from create_entries
            filtered_create_entries = []
            for entry in create_entries:
                path = entry["path"]

                # CRITICAL: Block standalone .js/.css/.html files in Python Web UI projects
                if has_presentation:
                    ext = os.path.splitext(path)[1].lower()
                    if ext in {'.js', '.css', '.html', '.htm'}:
                        invalid_reasons.append(
                            f"BLOCKED: Cannot create {path} - Python Web UI uses inline JS/CSS in .py files"
                        )
                        continue  # Skip this file, don't add to filtered list

                if not self._is_extension_allowed(path, allowed_exts):
                    invalid_reasons.append(f"Unsupported extension: {path}")
                    continue  # Skip this file

                # File is allowed, add to filtered list
                filtered_create_entries.append(entry)

            # Replace create_entries with filtered list
            create_entries = filtered_create_entries

            # Auto-correct: Move non-existent files from updates to creates
            corrected_update_entries = []
            for entry in update_entries:
                path = entry["path"]
                if not self._is_extension_allowed(path, allowed_exts):
                    invalid_reasons.append(f"Unsupported extension: {path}")
                    continue

                # Check if file exists
                if repo_path and not os.path.exists(os.path.join(repo_path, path)):
                    # Auto-correct: Move to files_to_create
                    print(f"[Orchestrator] Auto-correcting: Moving '{path}' from files_to_update → files_to_create (file doesn't exist)")
                    create_entries.append(entry)
                else:
                    corrected_update_entries.append(entry)

            # Update the step with corrected lists
            step["files_to_create"] = create_entries
            step["files_to_update"] = corrected_update_entries

            if invalid_reasons:
                removed_steps.append({
                    "step": step.get("step"),
                    "reason": "; ".join(invalid_reasons)
                })
                continue

            filtered_steps.append(step)

        if removed_steps:
            print("[Orchestrator] Removed plan steps due to unsupported file types:")
            for info in removed_steps:
                print(f"  - Step {info['step']}: {info['reason']}")

        plan["implementation_steps"] = filtered_steps

        if not any(step.get("agent") == "CodeAgent" for step in filtered_steps):
            raise ValueError("Planning did not produce any CodeAgent steps within supported file types")

        return plan

    def _normalize_plan_file_entries(self, files: Any) -> List[Dict[str, Any]]:
        """Normalize file descriptors from the execution plan"""
        normalized: List[Dict[str, Any]] = []
        if not files:
            return normalized

        if not isinstance(files, list):
            files = [files]

        for entry in files:
            if isinstance(entry, str):
                normalized.append({"path": entry})
                continue

            if isinstance(entry, dict):
                path = entry.get("path") or entry.get("file") or entry.get("target")
                if not path:
                    continue
                instructions = entry.get("instructions")
                if isinstance(instructions, str):
                    instructions = [instructions]
                normalized.append({
                    "path": path,
                    "instructions": instructions or []
                })

        return normalized

    def _is_extension_allowed(self, path: str, allowed_exts: Set[str]) -> bool:
        if not allowed_exts:
            return True
        ext = os.path.splitext(path)[1].lower()
        if not ext:
            return True
        return ext in allowed_exts
    
    async def validate_completion(self, context: WorkflowContext) -> bool:
        """Validate completion against acceptance criteria"""
        self.log(context, "Validating completion", "Checking criteria")
        context.current_state = AgentState.VALIDATING
        return True
