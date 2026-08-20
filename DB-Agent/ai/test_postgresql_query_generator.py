import pytest
import json
from unittest.mock import Mock, patch
from ai.postgresql_generation import PostgreSQLGenerator


class TestPostgreSQLGenerator:

    @pytest.fixture
    def mock_connection(self):
        """Mock PostgreSQL connection"""
        connection = Mock()
        connection.get_schema_info.return_value = [
            {"table_name": "users", "column_name": "id", "data_type": "integer", "is_primary_key": True},
            {"table_name": "users", "column_name": "name", "data_type": "varchar", "is_primary_key": False},
            {"table_name": "users", "column_name": "email", "data_type": "varchar", "is_primary_key": False},
            {"table_name": "orders", "column_name": "id", "data_type": "integer", "is_primary_key": True},
            {"table_name": "orders", "column_name": "user_id", "data_type": "integer", "foreign_reference": "users.id"},
            {"table_name": "orders", "column_name": "amount", "data_type": "decimal"},
        ]
        connection.get_all_tables.return_value = ["users", "orders"]
        connection.get_relationships.return_value = {
            "orders": [
                {"from_column": "user_id", "to_table": "users", "to_column": "id"}
            ]
        }
        connection.query.return_value = {
            "columns": ["id", "name"],
            "rows": [[1, "John"], [2, "Jane"]],
            "row_count": 2
        }
        return connection

    @pytest.fixture
    def generator(self, mock_connection):
        """Create PostgreSQL generator instance"""
        return PostgreSQLGenerator(mock_connection)

    def test_initialization(self, mock_connection):
        """Test PostgreSQL generator initialization"""
        generator = PostgreSQLGenerator(mock_connection)
        assert generator.connection == mock_connection
        assert generator.tables == ["users", "orders"]
        assert len(generator.schema_info) == 6
        assert "orders" in generator.relationships

    def test_initialization_missing_methods(self):
        """Test initialization when connection doesn't have optional methods"""
        # Create a connection mock that only has get_schema_info
        connection = type('MockConnection', (), {
            'get_schema_info': lambda self: []
        })()

        generator = PostgreSQLGenerator(connection)
        assert generator.tables == []
        assert generator.relationships == {}

    def test_detect_non_data_question_greetings(self, generator):
        """Test detection of greeting messages"""
        greetings = [
            "hello world",
            "hi",
            "hey",
            "hello",
            "test",
            "ping"
        ]

        for greeting in greetings:
            assert generator._detect_non_data_question(greeting), f"Should detect non-data question: {greeting}"

    def test_detect_non_data_question_personal(self, generator):
        """Test detection of personal questions"""
        personal_questions = [
            "what is your name",
            "who are you",
            "how are you",
            "what time is it",
            "what's the weather"
        ]

        for question in personal_questions:
            assert generator._detect_non_data_question(question), f"Should detect non-data question: {question}"

    def test_detect_non_data_question_database_keywords(self, generator):
        """Test that database-related questions are not flagged as non-data"""
        database_questions = [
            "show me users",
            "find records where age > 25",
            "count the orders",
            "what are the tables",
            "search for data",
            "select from users",
            "how many customers",
            "which orders",
            "show me films",
            "actors in database"
        ]

        for question in database_questions:
            assert not generator._detect_non_data_question(question), f"Should not detect non-data question: {question}"

    def test_detect_non_data_question_table_names(self, generator):
        """Test that questions mentioning actual table names are not flagged"""
        table_questions = [
            "show me all users",
            "count orders",
            "users and orders relationship"
        ]

        for question in table_questions:
            assert not generator._detect_non_data_question(question), f"Should not detect non-data question: {question}"

    def test_check_non_data_question_returns_error(self, generator):
        """Test that non-data questions return appropriate error"""
        result = generator._check_non_data_question("hello world")

        assert result is not None
        assert result["ok"] is False
        assert result["error_type"] == "non_data_question"
        assert "doesn't appear to be a database query" in result["error"]
        assert "users" in result["suggestion"]

    def test_check_non_data_question_database_query(self, generator):
        """Test that database queries don't trigger non-data error"""
        result = generator._check_non_data_question("show me all users")
        assert result is None

    @patch('ai.postgresql_generation.get_aoai_client')
    def test_generate_query_success(self, mock_get_client, generator):
        """Test successful SQL generation"""
        mock_choice = Mock()
        mock_choice.message.content = json.dumps({
            "sql": "SELECT u.name, u.email FROM users u WHERE u.age > %s",
            "parameters": [25],
            "rationale": "Find users older than 25",
            "tables_used": ["users"]
        })

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generator._generate_query("find users older than 25")

        assert "sql" in result
        assert "parameters" in result
        assert result["parameters"] == [25]
        assert "users" in result["sql"]
        assert "WHERE" in result["sql"]

    @patch('ai.postgresql_generation.get_aoai_client')
    def test_generate_query_ai_error_response(self, mock_get_client, generator):
        """Test AI returning error response"""
        mock_choice = Mock()
        mock_choice.message.content = json.dumps({
            "error": "Table 'products' not found",
            "suggestion": "Available tables are: users, orders"
        })

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generator._generate_query("show me products")

        assert result["ok"] is False
        assert result["error"] == "Table 'products' not found"
        assert result["error_type"] == "ai_rejected_query"
        assert "Available tables" in result["suggestion"]

    @patch('ai.postgresql_generation.get_aoai_client')
    def test_generate_query_write_operation_detected(self, mock_get_client, generator):
        """Test detection of write operations in generated SQL"""
        mock_choice = Mock()
        mock_choice.message.content = json.dumps({
            "sql": "DELETE FROM users WHERE age < 18",
            "parameters": []
        })

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generator._generate_query("remove young users")

        assert result["ok"] is False
        assert result["error_type"] == "unsafe_sql_generated"
        assert "write operations" in result["error"]

    @patch('ai.postgresql_generation.get_aoai_client')
    def test_generate_query_exception(self, mock_get_client, generator):
        """Test exception handling in query generation"""
        mock_get_client.side_effect = Exception("API connection failed")

        result = generator._generate_query("show me data")

        assert result["ok"] is False
        assert result["error_type"] == "generation_exception"
        assert "Failed to generate SQL query" in result["error"]

    def test_build_system_prompt(self, generator):
        """Test system prompt building"""
        prompt = generator._build_system_prompt()

        assert "expert SQL assistant" in prompt
        assert "PostgreSQL database" in prompt
        assert "ONLY generate SELECT queries" in prompt
        assert "NEVER generate INSERT, UPDATE, DELETE" in prompt
        assert str(generator.max_limit) in prompt
        assert "users" in prompt and "orders" in prompt

    def test_build_context(self, generator):
        """Test context building for PostgreSQL"""
        context = generator._build_context()

        # Check the actual strings that appear in the context
        assert "Database has 2 tables: users, orders" in context
        assert "users: id:integer(PK)" in context
        assert "user_id:integer->FK(users.id)" in context  # This is what actually appears
        assert "Joins: orders.user_id→users.id" in context

    def test_build_context_no_tables(self):
        """Test context building when no tables available"""
        # Create a minimal connection object without optional methods
        connection = type('MockConnection', (), {
            'get_schema_info': lambda self: []
        })()

        generator = PostgreSQLGenerator(connection)

        context = generator._build_context()
        assert context == "Database structure unknown"

    def test_execute_query(self, generator):
        """Test SQL execution"""
        sql = "SELECT * FROM users LIMIT 10"
        parameters = [25]

        result = generator._execute_query(sql, parameters)

        generator.connection.query.assert_called_once_with(sql, (25,))
        assert result["row_count"] == 2

    def test_execute_query_no_parameters(self, generator):
        """Test SQL execution without parameters"""
        sql = "SELECT * FROM users LIMIT 10"

        generator._execute_query(sql, None)

        generator.connection.query.assert_called_once_with(sql, None)

    def test_validate_before_execution(self, generator):
        """Test EXPLAIN validation before execution"""
        sql = "SELECT * FROM users"
        parameters = []

        generator._validate_before_execution(sql, parameters)

        # The actual implementation converts empty list to None
        generator.connection.query.assert_called_once_with("EXPLAIN " + sql, None)

    def test_extract_query_info(self, generator):
        """Test query info extraction"""
        query_result = {
            "sql": "SELECT * FROM users",
            "parameters": [25, "John"],
            "tables_used": ["users"]
        }

        info = generator._extract_query_info(query_result)

        assert info["query"] == "SELECT * FROM users"
        assert info["parameters"] == [25, "John"]

    def test_contains_write_operations_positive(self, generator):
        """Test write operation detection in SQL"""
        write_queries = [
            "DELETE FROM users",
            "INSERT INTO users VALUES (1, 'test')",
            "UPDATE users SET name = 'new'",
            "DROP TABLE users",
            "TRUNCATE TABLE users",
            "CREATE TABLE new_table",
            "ALTER TABLE users ADD COLUMN age INT"
        ]

        for query in write_queries:
            assert generator._contains_write_operations(query), f"Should detect write in: {query}"

    def test_contains_write_operations_negative(self, generator):
        """Test write operation detection with read-only SQL"""
        read_queries = [
            "SELECT * FROM users",
            "SELECT COUNT(*) FROM orders",
            "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id"
        ]

        for query in read_queries:
            assert not generator._contains_write_operations(query), f"Should not detect write in: {query}"

    def test_get_query_type(self, generator):
        """Test query type identification"""
        assert generator._get_query_type() == "SQL"

    def test_get_descriptions(self, generator):
        """Test description methods"""
        assert generator._get_read_only_description() == " (SELECT statements)"
        assert "Show me records" in generator._get_write_operation_suggestion()

    def test_validate_sql(self, generator):
        """Test SQL validation and cleanup"""
        sql_with_semicolon = "SELECT * FROM users;"
        result = generator._validate_sql(sql_with_semicolon)

        assert not result.endswith(";")
        assert "LIMIT" in result

    def test_add_limit_if_needed_no_limit(self, generator):
        """Test adding limit to query without one"""
        sql = "SELECT * FROM users"
        result = generator._add_limit_if_needed(sql)

        assert f"LIMIT {generator.max_limit}" in result

    def test_add_limit_if_needed_has_limit(self, generator):
        """Test not adding limit when query already has one"""
        sql = "SELECT * FROM users LIMIT 50"
        result = generator._add_limit_if_needed(sql)

        assert result.count("LIMIT") == 1
        assert "LIMIT 50" in result

    def test_add_limit_if_needed_has_aggregation(self, generator):
        """Test not adding limit when query has aggregation"""
        aggregation_queries = [
            "SELECT COUNT(*) FROM users",
            "SELECT city, COUNT(*) FROM users GROUP BY city",
            "SELECT AVG(age) FROM users",
            "SELECT MAX(amount) FROM orders"
        ]

        for sql in aggregation_queries:
            result = generator._add_limit_if_needed(sql)
            assert "LIMIT" not in result, f"Should not add limit to: {sql}"

    def test_build_fix_prompt(self, generator):
        """Test fix prompt building"""
        prompt = generator._build_fix_prompt(
            "SELECT invalid_column FROM users",
            "Column 'invalid_column' does not exist",
            "show user data",
            ["param1"]
        )

        assert "Fix this SQL query" in prompt
        assert "invalid_column" in prompt
        assert "Column 'invalid_column' does not exist" in prompt
        assert "show user data" in prompt
        assert "users.id:integer" in prompt

    def test_integration_successful_flow(self, generator):
        """Test complete successful flow"""
        with patch('ai.postgresql_generation.get_aoai_client') as mock_client:
            mock_choice = Mock()
            mock_choice.message.content = json.dumps({
                "sql": "SELECT name, email FROM users WHERE age > %s",
                "parameters": [25],
                "rationale": "Find users older than 25"
            })

            mock_response = Mock()
            mock_response.choices = [mock_choice]

            mock_client.return_value.chat.completions.create.return_value = mock_response

            result = generator.generate_and_execute("find users older than 25")

            assert result["ok"] is True
            assert result["query"] is not None
            assert result["result"]["row_count"] == 2
            assert "LIMIT" in result["query"]

    def test_integration_non_data_question(self, generator):
        """Test complete flow with non-data question"""
        result = generator.generate_and_execute("hello world")

        assert result["ok"] is False
        assert result["error_type"] == "non_data_question"
        assert "users" in result["suggestion"]