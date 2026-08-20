from core import BaseAgent, WorkflowContext, AgentState
from typing import Dict, Any, List, Optional
import os
import subprocess
import re

class TestAgent(BaseAgent):
    """
    Test Agent - Writes and executes tests
    
    Responsibilities:
    1. Generate unit tests for implemented code
    2. Generate integration tests
    3. Run test suites
    4. Report test results
    """
    
    def __init__(self, ai_client, deployment_name, mcp_manager, rag_service, repository_path: str):
        super().__init__("TestAgent", ai_client, deployment_name)
        self.mcp_manager = mcp_manager
        self.rag = rag_service
        self.repository_path = repository_path
    
    async def execute(self, context: WorkflowContext) -> bool:
        """Execute test generation from execution plan"""
        plan = context.execution_plan.get("implementation", {})
        steps = plan.get("implementation_steps", [])
        
        if not steps:
            return False
        
        for step in steps:
            if step.get("agent") == "TestAgent":
                success = await self.execute_step(context, step)
                if not success:
                    return False
        
        return True
    
    async def execute_step(self, context: WorkflowContext, step: Dict) -> bool:
        """Execute a single test step"""
        step_num = step.get("step")
        description = step.get("description")
        file_entries = self._normalize_file_entries(step.get("files_to_create"))

        self.log(context, f"Executing step {step_num}", description)
        context.current_state = AgentState.TESTING

        if not file_entries:
            self.log(context, "No test files", "Step lacks files_to_create entries", False)
            return False

        for entry in file_entries:
            # Fix test file paths - ensure they're in tests/ at project root for pytest discovery
            test_path = self._fix_test_path(entry["path"])
            if test_path != entry["path"]:
                print(f"  ⚠️  Corrected test path: {entry['path']} → {test_path}")
                entry["path"] = test_path

            # Clean up conflicting old test files before creating new ones
            removed = await self._cleanup_old_test_files(context, test_path)
            if removed:
                print(f"  ✓ Removed conflicting test files: {', '.join(removed)}")

            instructions = entry.get("instructions") or [description]
            success = await self.create_test_file(
                context,
                entry["path"],
                description,
                instructions
            )
            if not success:
                return False

        return True

    def _fix_test_path(self, original_path: str) -> str:
        """Fix test file paths to ensure pytest can discover them"""
        # Pytest expects tests in tests/ directory at project root
        # Not in subdirectories like presentation/tests/ or src/tests/

        # If path is already tests/..., keep it
        if original_path.startswith('tests/'):
            return original_path

        # If path is in a subdirectory like presentation/tests/...
        # Move it to tests/ at root
        if '/tests/' in original_path:
            # Extract just the filename
            filename = original_path.split('/')[-1]
            return f"tests/{filename}"

        # If path doesn't include 'tests' at all, prepend it
        if 'test_' in original_path:
            filename = original_path.split('/')[-1]
            return f"tests/{filename}"

        return original_path

    async def create_test_file(self, context: WorkflowContext,
                              file_path: str, description: str,
                              instructions: List[str]) -> bool:
        """Create a test file for the implemented code"""
        self.log(context, "Creating test file", file_path)

        # Get implemented files to test - show substantial content for better test generation
        implemented_files = "\n\n".join([
            f"--- {path} ---\n{content[:2000]}" + ("..." if len(content) > 2000 else "")
            for path, content in context.implementation_files.items()
        ])

        instructions_text = '\n'.join(f"- {item}" for item in instructions)

        # Detect project language and framework using RAG
        project_context = await self._detect_project_context(context)

        system_prompt = f"""You are a QA engineer writing comprehensive unit tests for a {project_context['language']} project.

CRITICAL REQUIREMENTS:
1. This is a {project_context['language']} project - use {project_context['test_framework']} for testing
2. NEVER import JavaScript libraries like jsdom, jest, or mocha
3. NEVER use browser-based testing approaches for Python backend code
4. NEVER create mock implementations or fake functions in the test file
5. ALWAYS import and test the ACTUAL code from the project modules

For Python web UI code (HTML/CSS/JS embedded in Python strings):
   - Import the REAL Python functions from the project (e.g., from presentation.styles import get_styles)
   - Test that these functions return strings containing expected CSS/HTML/JS
   - Check for presence of specific classes, IDs, CSS variables, etc.
   - Mock only EXTERNAL dependencies (databases, APIs), never the code being tested
   - Do NOT try to execute JavaScript - just verify it's present in the string

EXAMPLE - CORRECT approach:
```python
from presentation.styles import get_styles
from presentation.html_template import get_html_template

def test_dark_theme_css_variables():
    css = get_styles()
    assert '--bg-color' in css
    assert '.dark-theme' in css
```

EXAMPLE - WRONG approach (DO NOT DO THIS):
```python
# WRONG - Creating fake implementation
def get_styles():
    return "fake css"

def test_dark_theme():
    css = get_styles()  # Testing fake code, not real code!
```

Write tests that:
1. Import and test ACTUAL project code (never mock the code under test)
2. Cover all major functionality
3. Test edge cases and error conditions
4. Are clear and maintainable
5. Use {project_context['test_framework']} as the testing framework
6. Include setup/teardown as needed
7. Only import modules that exist in {project_context['language']} ecosystem

Write COMPLETE, runnable tests that can be collected and executed by {project_context['test_framework']}."""

        # Extract the module being tested from instructions or description
        # For incremental TDD, implementation may not exist yet, so we infer from description
        modules_to_test = []

        # First, check existing implementation files
        if implemented_files:
            for path, content in context.implementation_files.items():
                if path.endswith('.py'):
                    # Convert path to module import (e.g., presentation/styles.py -> presentation.styles)
                    module = path.replace('/', '.').replace('.py', '')
                    modules_to_test.append(module)

        # If no implementation yet, infer from test file path or description
        if not modules_to_test:
            # Extract module path from test file name
            # e.g., tests/test_styles.py -> presentation/styles.py
            test_file_name = file_path.split('/')[-1]  # test_styles.py
            if test_file_name.startswith('test_'):
                module_name = test_file_name.replace('test_', '').replace('.py', '')  # styles
                # Look for this module in common locations
                possible_paths = [
                    f"presentation/{module_name}",
                    f"src/{module_name}",
                    f"{module_name}"
                ]
                modules_to_test = possible_paths

        modules_hint = ""
        if modules_to_test:
            modules_hint = f"\n\nModules to test (import these in your test file):\n" + "\n".join(f"- from {m} import *  (or import specific functions)" for m in modules_to_test)

        user_prompt = f"""Create unit tests for this {project_context['language']} implementation:
            Test File: {file_path}
            Purpose: {description}
            
            Project Context:
            - Language: {project_context['language']}
            - Framework: {project_context['test_framework']}
            - Dependencies: {', '.join(project_context['dependencies'][:10])}
            
            Implementation Notes:
            {instructions_text}
            
            Implemented Code (these are the ACTUAL functions you must import and test):
            {implemented_files}
            {modules_hint}
            
            Work Item: {context.work_item_title}
            Acceptance Criteria:
            {chr(10).join(f'- {c}' for c in context.acceptance_criteria[:5])}
            
            Generate COMPLETE test file using {project_context['test_framework']}. Include:
            - Import statements for the ACTUAL project modules (see "Modules to test" above)
            - DO NOT create mock/fake implementations of the code being tested
            - Test setup/teardown if needed
            - Comprehensive test cases that call the REAL functions
            - Clear assertions checking the return values
            - Comments explaining what's being tested
            
            CRITICAL - You MUST import the real code:
            - If testing presentation/styles.py, use: from presentation.styles import get_styles
            - If testing presentation/html_template.py, use: from presentation.html_template import get_html_template
            - Then call these functions in your tests and assert on their return values
            
            IMPORTANT:
            - If testing HTML/CSS/JS generation code, test the Python functions that produce the strings
            - Do NOT import browser testing libraries
            - Do NOT try to execute JavaScript in Python tests
            - Do NOT create fake implementations in the test file
            
            Respond with ONLY the test file content."""

        try:
            test_content = await self.call_ai(system_prompt, user_prompt,
                                             temperature=0.2, max_tokens=2500)

            if "```" in test_content:
                lines = test_content.split('\n')
                in_code_block = False
                clean_lines = []

                for line in lines:
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block:
                        clean_lines.append(line)

                if clean_lines:
                    test_content = '\n'.join(clean_lines)

            # Validate test file can be imported (syntax check)
            validation_result = await self._validate_test_syntax(test_content, file_path, project_context)
            if not validation_result['valid']:
                print(f"⚠️  Generated test has issues: {validation_result['error']}")
                print(f"   Attempting to fix...")

                # Try to fix common issues
                test_content = await self._fix_test_issues(test_content, validation_result['error'], project_context)

                # Validate again
                validation_result = await self._validate_test_syntax(test_content, file_path, project_context)
                if not validation_result['valid']:
                    print(f"✗ Failed to generate valid test file: {validation_result['error']}")
                    self.log(context, "Test validation failed", validation_result['error'], False)
                    return False

            # Check and install test dependencies BEFORE writing file
            deps_ok = await self._check_and_install_test_dependencies(test_content, context)
            if not deps_ok:
                print(f"✗ Could not satisfy test dependencies")
                self.log(context, "Dependency installation failed", file_path, False)
                return False

            # Write test file
            full_path = os.path.join(self.repository_path, file_path)
            target_dir = os.path.dirname(full_path) or self.repository_path
            os.makedirs(target_dir, exist_ok=True)

            # Ensure __init__.py exists in test directory for pytest discovery
            init_file = os.path.join(target_dir, '__init__.py')
            if not os.path.exists(init_file):
                with open(init_file, 'w') as f:
                    f.write('"""Test package"""\n')
                print(f"  ✓ Created {init_file} for pytest discovery")

            with open(full_path, 'w') as f:
                f.write(test_content)

            if os.path.exists(full_path):
                context.test_files.append(file_path)
                self.log(context, "Test file created", f"{file_path} ({len(test_content)} chars)")
                print(f"✓ Created: {full_path}")
                return True
            else:
                self.log(context, "Test creation failed", file_path, False)
                return False

        except Exception as e:
            print(f"✗ Error: {e}")
            self.log(context, "Error creating test", str(e), False)
            return False

    async def _detect_project_context(self, context: WorkflowContext) -> Dict[str, Any]:
        """Detect project language, framework, and dependencies using RAG"""
        try:
            # Query RAG for project info
            rag_query = "What programming language is this project? What testing framework does it use? List key dependencies."
            rag_results = self.rag.search(rag_query, n_results=5)

            # Build context from RAG results
            rag_context = "\n".join([
                f"{r.get('file_path', 'unknown')}: {r.get('content', '')[:200]}"
                for r in rag_results
            ])

            # Check for obvious markers
            language = "Python"  # Default
            test_framework = "pytest"  # Default
            dependencies = []

            # Look for requirements.txt or setup.py
            if os.path.exists(os.path.join(self.repository_path, "requirements.txt")):
                with open(os.path.join(self.repository_path, "requirements.txt"), 'r') as f:
                    deps_text = f.read()
                    dependencies = [line.split('==')[0].split('>=')[0].strip()
                                   for line in deps_text.split('\n')
                                   if line.strip() and not line.startswith('#')]

            # Check file extensions in implementation
            impl_files = list(context.implementation_files.keys())
            if impl_files:
                if any(f.endswith('.py') for f in impl_files):
                    language = "Python"
                    test_framework = "pytest"
                elif any(f.endswith('.js') or f.endswith('.ts') for f in impl_files):
                    language = "JavaScript"
                    test_framework = "jest"
                elif any(f.endswith('.go') for f in impl_files):
                    language = "Go"
                    test_framework = "testing"

            return {
                "language": language,
                "test_framework": test_framework,
                "dependencies": dependencies,
                "rag_context": rag_context
            }

        except Exception as e:
            print(f"⚠️  Could not detect project context: {e}")
            # Return safe defaults
            return {
                "language": "Python",
                "test_framework": "pytest",
                "dependencies": [],
                "rag_context": ""
            }

    async def _validate_test_syntax(self, test_content: str, file_path: str,
                                   project_context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate test file syntax and imports"""
        try:
            # Check for JavaScript imports in Python tests
            if project_context['language'] == 'Python':
                js_imports = ['jsdom', 'jest', 'mocha', 'chai', 'enzyme', 'react-testing-library']
                for js_import in js_imports:
                    if f"import {js_import}" in test_content or f"from {js_import}" in test_content:
                        return {
                            "valid": False,
                            "error": f"JavaScript library '{js_import}' imported in Python test"
                        }

            # Try to compile the Python code
            if project_context['language'] == 'Python':
                try:
                    compile(test_content, file_path, 'exec')
                except SyntaxError as se:
                    return {
                        "valid": False,
                        "error": f"Syntax error: {se}"
                    }

            return {"valid": True, "error": None}

        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def _fix_test_issues(self, test_content: str, error: str,
                               project_context: Dict[str, Any]) -> str:
        """Use AI to fix common test issues"""
        system_prompt = f"""You are a {project_context['language']} test expert fixing test code issues.

            Fix the test code to resolve the error while maintaining test coverage.
            
            Rules:
            1. Use only {project_context['language']} libraries and {project_context['test_framework']}
            2. Remove any JavaScript libraries (jsdom, jest, etc.)
            3. For Python web UI testing, test the Python functions that generate HTML strings
            4. Do NOT try to execute JavaScript in Python tests
            5. Keep the test logic and coverage the same, just fix the technical issues
            
            Respond with ONLY the fixed test code, no explanations."""

        user_prompt = f"""Fix this test code:

            Error: {error}
            
            Original Test:
            {test_content}
            
            Language: {project_context['language']}
            Framework: {project_context['test_framework']}
            
            Generate the corrected test code."""

        try:
            fixed_content = await self.call_ai(system_prompt, user_prompt,
                                              temperature=0.1, max_tokens=2500)

            # Extract code from markdown if present
            if "```" in fixed_content:
                lines = fixed_content.split('\n')
                in_code_block = False
                clean_lines = []

                for line in lines:
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block:
                        clean_lines.append(line)

                if clean_lines:
                    fixed_content = '\n'.join(clean_lines)

            return fixed_content

        except Exception as e:
            print(f"✗ Error fixing test: {e}")
            return test_content  # Return original if fix fails
    
    async def _check_and_install_test_dependencies(self, test_content: str, context: WorkflowContext) -> bool:
        """
        Extract imports from test code and ensure dependencies are installed.
        Returns True if all dependencies are satisfied.
        """
        # Extract import statements
        import_pattern = r'^\s*(?:from|import)\s+([\w.]+)'
        imports = set()
        for line in test_content.split('\n'):
            match = re.match(import_pattern, line)
            if match:
                # Extract package name (before first dot)
                package = match.group(1).split('.')[0]
                imports.add(package)

        # Filter out standard library modules
        stdlib_modules = {'os', 'sys', 're', 'json', 'typing', 'pathlib',
                         'subprocess', 'pytest', 'unittest', 'asyncio', 'time',
                         'datetime', 'collections', 'itertools', 'functools'}

        # Common project directory names that should always be treated as project modules
        # even if they don't exist (TDD scenario or test is incorrect)
        common_project_dirs = {'src', 'lib', 'app', 'core', 'presentation', 'services',
                               'utils', 'helpers', 'models', 'views', 'controllers',
                               'routes', 'api', 'database', 'config', 'tests', 'test',
                               'agents', 'backend', 'frontend', 'common', 'shared',
                               'components', 'modules', 'packages', 'internal'}

        # Dynamically detect project modules by checking if directories exist in repository
        # OR if they're being implemented as part of this work item (TDD scenario)
        project_modules = set()
        for package in imports:
            if package in stdlib_modules:
                continue

            # Check if this is a common project directory name
            if package in common_project_dirs:
                project_modules.add(package)
                print(f"  ℹ️  Recognized '{package}' as project module (common project directory)")
                continue

            # Check if this is a project module by looking for the directory or .py file
            potential_paths = [
                os.path.join(self.repository_path, package),  # directory (package)
                os.path.join(self.repository_path, f"{package}.py"),  # single file module
            ]

            # Check if module exists in filesystem
            if any(os.path.exists(p) for p in potential_paths):
                project_modules.add(package)
                continue

            # TDD scenario: Module being implemented in this work item (doesn't exist yet)
            # Check if this package name appears in the execution plan or implementation files
            plan = context.execution_plan.get("implementation", {})
            steps = plan.get("implementation_steps", [])

            # Check if package name appears in any planned file paths
            is_being_implemented = False
            for step in steps:
                # Check files_to_create
                files_to_create = step.get("files_to_create", [])
                if isinstance(files_to_create, list):
                    for file_entry in files_to_create:
                        if isinstance(file_entry, dict):
                            file_path = file_entry.get("path", "")
                        else:
                            file_path = str(file_entry)

                        # Check if package name is in the file path
                        if package in file_path or package.replace('_', '') in file_path:
                            is_being_implemented = True
                            break

                # Check files_to_update
                files_to_update = step.get("files_to_update", [])
                if isinstance(files_to_update, list):
                    for file_entry in files_to_update:
                        if isinstance(file_entry, dict):
                            file_path = file_entry.get("path", "")
                        else:
                            file_path = str(file_entry)

                        if package in file_path or package.replace('_', '') in file_path:
                            is_being_implemented = True
                            break

                if is_being_implemented:
                    break

            if is_being_implemented:
                project_modules.add(package)
                print(f"  ℹ️  Recognized '{package}' as project module (being implemented)")

        third_party = imports - stdlib_modules - project_modules

        if not third_party:
            return True  # No third-party dependencies

        print(f"  Detected test dependencies: {', '.join(sorted(third_party))}")

        # Check which ones are missing
        missing = []
        for package in third_party:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)

        if not missing:
            print(f"  ✓ All dependencies already installed")
            return True

        print(f"  ⚠️  Missing dependencies: {', '.join(missing)}")
        print(f"  Installing...")

        # Map common import names to package names
        package_map = {
            'bs4': 'beautifulsoup4',
            'PIL': 'pillow',
            'cv2': 'opencv-python',
            'yaml': 'pyyaml',
            'dotenv': 'python-dotenv'
        }

        # Install missing packages
        for package in missing:
            pip_package = package_map.get(package, package)

            try:
                result = subprocess.run(
                    ['pip', 'install', pip_package],
                    cwd=self.repository_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    print(f"  ✓ Installed {pip_package}")

                    # Update requirements.txt
                    await self._update_requirements_txt(pip_package)
                else:
                    print(f"  ✗ Failed to install {pip_package}: {result.stderr[:200]}")
                    return False

            except Exception as e:
                print(f"  ✗ Error installing {pip_package}: {e}")
                return False

        return True

    async def _update_requirements_txt(self, package: str):
        """Add package to requirements.txt if not already present"""
        req_file = os.path.join(self.repository_path, 'requirements.txt')

        # Read existing requirements
        if os.path.exists(req_file):
            with open(req_file, 'r') as f:
                existing = f.read()
        else:
            existing = ""

        # Check if package already listed (exact match or as dependency)
        if package in existing or f"{package}==" in existing or f"{package}>=" in existing:
            return

        # Append package
        with open(req_file, 'a') as f:
            if existing and not existing.endswith('\n'):
                f.write('\n')
            f.write(f"{package}\n")

        print(f"  ✓ Added {package} to requirements.txt")

    async def _cleanup_old_test_files(self, context: WorkflowContext, new_test_path: str) -> List[str]:
        """
        Remove old/conflicting test files that may cause import errors.
        Returns list of removed files.
        """
        test_dir = os.path.join(self.repository_path, 'tests')
        if not os.path.exists(test_dir):
            return []

        # Get the feature name from new test path
        # e.g., tests/test_theme_functionality.py -> theme
        new_test_name = os.path.basename(new_test_path)
        feature_keywords = set(new_test_name.replace('test_', '').replace('.py', '').split('_'))

        removed = []
        for filename in os.listdir(test_dir):
            if not filename.startswith('test_') or not filename.endswith('.py'):
                continue

            if filename == os.path.basename(new_test_path):
                continue  # Don't remove the file we're about to create

            # Check if this is a related test file (similar keywords)
            old_keywords = set(filename.replace('test_', '').replace('.py', '').split('_'))
            overlap = feature_keywords & old_keywords

            if overlap:  # There's keyword overlap - possibly related
                old_path = os.path.join(test_dir, filename)
                print(f"  Checking old test file: {filename}")

                # Try to read it and check for import errors
                try:
                    with open(old_path, 'r') as f:
                        content = f.read()

                    # Look for suspicious imports that don't exist in project
                    suspicious_patterns = [
                        r'from presentation\.(theme_toggle|static|nonexistent)',
                        r'from src\.(nonexistent|fake)',
                        r'import theme_toggle',
                        r'from \.\..*theme_toggle'
                    ]

                    has_bad_import = any(re.search(pattern, content) for pattern in suspicious_patterns)

                    if has_bad_import:
                        print(f"  ⚠️  {filename} has invalid imports - removing")
                        os.remove(old_path)
                        removed.append(filename)
                    else:
                        # Try to compile it - if it has syntax errors, remove it
                        try:
                            compile(content, old_path, 'exec')
                        except SyntaxError:
                            print(f"  ⚠️  {filename} has syntax errors - removing")
                            os.remove(old_path)
                            removed.append(filename)

                except Exception as e:
                    print(f"  ⚠️  Error checking {filename}: {e}")

        return removed

    def _normalize_file_entries(self, files: Any) -> List[Dict[str, Any]]:
        """Normalize file descriptors for test generation"""
        normalized: List[Dict[str, Any]] = []
        if not files:
            return normalized

        if not isinstance(files, list):
            files = [files]

        for entry in files:
            if isinstance(entry, str):
                normalized.append({"path": entry, "instructions": []})
                continue

            if isinstance(entry, dict):
                path = entry.get("path") or entry.get("file") or entry.get("target")
                if not path:
                    continue
                instructions = entry.get("instructions", [])
                if isinstance(instructions, str):
                    instructions = [instructions]
                normalized.append({
                    "path": path,
                    "instructions": instructions
                })

        return normalized
    
    async def run_tests(self, context: WorkflowContext, test_file: Optional[str] = None) -> bool:
        """Execute tests using pytest"""
        test_target = test_file or "tests/"
        self.log(context, "Running tests", test_target)

        if not context.test_files:
            self.log(context, "No tests to run", "", True)
            context.test_results = {"passed": True, "exit_code": 0}
            return True

        print(f"\n{'='*60}")
        print("EXECUTING TESTS")
        print('='*60)

        # Check if pytest is available
        pytest_check = subprocess.run(
            ["python", "-m", "pytest", "--version"],
            cwd=self.repository_path,
            capture_output=True,
            text=True
        )

        if pytest_check.returncode != 0:
            print("⚠️  pytest not installed in target repository")
            print("   Attempting to install pytest...")

            # Try to install pytest
            install_result = subprocess.run(
                ["pip", "install", "pytest"],
                cwd=self.repository_path,
                capture_output=True,
                text=True,
                timeout=60
            )

            if install_result.returncode == 0:
                print("✓ pytest installed successfully")
                # Continue to run tests below
            else:
                print("✗ Failed to install pytest")
                print(f"   Error: {install_result.stderr}")
                print(f"   To run tests manually: cd {self.repository_path} && pip install pytest && pytest")
                context.test_results = {
                    "passed": False,  # Tests were NOT executed
                    "exit_code": -1,
                    "skipped": True,
                    "passed_count": 0,
                    "failed_count": 0,
                    "message": "pytest not installed - tests not executed"
                }
                self.log(context, "Tests skipped", "pytest not available")
                return True  # Don't fail workflow, but mark tests as not passed

        # Run pytest
        try:
            # Try pytest first, fall back to python -m pytest
            result = subprocess.run(
                ["pytest", "-v", "--tb=short", "--color=yes", test_target],
                cwd=self.repository_path,
                capture_output=True,
                text=True,
                timeout=120
            )
        except FileNotFoundError:
            # pytest not in PATH, try python -m pytest
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", "-v", "--tb=short", "--color=yes", test_target],
                    cwd=self.repository_path,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            except Exception as e:
                print(f"✗ Failed to run pytest: {e}")
                print("  Make sure pytest is installed: pip install pytest")
                context.test_results = {
                    "passed": False,
                    "exit_code": -1,
                    "error": str(e)
                }
                return False
        except subprocess.TimeoutExpired:
            print("✗ Tests timed out after 120 seconds")
            context.test_results = {
                "passed": False,
                "exit_code": -1,
                "error": "Timeout"
            }
            return False
        except Exception as e:
            print(f"✗ Error running tests: {e}")
            context.test_results = {
                "passed": False,
                "exit_code": -1,
                "error": str(e)
            }
            return False

        # Parse results
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

        # Extract test counts
        passed_match = re.search(r'(\d+) passed', stdout)
        failed_match = re.search(r'(\d+) failed', stdout)
        error_match = re.search(r'(\d+) error', stdout)

        passed_count = int(passed_match.group(1)) if passed_match else 0
        failed_count = int(failed_match.group(1)) if failed_match else 0
        error_count = int(error_match.group(1)) if error_match else 0

        # Detect collection errors (exit code 2 usually means collection failure)
        is_collection_error = (exit_code == 2 or error_count > 0) and passed_count == 0 and failed_count == 0

        # Parse failure details
        failed_tests = self._parse_test_failures(stdout)

        context.test_results = {
            "passed": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "failed_tests": failed_tests,
            "collection_error": is_collection_error
        }

        # Print results
        print(stdout)
        if stderr:
            print("STDERR:", stderr)

        print('='*60)
        if exit_code == 0:
            print(f"✓ All tests passed ({passed_count} tests)")
        elif is_collection_error:
            print(f"✗ TEST COLLECTION ERROR - Tests could not be imported/parsed")
            print(f"   Exit code: {exit_code}")
            print(f"   Errors: {error_count}")
            print("   This indicates the test file has import errors or syntax issues")
        else:
            print(f"✗ Tests failed: {failed_count} failed, {error_count} errors, {passed_count} passed")
        print('='*60 + '\n')

        self.log(context, "Tests executed",
                f"Exit code: {exit_code}, Passed: {passed_count}, Failed: {failed_count}")

        return exit_code == 0

    def _parse_test_failures(self, pytest_output: str) -> List[Dict[str, Any]]:
        """Parse pytest output to extract failure details"""
        failures = []

        # Look for FAILED test cases
        failed_pattern = r'FAILED (.*?) - (.*?)(?:\n|$)'
        matches = re.finditer(failed_pattern, pytest_output)

        for match in matches:
            test_name = match.group(1)
            error_msg = match.group(2)
            failures.append({
                "test": test_name,
                "error": error_msg
            })

        return failures

    async def analyze_test_failures(self, context: WorkflowContext) -> Optional[Dict[str, Any]]:
        """Use AI to analyze why tests failed and suggest fixes"""
        test_results = context.test_results

        if not test_results or test_results.get("passed", False):
            return None

        failed_tests = test_results.get("failed_tests", [])
        stdout = test_results.get("stdout", "")

        if not failed_tests:
            return None

        self.log(context, "Analyzing failures", f"{len(failed_tests)} failed tests")

        print(f"\n{'='*60}")
        print("ANALYZING TEST FAILURES")
        print('='*60)

        # Get implementation files for context
        impl_summary = "\n\n".join([
            f"--- {path} ---\n{content[:500]}..."
            for path, content in context.implementation_files.items()
        ])

        system_prompt = """You are a senior developer analyzing test failures.

For each failed test, determine:
1. Root cause of the failure
2. Whether it's a bug in the implementation or a bug in the test
3. Specific code changes needed to fix it

Return JSON:
{
    "failures": [
        {
            "test": "test_file.py::test_name",
            "root_cause": "Brief explanation",
            "issue_type": "implementation_bug" | "test_bug" | "missing_feature",
            "fix": {
                "file": "path/to/file.py",
                "description": "Specific change needed",
                "code_snippet": "def fixed_function():\\n    return 'correct'"
            }
        }
    ],
    "summary": "Overall assessment of what went wrong"
}"""

        failures_text = '\n'.join([
            f"- {f['test']}: {f['error']}"
            for f in failed_tests
        ])

        user_prompt = f"""Analyze these test failures:

Failed Tests:
{failures_text}

Pytest Output:
{stdout[-2000:]}

Implementation:
{impl_summary}

Provide your analysis in JSON format."""

        try:
            ai_response = await self.call_ai(system_prompt, user_prompt,
                                            temperature=0.1, max_tokens=2500)
            analysis = self.extract_json(ai_response)

            if not analysis:
                print("✗ Failed to parse AI analysis")
                return None

            # Print analysis
            print(f"\nRoot Cause Analysis:")
            print(f"  {analysis.get('summary', 'No summary provided')}")
            print()

            for failure in analysis.get("failures", []):
                print(f"Test: {failure.get('test', 'Unknown')}")
                print(f"  Cause: {failure.get('root_cause', 'Unknown')}")
                print(f"  Type: {failure.get('issue_type', 'Unknown')}")
                fix = failure.get("fix", {})
                if fix:
                    print(f"  Fix: {fix.get('description', 'No description')}")
                    print(f"  File: {fix.get('file', 'Unknown')}")
                print()

            print('='*60 + '\n')

            self.log(context, "Failure analysis complete",
                    f"Analyzed {len(analysis.get('failures', []))} failures")

            return analysis

        except Exception as e:
            print(f"✗ Error during analysis: {e}")
            import traceback
            traceback.print_exc()
            return None
