import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
from ai.base import BaseQueryGenerator


class TestableQueryGenerator(BaseQueryGenerator):
    """Concrete implementation for testing abstract base class"""

    def __init__(self, connection):
        super().__init__(connection)
        self.generated_query = ""
        self.query_parameters = []

    def _generate_query(self, question: str) -> Dict[str, Any]:
        if "error_generation" in question:
            return {
                "ok": False,
                "error": "Test generation error",
                "error_type": "test_error"
            }
        return {
            "ok": True,
            "sql": "SELECT * FROM test",
            "parameters": []
        }

    def _build_system_prompt(self) -> str:
        return "Test system prompt"

    def _build_context(self) -> str:
        return "Test context"

    def _execute_query(self, query: str, parameters: Any = None) -> Any:
        if "execution_error" in query:
            raise Exception("Test execution error")
        return {"columns": ["id", "name"], "rows": [[1, "test"]], "row_count": 1}

    def _extract_query_info(self, query_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "query": query_result.get("sql", ""),
            "parameters": query_result.get("parameters", [])
        }

    def _contains_write_operations(self, query: str) -> bool:
        return any(word in query.upper() for word in ["DELETE", "INSERT", "UPDATE"])

    def _get_query_type(self) -> str:
        return "Test Query"

    def _get_read_only_description(self) -> str:
        return " (read-only)"

    def _get_write_operation_suggestion(self) -> str:
        return "Try read operations instead"


class TestBaseQueryGenerator:

    @pytest.fixture
    def mock_connection(self):
        """Mock database connection"""
        connection = Mock()
        connection.query.return_value = {"columns": ["id"], "rows": [[1]], "row_count": 1}
        return connection

    @pytest.fixture
    def generator(self, mock_connection):
        """Create test generator instance"""
        return TestableQueryGenerator(mock_connection)

    def test_initialization(self, mock_connection):
        """Test base class initialization"""
        generator = TestableQueryGenerator(mock_connection)
        assert generator.connection == mock_connection
        assert generator.max_limit == 200

    def test_detect_write_operation_positive(self, generator):
        """Test write operation detection for various write keywords"""
        write_questions = [
            "delete all records",
            "insert new data",
            "update the table",
            "drop the database",
            "create a new table",
            "modify existing records"
        ]

        for question in write_questions:
            assert generator._detect_write_operation(question), f"Should detect write operation in: {question}"

    def test_detect_write_operation_negative(self, generator):
        """Test write operation detection for read operations"""
        read_questions = [
            "show me all records",
            "find customers",
            "select data from table",
            "count the records",
            "what are the results"
        ]

        for question in read_questions:
            assert not generator._detect_write_operation(question), f"Should not detect write operation in: {question}"

    def test_generate_and_execute_write_operation_blocked(self, generator):
        """Test that write operations are blocked"""
        result = generator.generate_and_execute("delete all records")

        assert result["ok"] is False
        assert result["error_type"] == "write_operation_blocked"
        assert "write operations are not allowed" in result["error"].lower()
        assert result["suggestion"] == "Try read operations instead"
        assert result["attempts"] == 0

    def test_generate_and_execute_successful_query(self, generator):
        """Test successful query generation and execution"""
        result = generator.generate_and_execute("show me data")

        assert result["ok"] is True
        assert result["query"] == "SELECT * FROM test"
        assert "result" in result
        assert result["attempts"] == 1

    def test_generate_and_execute_generation_error(self, generator):
        """Test query generation error handling"""
        result = generator.generate_and_execute("error_generation test")

        assert result["ok"] is False
        assert result["error"] == "Test generation error"
        assert result["error_type"] == "test_error"

    def test_generate_and_execute_no_query_generated(self, generator):
        """Test case when no valid query is generated"""
        # Override the extract method to return empty query
        generator._extract_query_info = lambda x: {"query": "", "parameters": []}

        result = generator.generate_and_execute("show me data")

        assert result["ok"] is False
        assert result["error_type"] == "no_query_generated"
        assert "No valid Test Query was generated" in result["error"]

    def test_execute_with_retries_success(self, generator):
        """Test successful execution with retries"""
        query_info = {"query": "SELECT * FROM test", "parameters": []}

        result = generator._execute_with_retries(query_info, "test question", 2)

        assert result["ok"] is True
        assert result["query"] == "SELECT * FROM test"
        assert result["attempts"] == 1

    def test_execute_with_retries_max_exceeded(self, generator):
        """Test max retries exceeded"""
        # Create a generator that will always fail and never fix
        failing_generator = TestableQueryGenerator(generator.connection)

        # Override the _attempt_fix method to always return None (no fix)
        failing_generator._attempt_fix = lambda query, error, question, params: None

        query_info = {"query": "execution_error query", "parameters": []}

        result = failing_generator._execute_with_retries(query_info, "test question", 1)

        assert result["ok"] is False
        assert result["attempts"] == 2
        assert result["error"] == "Max retries exceeded"

    @patch('ai.base.get_aoai_client')
    def test_attempt_fix_success(self, mock_get_client, generator):
        """Test successful query fixing"""
        # Mock OpenAI response structure
        mock_choice = Mock()
        mock_choice.message.content = '{"query": "SELECT * FROM fixed", "parameters": []}'

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generator._attempt_fix("bad query", "syntax error", "test question", [])

        assert result is not None
        assert result["query"] == "SELECT * FROM fixed"
        assert result["parameters"] == []

    @patch('ai.base.get_aoai_client')
    def test_attempt_fix_exception(self, mock_get_client, generator):
        """Test query fixing when exception occurs"""
        mock_get_client.side_effect = Exception("API error")

        result = generator._attempt_fix("bad query", "syntax error", "test question", [])

        assert result is None

    def test_build_fix_prompt_default(self, generator):
        """Test default fix prompt building"""
        prompt = generator._build_fix_prompt("SELECT *", "syntax error", "show data", [])

        assert "Fix this Test Query" in prompt
        assert "SELECT *" in prompt
        assert "syntax error" in prompt
        assert "show data" in prompt
        assert "Test context" in prompt

    def test_parse_fix_response_success(self, generator):
        """Test successful fix response parsing"""
        response_content = '{"query": "SELECT * FROM table", "parameters": ["param1"]}'

        result = generator._parse_fix_response(response_content, "original", [])

        assert result["query"] == "SELECT * FROM table"
        assert result["parameters"] == ["param1"]

    def test_parse_fix_response_json_error(self, generator):
        """Test fix response parsing with invalid JSON"""
        response_content = 'invalid json'

        result = generator._parse_fix_response(response_content, "original", ["param"])

        assert result["query"] == "original"
        assert result["parameters"] == ["param"]

    def test_check_non_data_question_default(self, generator):
        """Test default non-data question check (returns None)"""
        result = generator._check_non_data_question("hello world")
        assert result is None

    def test_validate_before_execution_default(self, generator):
        """Test default validation before execution (does nothing)"""
        # Should not raise any exception
        generator._validate_before_execution("SELECT * FROM test", [])

    def test_abstract_methods_implemented(self, generator):
        """Test that all abstract methods are properly implemented"""
        # These should not raise NotImplementedError
        assert generator._generate_query("test") is not None
        assert generator._build_system_prompt() == "Test system prompt"
        assert generator._build_context() == "Test context"
        assert generator._execute_query("SELECT 1") is not None
        assert generator._extract_query_info({}) is not None
        assert isinstance(generator._contains_write_operations("SELECT"), bool)
        assert generator._get_query_type() == "Test Query"
        assert generator._get_read_only_description() == " (read-only)"
        assert generator._get_write_operation_suggestion() == "Try read operations instead"


class TestBaseQueryGeneratorAbstract:
    """Test that abstract methods raise NotImplementedError when not implemented"""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseQueryGenerator cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseQueryGenerator(Mock())

    def test_abstract_methods_exist(self):
        """Test that all expected abstract methods are defined"""
        abstract_methods = {
            '_generate_query',
            '_build_system_prompt',
            '_build_context',
            '_execute_query',
            '_extract_query_info',
            '_contains_write_operations',
            '_get_query_type',
            '_get_read_only_description',
            '_get_write_operation_suggestion'
        }

        actual_methods = set(BaseQueryGenerator.__abstractmethods__)
        assert abstract_methods == actual_methods