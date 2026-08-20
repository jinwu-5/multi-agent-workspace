import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from ai.mongodb_generation import MongoDBQueryGenerator


class TestMongoDBQueryGenerator:

    @pytest.fixture
    def mock_connection(self):
        """Mock MongoDB connection"""
        connection = Mock()
        connection.collection_name = "test_collection"
        connection.get_schema_info.return_value = [
            {"column_name": "name", "data_type": "string", "examples": ["John", "Jane"]},
            {"column_name": "age", "data_type": "number", "examples": [25, 30]},
            {"column_name": "city", "data_type": "string", "examples": ["New York", "Boston"]}
        ]
        connection.query.return_value = {
            "columns": ["name", "age"],
            "rows": [["John", 25], ["Jane", 30]],
            "row_count": 2
        }
        return connection

    @pytest.fixture
    def generator(self, mock_connection):
        """Create MongoDB generator instance"""
        return MongoDBQueryGenerator(mock_connection)

    def test_initialization(self, mock_connection):
        """Test MongoDB generator initialization"""
        generator = MongoDBQueryGenerator(mock_connection)
        assert generator.connection == mock_connection
        assert generator.collection_name == "test_collection"
        assert generator.max_limit == 200

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
            "show me documents",
            "find records where age > 25",
            "count the documents",
            "what are the fields",
            "search for data",
            "list all records",
            "aggregate by city",
            "match documents",
            "show me test_collection data"
        ]

        for question in database_questions:
            assert not generator._detect_non_data_question(question), f"Should not detect non-data question: {question}"

    def test_check_non_data_question_returns_error(self, generator):
        """Test that non-data questions return appropriate error"""
        result = generator._check_non_data_question("hello world")

        assert result is not None
        assert result["ok"] is False
        assert result["error_type"] == "non_data_question"
        assert "doesn't appear to be a database query" in result["error"]
        assert "test_collection" in result["suggestion"]

    def test_check_non_data_question_database_query(self, generator):
        """Test that database queries don't trigger non-data error"""
        result = generator._check_non_data_question("show me all documents")
        assert result is None

    @patch('ai.mongodb_generation.get_aoai_client')
    def test_generate_query_success(self, mock_get_client, generator):
        """Test successful pipeline generation"""
        mock_choice = Mock()
        mock_choice.message.content = json.dumps({
            "pipeline": [{"$match": {"age": {"$gt": 25}}}, {"$limit": 10}],
            "rationale": "Filter by age and limit results"
        })

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generator._generate_query("find people older than 25")

        # Successful results don't have "ok" key, they have "pipeline" and "query"
        assert "pipeline" in result
        assert "query" in result
        assert result["pipeline"][0]["$match"]["age"]["$gt"] == 25
        assert "$limit" in str(result["pipeline"])

    @patch('ai.mongodb_generation.get_aoai_client')
    def test_generate_query_ai_error_response(self, mock_get_client, generator):
        """Test AI returning error response"""
        mock_choice = Mock()
        mock_choice.message.content = json.dumps({
            "error": "Field 'salary' not found",
            "suggestion": "Try using available fields: name, age, city"
        })

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generator._generate_query("show salary information")

        assert result["ok"] is False
        assert result["error"] == "Field 'salary' not found"
        assert result["error_type"] == "field_not_found"
        assert "available fields" in result["suggestion"]

    @patch('ai.mongodb_generation.get_aoai_client')
    def test_generate_query_write_operation_detected(self, mock_get_client, generator):
        """Test detection of write operations in generated pipeline"""
        mock_choice = Mock()
        mock_choice.message.content = json.dumps({
            "pipeline": [{"$out": "new_collection"}]
        })

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generator._generate_query("export data to new collection")

        assert result["ok"] is False
        assert result["error_type"] == "unsafe_pipeline_generated"
        assert "write operations" in result["error"]

    @patch('ai.mongodb_generation.get_aoai_client')
    def test_generate_query_exception(self, mock_get_client, generator):
        """Test exception handling in query generation"""
        mock_get_client.side_effect = Exception("API connection failed")

        result = generator._generate_query("show me data")

        assert result["ok"] is False
        assert result["error_type"] == "generation_exception"
        assert "Failed to generate MongoDB pipeline" in result["error"]

    def test_build_system_prompt(self, generator):
        """Test system prompt building"""
        prompt = generator._build_system_prompt()

        assert "MongoDB expert" in prompt
        assert "test_collection" in prompt
        assert "$match, $project, $group, $sort, $limit, $unwind" in prompt
        assert "NEVER use write operations" in prompt
        assert str(generator.max_limit) in prompt

    def test_build_context(self, generator):
        """Test context building for AI"""
        context = generator._build_context()

        assert "Collection: test_collection" in context
        assert "name:string (e.g. John, Jane)" in context
        assert "age:number (e.g. 25, 30)" in context
        assert "city:string (e.g. New York, Boston)" in context

    def test_execute_query(self, generator):
        """Test query execution"""
        pipeline_json = '[{"$limit": 5}]'
        result = generator._execute_query(pipeline_json)

        generator.connection.query.assert_called_once_with(pipeline_json)
        assert result["row_count"] == 2

    def test_extract_query_info(self, generator):
        """Test query info extraction"""
        query_result = {
            "query": '[{"$limit": 10}]',
            "pipeline": [{"$limit": 10}]
        }

        info = generator._extract_query_info(query_result)

        assert info["query"] == '[{"$limit": 10}]'
        assert info["parameters"] is None

    def test_contains_write_operations_positive(self, generator):
        """Test write operation detection in pipelines"""
        write_pipelines = [
            '[{"$out": "collection"}]',
            '[{"$merge": {"into": "target"}}]',
            '[{"$replace": {"with": "data"}}]'
        ]

        for pipeline in write_pipelines:
            assert generator._contains_write_operations(pipeline), f"Should detect write in: {pipeline}"

    def test_contains_write_operations_negative(self, generator):
        """Test write operation detection with read-only pipelines"""
        read_pipelines = [
            '[{"$match": {"age": 25}}]',
            '[{"$group": {"_id": "$city", "count": {"$sum": 1}}}]',
            '[{"$sort": {"name": 1}}, {"$limit": 10}]'
        ]

        for pipeline in read_pipelines:
            assert not generator._contains_write_operations(pipeline), f"Should not detect write in: {pipeline}"

    def test_contains_write_operations_invalid_json(self, generator):
        """Test write operation detection with invalid JSON"""
        assert not generator._contains_write_operations("invalid json")

    def test_get_query_type(self, generator):
        """Test query type identification"""
        assert generator._get_query_type() == "MongoDB pipeline"

    def test_get_descriptions(self, generator):
        """Test description methods"""
        assert generator._get_read_only_description() == ""
        assert "Show me documents" in generator._get_write_operation_suggestion()

    def test_ensure_limit_applied_empty_pipeline(self, generator):
        """Test limit application to empty pipeline"""
        result = generator._ensure_limit_applied([])
        assert result == [{"$limit": 200}]

    def test_ensure_limit_applied_no_aggregation_no_limit(self, generator):
        """Test limit application to pipeline without aggregation or limit"""
        pipeline = [{"$match": {"age": {"$gt": 25}}}]
        result = generator._ensure_limit_applied(pipeline)

        assert len(result) == 2
        assert result[1] == {"$limit": 200}

    def test_ensure_limit_applied_has_aggregation(self, generator):
        """Test limit not added when pipeline has aggregation"""
        pipeline = [{"$group": {"_id": "$city", "count": {"$sum": 1}}}]
        result = generator._ensure_limit_applied(pipeline)

        assert len(result) == 1  # No limit added
        assert result == pipeline

    def test_ensure_limit_applied_has_limit(self, generator):
        """Test limit not added when pipeline already has limit"""
        pipeline = [{"$match": {"age": {"$gt": 25}}}, {"$limit": 50}]
        result = generator._ensure_limit_applied(pipeline)

        assert len(result) == 2  # No additional limit
        assert result == pipeline

    def test_ensure_limit_applied_limit_too_high(self, generator):
        """Test limit capping when existing limit is too high"""
        pipeline = [{"$limit": 500}]
        result = generator._ensure_limit_applied(pipeline)

        assert result[0]["$limit"] == 200

    def test_build_fix_prompt(self, generator):
        """Test fix prompt building"""
        prompt = generator._build_fix_prompt(
            '[{"$match": {"invalid_field": 1}}]',
            "Field 'invalid_field' not found",
            "show me data",
            None
        )

        assert "Fix this MongoDB pipeline" in prompt
        assert "invalid_field" in prompt
        assert "Available fields: name, age, city" in prompt
        assert str(generator.max_limit) in prompt

    def test_parse_fix_response_valid_json_array(self, generator):
        """Test parsing valid JSON array fix response"""
        response = '[{"$match": {"age": {"$gt": 25}}}, {"$limit": 10}]'

        result = generator._parse_fix_response(response, "original", None)

        assert "query" in result
        pipeline = json.loads(result["query"])
        assert isinstance(pipeline, list)
        assert result["parameters"] is None

    def test_parse_fix_response_invalid_json(self, generator):
        """Test parsing invalid JSON fix response"""
        response = 'invalid json'

        result = generator._parse_fix_response(response, "original", None)

        assert result["query"] == "original"
        assert result["parameters"] is None

    def test_parse_fix_response_not_array(self, generator):
        """Test parsing fix response that's not a JSON array"""
        response = '{"pipeline": [{"$limit": 10}]}'

        result = generator._parse_fix_response(response, "original", None)

        assert result["query"] == "original"

    def test_integration_successful_flow(self, generator):
        """Test complete successful flow"""
        with patch('ai.mongodb_generation.get_aoai_client') as mock_client:
            mock_choice = Mock()
            mock_choice.message.content = json.dumps({
                "pipeline": [{"$match": {"age": {"$gt": 25}}}, {"$limit": 10}],
                "rationale": "Find people older than 25"
            })

            mock_response = Mock()
            mock_response.choices = [mock_choice]

            mock_client.return_value.chat.completions.create.return_value = mock_response

            result = generator.generate_and_execute("find people older than 25")

            assert result["ok"] is True
            assert result["query"] is not None
            assert result["result"]["row_count"] == 2

    def test_integration_non_data_question(self, generator):
        """Test complete flow with non-data question"""
        result = generator.generate_and_execute("hello world")

        assert result["ok"] is False
        assert result["error_type"] == "non_data_question"