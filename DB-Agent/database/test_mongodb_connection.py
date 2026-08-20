import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from bson import Decimal128, ObjectId
from database.mongodb_connection import MongoDBConnection


class TestMongoDBConnection:

    @pytest.fixture
    def mock_mongo_client(self):
        """Mock MongoDB client and collection"""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection

        return mock_client, mock_db, mock_collection

    @pytest.fixture
    def connection(self, mock_mongo_client):
        """Create MongoDB connection with mocked client"""
        mock_client, mock_db, mock_collection = mock_mongo_client

        with patch('database.mongodb_connection.MongoClient', return_value=mock_client):
            conn = MongoDBConnection(
                connection_string="mongodb://localhost:27017",
                database_name="test_db",
                collection_name="test_collection"
            )
        return conn

    def test_initialization(self, connection):
        """Test MongoDB connection initialization"""
        assert connection.database_name == "test_db"
        assert connection.collection_name == "test_collection"
        assert connection.client is not None
        assert connection.db is not None
        assert connection.collection is not None

    def test_convert_mongo_types_basic(self, connection):
        """Test conversion of basic MongoDB types"""
        # Test Decimal128
        decimal_val = Decimal128("123.45")
        result = connection._convert_mongo_types(decimal_val)
        assert result == 123.45

        # Test datetime
        dt = datetime(2023, 1, 1, 12, 0, 0)
        result = connection._convert_mongo_types(dt)
        assert result == "2023-01-01T12:00:00"

        # Test ObjectId - it actually gets returned as-is unless it has __dict__
        obj_id = ObjectId()
        result = connection._convert_mongo_types(obj_id)
        # ObjectId objects are returned as ObjectId, not string
        assert isinstance(result, ObjectId)

        # Test regular types
        assert connection._convert_mongo_types("string") == "string"
        assert connection._convert_mongo_types(42) == 42
        assert connection._convert_mongo_types(True) is True

    def test_convert_mongo_types_nested(self, connection):
        """Test conversion of nested structures"""
        test_data = {
            "name": "John",
            "amount": Decimal128("100.50"),
            "created_at": datetime(2023, 1, 1),
            "nested": {
                "value": Decimal128("50.25"),
                "items": [
                    {"price": Decimal128("10.00")},
                    {"price": Decimal128("20.00")}
                ]
            }
        }

        result = connection._convert_mongo_types(test_data)

        assert result["name"] == "John"
        assert result["amount"] == 100.50
        assert result["created_at"] == "2023-01-01T00:00:00"
        assert result["nested"]["value"] == 50.25
        assert result["nested"]["items"][0]["price"] == 10.00
        assert result["nested"]["items"][1]["price"] == 20.00

    def test_extract_columns_flat(self, connection):
        """Test column extraction from flat document"""
        doc = {
            "_id": ObjectId(),
            "name": "John",
            "age": 30,
            "email": "john@example.com"
        }

        columns = connection._extract_columns(doc)

        assert "_id" in columns
        assert "name" in columns
        assert "age" in columns
        assert "email" in columns
        assert len(columns) == 4

    def test_extract_columns_nested(self, connection):
        """Test column extraction from nested document"""
        doc = {
            "_id": ObjectId(),
            "name": "John",
            "address": {
                "street": "123 Main St",
                "city": "Anytown",
                "coordinates": {
                    "lat": 40.7128,
                    "lng": -74.0060
                }
            },
            "tags": ["developer", "python"]
        }

        columns = connection._extract_columns(doc)

        expected_columns = [
            "_id", "name", "address.street", "address.city",
            "address.coordinates.lat", "address.coordinates.lng", "tags"
        ]

        for col in expected_columns:
            assert col in columns

    def test_extract_columns_with_prefix(self, connection):
        """Test column extraction with prefix"""
        doc = {"name": "John", "age": 30}
        columns = connection._extract_columns(doc, prefix="user")

        assert "user.name" in columns
        assert "user.age" in columns

    def test_query_success(self, connection):
        """Test successful query execution"""
        # Mock aggregation results
        mock_results = [
            {"_id": "1", "name": "John", "age": 30},
            {"_id": "2", "name": "Jane", "age": 25}
        ]

        connection.collection.aggregate.return_value = mock_results

        pipeline = '[{"$match": {"age": {"$gte": 18}}}]'
        result = connection.query(pipeline)

        # Verify aggregate was called correctly
        connection.collection.aggregate.assert_called_once()
        call_args = connection.collection.aggregate.call_args
        assert call_args[0][0] == [{"$match": {"age": {"$gte": 18}}}]
        assert call_args[1]["maxTimeMS"] == 10000

        # Verify result structure
        assert result["row_count"] == 2
        assert len(result["rows"]) == 2
        assert "_id" in result["columns"]
        assert "name" in result["columns"]
        assert "age" in result["columns"]

    def test_query_empty_results(self, connection):
        """Test query with empty results"""
        connection.collection.aggregate.return_value = []

        pipeline = '[{"$match": {"nonexistent": "value"}}]'
        result = connection.query(pipeline)

        assert result["row_count"] == 0
        assert result["rows"] == []
        assert result["columns"] == []

    def test_query_invalid_json(self, connection):
        """Test query with invalid JSON pipeline"""
        invalid_pipeline = '{"invalid": json}'

        with pytest.raises(Exception) as exc_info:
            connection.query(invalid_pipeline)

        assert "MongoDB query failed" in str(exc_info.value)

    def test_query_mongo_exception(self, connection):
        """Test query when MongoDB raises exception"""
        connection.collection.aggregate.side_effect = Exception("Connection timeout")

        pipeline = '[{"$match": {}}]'

        with pytest.raises(Exception) as exc_info:
            connection.query(pipeline)

        assert "MongoDB query failed: Connection timeout" in str(exc_info.value)

    def test_analyze_document_simple(self, connection):
        """Test document analysis with simple structure"""
        doc = {
            "name": "John",
            "age": 30,
            "active": True
        }

        field_info = {}
        connection._analyze_document(doc, field_info)

        assert "name" in field_info
        assert "age" in field_info
        assert "active" in field_info

        assert "str" in field_info["name"]["types"]
        assert "int" in field_info["age"]["types"]
        assert "bool" in field_info["active"]["types"]

        assert "John" in field_info["name"]["examples"]
        assert "30" in field_info["age"]["examples"]
        assert "True" in field_info["active"]["examples"]

    def test_analyze_document_nested(self, connection):
        """Test document analysis with nested structure"""
        doc = {
            "user": {
                "profile": {
                    "name": "John"
                }
            }
        }

        field_info = {}
        connection._analyze_document(doc, field_info)

        assert "user" in field_info
        assert "user.profile" in field_info
        assert "user.profile.name" in field_info

    def test_analyze_document_long_value_truncation(self, connection):
        """Test that long values are truncated in examples"""
        doc = {
            "long_text": "a" * 100  # 100 character string
        }

        field_info = {}
        connection._analyze_document(doc, field_info)

        example = field_info["long_text"]["examples"][0]
        assert len(example) == 50  # Should be truncated to 50 chars
        assert example == "a" * 50

    def test_analyze_document_example_limit(self, connection):
        """Test that examples are limited to 5"""
        field_info = {"field": {"types": [], "examples": []}}

        # Analyze same field 10 times
        for i in range(10):
            doc = {"field": f"value_{i}"}
            connection._analyze_document(doc, field_info)

        assert len(field_info["field"]["examples"]) == 5

    def test_map_python_type_to_mongo(self, connection):
        """Test Python type to MongoDB type mapping"""
        mappings = {
            "str": "string",
            "int": "int32",
            "float": "double",
            "bool": "boolean",
            "datetime": "date",
            "ObjectId": "objectId",
            "list": "array",
            "dict": "object",
            "unknown_type": "unknown_type"  # Should return as-is
        }

        for python_type, expected_mongo_type in mappings.items():
            result = connection._map_python_type_to_mongo(python_type)
            assert result == expected_mongo_type

    def test_get_schema_info_success(self, connection):
        """Test successful schema analysis"""
        sample_docs = [
            {"name": "John", "age": 30, "active": True},
            {"name": "Jane", "age": 25, "active": False},
            {"name": "Bob", "age": 35, "active": True}
        ]

        connection.collection.aggregate.return_value = sample_docs

        schema = connection.get_schema_info()

        # Verify aggregate was called with correct pipeline
        connection.collection.aggregate.assert_called_once()
        call_args = connection.collection.aggregate.call_args[0][0]
        assert call_args[0]["$sample"]["size"] == 100
        assert call_args[1]["$project"]["_id"] == 0

        # Verify schema structure
        assert len(schema) == 3  # name, age, active

        # Find each field in schema
        name_field = next(f for f in schema if f["column_name"] == "name")
        age_field = next(f for f in schema if f["column_name"] == "age")
        active_field = next(f for f in schema if f["column_name"] == "active")

        assert name_field["data_type"] == "string"
        assert age_field["data_type"] == "int32"
        assert active_field["data_type"] == "boolean"

        assert "John" in name_field["examples"]
        assert "30" in age_field["examples"]
        assert "True" in active_field["examples"]

    def test_get_schema_info_empty_collection(self, connection):
        """Test schema analysis with empty collection"""
        connection.collection.aggregate.return_value = []

        schema = connection.get_schema_info()

        assert schema == []

    def test_get_schema_info_mixed_types(self, connection):
        """Test schema analysis with mixed field types"""
        sample_docs = [
            {"field": "string_value"},
            {"field": 42},
            {"field": "another_string"},
            {"field": "yet_another_string"}
        ]

        connection.collection.aggregate.return_value = sample_docs

        schema = connection.get_schema_info()

        field_schema = schema[0]
        # Should pick string as primary type (appears 3 times vs int 1 time)
        assert field_schema["data_type"] == "string"

    def test_get_schema_info_exception(self, connection):
        """Test schema analysis when exception occurs"""
        connection.collection.aggregate.side_effect = Exception("Connection error")

        with patch('builtins.print') as mock_print:
            schema = connection.get_schema_info()

        assert schema == []
        mock_print.assert_called_once()
        assert "Error analyzing schema" in mock_print.call_args[0][0]

    def test_get_column_names(self, connection):
        """Test getting column names"""
        # Mock schema info
        with patch.object(connection, 'get_schema_info') as mock_schema:
            mock_schema.return_value = [
                {"column_name": "name", "data_type": "string"},
                {"column_name": "age", "data_type": "int32"},
                {"column_name": "profile.email", "data_type": "string"}
            ]

            columns = connection.get_column_names()

            assert columns == ["name", "age", "profile.email"]

    def test_query_with_mongo_types_conversion(self, connection):
        """Test query result conversion of MongoDB types"""
        mock_results = [
            {
                "_id": ObjectId(),
                "amount": Decimal128("100.50"),
                "created_at": datetime(2023, 1, 1),
                "nested": {
                    "value": Decimal128("25.75")
                }
            }
        ]

        connection.collection.aggregate.return_value = mock_results

        pipeline = '[{"$match": {}}]'
        result = connection.query(pipeline)

        row = result["rows"][0]
        assert isinstance(row["amount"], float)
        assert row["amount"] == 100.50
        assert isinstance(row["created_at"], str)
        assert row["created_at"] == "2023-01-01T00:00:00"
        assert isinstance(row["nested"]["value"], float)
        assert row["nested"]["value"] == 25.75

    def test_schema_analysis_with_complex_nested_structure(self, connection):
        """Test schema analysis with deeply nested documents"""
        sample_docs = [
            {
                "user": {
                    "profile": {
                        "personal": {
                            "name": "John",
                            "age": 30
                        },
                        "contact": {
                            "email": "john@example.com"
                        }
                    }
                }
            }
        ]

        connection.collection.aggregate.return_value = sample_docs

        schema = connection.get_schema_info()

        field_names = [field["column_name"] for field in schema]

        assert "user" in field_names
        assert "user.profile" in field_names
        assert "user.profile.personal" in field_names
        assert "user.profile.personal.name" in field_names
        assert "user.profile.personal.age" in field_names
        assert "user.profile.contact" in field_names
        assert "user.profile.contact.email" in field_names