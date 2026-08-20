"""
Test Templates and Patterns

Provides proven test patterns that TestAgent can follow
"""

TEST_QUALITY_CHECKLIST = """
## Test Quality Checklist

Every test should cover:
1. **Happy Path** - Valid inputs, expected behavior
2. **Invalid Inputs** - None, empty strings, wrong types, out-of-range values
3. **Boundary Conditions** - Min/max values, edge cases, limits
4. **Error Conditions** - Exceptions, failures, timeouts
5. **State Changes** - Verify before/after states are correct

Assertion Quality:
- Use specific assertions (assertEqual, assertIn, assertRaises)
- Include meaningful assertion messages
- Test expected values, not just existence
- Avoid bare "assert result" - be specific about what you expect

Test Independence:
- Each test should run in isolation
- No shared state between tests
- Use setUp/tearDown or fixtures for test data
- Tests should pass in any order
"""

PYTHON_TEST_TEMPLATE = """
# Test Template for Python Unit Tests
import pytest
from unittest.mock import Mock, patch, MagicMock


class Test{ClassName}:
    \"\"\"Test suite for {ClassName}\"\"\"

    def setup_method(self):
        \"\"\"Set up test fixtures before each test method\"\"\"
        # Initialize test data
        pass

    def teardown_method(self):
        \"\"\"Clean up after each test method\"\"\"
        # Clean up resources
        pass

    # Happy Path Tests
    def test_{function}_with_valid_input_returns_expected_result(self):
        \"\"\"Test {function} with valid input returns expected result\"\"\"
        # Arrange
        input_data = "valid_input"
        expected = "expected_output"

        # Act
        result = function_under_test(input_data)

        # Assert
        assert result == expected, f"Expected {expected}, got {result}"

    # Invalid Input Tests
    def test_{function}_with_none_raises_value_error(self):
        \"\"\"Test {function} with None input raises ValueError\"\"\"
        with pytest.raises(ValueError, match="cannot be None"):
            function_under_test(None)

    def test_{function}_with_empty_string_raises_value_error(self):
        \"\"\"Test {function} with empty string raises ValueError\"\"\"
        with pytest.raises(ValueError):
            function_under_test("")

    def test_{function}_with_wrong_type_raises_type_error(self):
        \"\"\"Test {function} with wrong type raises TypeError\"\"\"
        with pytest.raises(TypeError):
            function_under_test(123)  # Passing int when str expected

    # Boundary Tests
    def test_{function}_with_minimum_valid_input(self):
        \"\"\"Test {function} with minimum valid input\"\"\"
        result = function_under_test(min_valid_value)
        assert result is not None

    def test_{function}_with_maximum_valid_input(self):
        \"\"\"Test {function} with maximum valid input\"\"\"
        result = function_under_test(max_valid_value)
        assert result is not None

    # Edge Cases
    def test_{function}_with_special_characters(self):
        \"\"\"Test {function} handles special characters correctly\"\"\"
        special_input = "test@#$%^&*()"
        result = function_under_test(special_input)
        # Assert specific behavior

    # State Change Tests
    def test_{function}_updates_state_correctly(self):
        \"\"\"Test {function} updates internal state correctly\"\"\"
        # Arrange
        initial_state = get_initial_state()

        # Act
        function_under_test(input_data)

        # Assert
        final_state = get_final_state()
        assert final_state != initial_state
        assert final_state == expected_state

    # Mock/Integration Tests
    @patch('module.external_dependency')
    def test_{function}_calls_external_dependency(self, mock_dep):
        \"\"\"Test {function} calls external dependency correctly\"\"\"
        # Arrange
        mock_dep.return_value = "mocked_result"

        # Act
        result = function_under_test()

        # Assert
        mock_dep.assert_called_once()
        assert result == "expected_result_using_mock"
"""

WEB_UI_TEST_TEMPLATE = """
# Test Template for Web UI (Python-rendered HTML/CSS)
import pytest


class TestWebUIComponent:
    \"\"\"Test suite for web UI component\"\"\"

    def test_html_contains_required_elements(self):
        \"\"\"Test HTML template contains all required elements\"\"\"
        html = generate_html_template()

        # Test for specific elements
        assert 'id="theme-toggle"' in html, "Missing theme toggle button"
        assert 'class="theme-toggle-btn"' in html, "Missing button class"
        assert '<button' in html, "No button element found"

    def test_css_contains_theme_variables(self):
        \"\"\"Test CSS includes theme variable definitions\"\"\"
        css = generate_css_styles()

        # Test for CSS variables
        assert '--bg-color' in css, "Missing background color variable"
        assert '--text-color' in css, "Missing text color variable"
        assert '.dark-theme' in css, "Missing dark theme class"

    def test_javascript_included_inline(self):
        \"\"\"Test JavaScript is included inline in HTML\"\"\"
        html = generate_html_template()

        # JavaScript should be inline
        assert '<script>' in html, "No inline script tag"
        assert 'localStorage' in html, "JavaScript not using localStorage"
        assert '</script>' in html, "Script tag not closed"

    def test_html_structure_valid(self):
        \"\"\"Test HTML has valid structure\"\"\"
        html = generate_html_template()

        # Basic validation
        assert html.count('<html') == html.count('</html>'), "HTML tag mismatch"
        assert html.count('<body') == html.count('</body>'), "Body tag mismatch"
        assert html.count('<head') == html.count('</head>'), "Head tag mismatch"

    def test_css_syntax_valid(self):
        \"\"\"Test CSS has valid syntax (basic check)\"\"\"
        css = generate_css_styles()

        # Count braces
        open_braces = css.count('{')
        close_braces = css.count('}')
        assert open_braces == close_braces, f"CSS brace mismatch: {open_braces} open, {close_braces} close"

    def test_theme_toggle_logic_present(self):
        \"\"\"Test theme toggle JavaScript logic is present\"\"\"
        html = generate_html_template()

        # Check for key logic
        assert 'addEventListener' in html or 'onclick' in html, "No event handler for toggle"
        assert 'classList' in html or 'className' in html, "No class manipulation"
"""

ACCEPTANCE_CRITERIA_TEST_TEMPLATE = """
# Test Template for Acceptance Criteria Validation
import pytest


class TestAcceptanceCriteria:
    \"\"\"Tests that validate acceptance criteria\"\"\"

    def test_ac1_{criterion_slug}(self):
        \"\"\"
        Acceptance Criterion 1: {criterion_text}
        \"\"\"
        # This test validates that AC1 is met
        # Arrange
        setup_preconditions()

        # Act
        result = perform_action()

        # Assert - verify criterion is met
        assert result_meets_criterion(result), "AC1 not met: {criterion_text}"

    def test_ac2_{criterion_slug}(self):
        \"\"\"
        Acceptance Criterion 2: {criterion_text}
        \"\"\"
        # Similar pattern for AC2
        pass
"""

def get_test_pattern_for_project_type(project_type: str) -> str:
    """Return test pattern based on project type"""

    patterns = {
        "python_web_ui": WEB_UI_TEST_TEMPLATE,
        "python_api": PYTHON_TEST_TEMPLATE,
        "python_library": PYTHON_TEST_TEMPLATE,
        "acceptance_criteria": ACCEPTANCE_CRITERIA_TEST_TEMPLATE
    }

    return patterns.get(project_type, PYTHON_TEST_TEMPLATE)


def get_test_guidance() -> str:
    """Return comprehensive test guidance"""
    return f"""{TEST_QUALITY_CHECKLIST}

## Common Test Anti-Patterns to Avoid

❌ **DON'T:**
- Write tests that just check if code runs without errors
- Use bare "assert result" without checking specific values
- Create tests that depend on execution order
- Mock everything - test real behavior when possible
- Write vague test names like "test1", "test2"
- Skip testing edge cases and error conditions

✅ **DO:**
- Test behavior, not implementation details
- Use descriptive test names that explain the scenario
- Test both success and failure paths
- Verify state changes, not just return values
- Use appropriate fixtures and mocks
- Follow Arrange-Act-Assert pattern

## Example: Good vs. Bad Tests

❌ BAD:
```python
def test_function():
    result = my_function("test")
    assert result  # Too vague!
```

✅ GOOD:
```python
def test_my_function_with_valid_string_returns_uppercase():
    # Arrange
    input_str = "test"
    expected = "TEST"

    # Act
    result = my_function(input_str)

    # Assert
    assert result == expected, f"Expected '{expected}', got '{result}'"
    assert isinstance(result, str), "Result should be a string"
```
"""
