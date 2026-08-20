import pytest
from unittest.mock import Mock, patch, MagicMock, ANY
from database.postgresql_connection import PostgreSQLConnection


class TestPostgreSQLConnection:

    @pytest.fixture
    def mock_psycopg_connection(self):
        """Mock psycopg connection and cursor"""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()

        # Set up the connection context manager
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None

        # Set up the cursor context manager
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.__exit__.return_value = None

        # Connection.cursor() returns the mock cursor
        mock_conn.cursor.return_value = mock_cursor

        return mock_conn, mock_cursor

    @pytest.fixture
    def connection(self):
        """Create PostgreSQL connection"""
        return PostgreSQLConnection(
            connection_string="postgresql://user:pass@localhost/testdb",
            schema_name="public"
        )

    def test_initialization(self, connection):
        """Test PostgreSQL connection initialization"""
        assert connection.connection_string == "postgresql://user:pass@localhost/testdb"
        assert connection.schema_name == "public"
        assert connection._tables_cache is None
        assert connection._relationships_cache is None
        assert connection._schema_cache is None

    def test_initialization_default_schema(self):
        """Test initialization with default schema"""
        conn = PostgreSQLConnection("postgresql://user:pass@localhost/testdb")
        assert conn.schema_name == "public"

    @patch('database.postgresql_connection.psycopg.connect')
    def test_query_success(self, mock_connect, connection, mock_psycopg_connection):
        """Test successful query execution"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        # Mock query results - create proper description objects
        id_desc = Mock()
        id_desc.name = "id"
        name_desc = Mock()
        name_desc.name = "name"
        email_desc = Mock()
        email_desc.name = "email"

        mock_cursor.description = [id_desc, name_desc, email_desc]
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "John", "email": "john@example.com"},
            {"id": 2, "name": "Jane", "email": "jane@example.com"}
        ]

        result = connection.query("SELECT * FROM users", ("param1",))

        # Verify connection setup
        mock_connect.assert_called_once_with(
            "postgresql://user:pass@localhost/testdb",
            autocommit=True,
            row_factory=ANY
        )

        # Verify query execution
        mock_cursor.execute.assert_any_call("SET statement_timeout = '30s'")
        mock_cursor.execute.assert_any_call("SELECT * FROM users", ("param1",))

        # Verify result
        assert result["columns"] == ["id", "name", "email"]
        assert result["row_count"] == 2
        assert len(result["rows"]) == 2
        assert result["rows"][0]["name"] == "John"

    @patch('database.postgresql_connection.psycopg.connect')
    def test_query_no_params(self, mock_connect, connection, mock_psycopg_connection):
        """Test query execution without parameters"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        count_desc = Mock()
        count_desc.name = "count"
        mock_cursor.description = [count_desc]
        mock_cursor.fetchall.return_value = [{"count": 5}]

        result = connection.query("SELECT COUNT(*) as count FROM users")

        # Should pass empty tuple when no params provided
        mock_cursor.execute.assert_any_call("SELECT COUNT(*) as count FROM users", ())

        assert result["columns"] == ["count"]
        assert result["rows"][0]["count"] == 5

    @patch('database.postgresql_connection.psycopg.connect')
    def test_query_no_params(self, mock_connect, connection, mock_psycopg_connection):
        """Test query execution without parameters"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        count_desc = Mock()
        count_desc.name = "count"
        mock_cursor.description = [count_desc]
        mock_cursor.fetchall.return_value = [{"count": 5}]

        result = connection.query("SELECT COUNT(*) as count FROM users")

        # Should pass empty tuple when no params provided
        mock_cursor.execute.assert_any_call("SELECT COUNT(*) as count FROM users", ())

        assert result["columns"] == ["count"]
        assert result["rows"][0]["count"] == 5

    @patch('database.postgresql_connection.psycopg.connect')
    def test_query_no_results(self, mock_connect, connection, mock_psycopg_connection):
        """Test query with no results (like INSERT/UPDATE)"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        # No description means no result set (like INSERT)
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []

        result = connection.query("INSERT INTO users VALUES (1, 'test')")

        assert result["columns"] == []
        assert result["rows"] == []
        assert result["row_count"] == 0

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_all_tables_success(self, mock_connect, connection, mock_psycopg_connection):
        """Test successful table retrieval"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = [Mock(name="table_name")]
        mock_cursor.fetchall.return_value = [
            {"table_name": "users"},
            {"table_name": "orders"},
            {"table_name": "products"}
        ]

        tables = connection.get_all_tables()

        # Verify correct query
        expected_query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        mock_cursor.execute.assert_any_call(expected_query, ("public",))

        assert tables == ["users", "orders", "products"]
        assert connection._tables_cache == ["users", "orders", "products"]

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_all_tables_cached(self, mock_connect, connection):
        """Test that tables are cached after first call"""
        connection._tables_cache = ["cached_table"]

        tables = connection.get_all_tables()

        # Should not make database call
        mock_connect.assert_not_called()
        assert tables == ["cached_table"]

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_schema_info_success(self, mock_connect, connection, mock_psycopg_connection):
        """Test successful schema info retrieval"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        # Create proper description mock objects
        desc_mocks = []
        field_names = ["table_name", "column_name", "data_type", "is_nullable",
                       "column_default", "is_primary_key", "is_foreign_key",
                       "foreign_table_name", "foreign_column_name"]

        for field_name in field_names:
            desc_mock = Mock()
            desc_mock.name = field_name
            desc_mocks.append(desc_mock)

        mock_cursor.description = desc_mocks
        mock_cursor.fetchall.return_value = [
            {
                "table_name": "users", "column_name": "id", "data_type": "integer",
                "is_nullable": "NO", "column_default": "nextval('users_id_seq'::regclass)",
                "is_primary_key": True, "is_foreign_key": False,
                "foreign_table_name": None, "foreign_column_name": None
            },
            {
                "table_name": "users", "column_name": "name", "data_type": "varchar",
                "is_nullable": "YES", "column_default": None,
                "is_primary_key": False, "is_foreign_key": False,
                "foreign_table_name": None, "foreign_column_name": None
            },
            {
                "table_name": "orders", "column_name": "user_id", "data_type": "integer",
                "is_nullable": "NO", "column_default": None,
                "is_primary_key": False, "is_foreign_key": True,
                "foreign_table_name": "users", "foreign_column_name": "id"
            }
        ]

        schema_info = connection.get_schema_info()

        # Verify query parameters (called 3 times for the 3 %s placeholders)
        assert mock_cursor.execute.call_args[0][1] == ("public", "public", "public")

        # Verify schema structure
        assert len(schema_info) == 3

        # Check first column (users.id - primary key)
        users_id = schema_info[0]
        assert users_id["table_name"] == "users"
        assert users_id["column_name"] == "id"
        assert users_id["data_type"] == "integer"
        assert users_id["is_primary_key"] is True
        assert users_id["is_foreign_key"] is False
        assert users_id["foreign_reference"] is None

        # Check foreign key column (orders.user_id)
        orders_user_id = schema_info[2]
        assert orders_user_id["table_name"] == "orders"
        assert orders_user_id["column_name"] == "user_id"
        assert orders_user_id["is_foreign_key"] is True
        assert orders_user_id["foreign_reference"] == "users.id"

        # Verify caching
        assert connection._schema_cache == schema_info

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_schema_info_cached(self, mock_connect, connection):
        """Test that schema info is cached"""
        cached_schema = [{"table_name": "cached", "column_name": "test"}]
        connection._schema_cache = cached_schema

        schema_info = connection.get_schema_info()

        mock_connect.assert_not_called()
        assert schema_info == cached_schema

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_relationships_success(self, mock_connect, connection, mock_psycopg_connection):
        """Test successful relationships retrieval"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = [
            Mock(name="from_table"), Mock(name="from_column"),
            Mock(name="to_table"), Mock(name="to_column")
        ]
        mock_cursor.fetchall.return_value = [
            {
                "from_table": "orders", "from_column": "user_id",
                "to_table": "users", "to_column": "id"
            },
            {
                "from_table": "orders", "from_column": "product_id",
                "to_table": "products", "to_column": "id"
            },
            {
                "from_table": "order_items", "from_column": "order_id",
                "to_table": "orders", "to_column": "id"
            }
        ]

        relationships = connection.get_relationships()

        # Verify query
        assert mock_cursor.execute.call_args[0][1] == ("public",)

        # Verify relationship structure
        assert "orders" in relationships
        assert "order_items" in relationships

        # Check orders relationships
        orders_rels = relationships["orders"]
        assert len(orders_rels) == 2

        user_rel = next(r for r in orders_rels if r["from_column"] == "user_id")
        assert user_rel["to_table"] == "users"
        assert user_rel["to_column"] == "id"

        product_rel = next(r for r in orders_rels if r["from_column"] == "product_id")
        assert product_rel["to_table"] == "products"
        assert product_rel["to_column"] == "id"

        # Check order_items relationship
        order_items_rels = relationships["order_items"]
        assert len(order_items_rels) == 1
        assert order_items_rels[0]["from_column"] == "order_id"
        assert order_items_rels[0]["to_table"] == "orders"
        assert order_items_rels[0]["to_column"] == "id"

        # Verify caching
        assert connection._relationships_cache == relationships

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_relationships_cached(self, mock_connect, connection):
        """Test that relationships are cached"""
        cached_relationships = {"table1": [{"from_column": "col1", "to_table": "table2"}]}
        connection._relationships_cache = cached_relationships

        relationships = connection.get_relationships()

        mock_connect.assert_not_called()
        assert relationships == cached_relationships

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_relationships_empty(self, mock_connect, connection, mock_psycopg_connection):
        """Test relationships when no foreign keys exist"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = [
            Mock(name="from_table"), Mock(name="from_column"),
            Mock(name="to_table"), Mock(name="to_column")
        ]
        mock_cursor.fetchall.return_value = []

        relationships = connection.get_relationships()

        assert relationships == {}

    def test_get_column_names(self, connection):
        """Test getting column names from schema"""
        mock_schema = [
            {"table_name": "users", "column_name": "id"},
            {"table_name": "users", "column_name": "name"},
            {"table_name": "orders", "column_name": "id"},
            {"table_name": "orders", "column_name": "user_id"}
        ]

        with patch.object(connection, 'get_schema_info', return_value=mock_schema):
            column_names = connection.get_column_names()

        expected = ["users.id", "users.name", "orders.id", "orders.user_id"]
        assert column_names == expected

    @patch('database.postgresql_connection.psycopg.connect')
    def test_query_with_complex_result_set(self, mock_connect, connection, mock_psycopg_connection):
        """Test query with complex result set including NULLs"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = [
            Mock(name="id"), Mock(name="name"), Mock(name="email"), Mock(name="phone")
        ]
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "John", "email": "john@example.com", "phone": "123-456-7890"},
            {"id": 2, "name": "Jane", "email": None, "phone": None},
            {"id": 3, "name": "Bob", "email": "bob@example.com", "phone": "098-765-4321"}
        ]

        result = connection.query("SELECT * FROM users")

        assert result["row_count"] == 3
        assert result["rows"][0]["email"] == "john@example.com"
        assert result["rows"][1]["email"] is None
        assert result["rows"][1]["phone"] is None

    @patch('database.postgresql_connection.psycopg.connect')
    def test_connection_error_handling(self, mock_connect, connection):
        """Test connection error handling"""
        mock_connect.side_effect = Exception("Connection failed")

        with pytest.raises(Exception) as exc_info:
            connection.query("SELECT 1")

        assert "Connection failed" in str(exc_info.value)

    @patch('database.postgresql_connection.psycopg.connect')
    def test_query_timeout_setting(self, mock_connect, connection, mock_psycopg_connection):
        """Test that query timeout is properly set"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []

        connection.query("SELECT 1")

        # Verify timeout was set
        timeout_call = mock_cursor.execute.call_args_list[0]
        assert timeout_call[0][0] == "SET statement_timeout = '30s'"

    @patch('database.postgresql_connection.psycopg.connect')
    def test_schema_info_foreign_key_handling(self, mock_connect, connection, mock_psycopg_connection):
        """Test proper handling of foreign key references in schema info"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = [
            Mock(name="table_name"), Mock(name="column_name"), Mock(name="data_type"),
            Mock(name="is_nullable"), Mock(name="column_default"), Mock(name="is_primary_key"),
            Mock(name="is_foreign_key"), Mock(name="foreign_table_name"), Mock(name="foreign_column_name")
        ]
        mock_cursor.fetchall.return_value = [
            {
                "table_name": "orders", "column_name": "user_id", "data_type": "integer",
                "is_nullable": "NO", "column_default": None,
                "is_primary_key": False, "is_foreign_key": True,
                "foreign_table_name": "users", "foreign_column_name": "id"
            },
            {
                "table_name": "orders", "column_name": "status", "data_type": "varchar",
                "is_nullable": "YES", "column_default": None,
                "is_primary_key": False, "is_foreign_key": False,
                "foreign_table_name": None, "foreign_column_name": None
            }
        ]

        schema_info = connection.get_schema_info()

        # Foreign key column should have reference
        fk_column = schema_info[0]
        assert fk_column["foreign_reference"] == "users.id"

        # Regular column should not have reference
        regular_column = schema_info[1]
        assert regular_column["foreign_reference"] is None

    def test_schema_name_custom(self):
        """Test initialization with custom schema name"""
        connection = PostgreSQLConnection(
            "postgresql://user:pass@localhost/testdb",
            schema_name="custom_schema"
        )
        assert connection.schema_name == "custom_schema"

    @patch('database.postgresql_connection.psycopg.connect')
    def test_get_all_tables_custom_schema(self, mock_connect, mock_psycopg_connection):
        """Test table retrieval with custom schema"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        connection = PostgreSQLConnection(
            "postgresql://user:pass@localhost/testdb",
            schema_name="test_schema"
        )

        mock_cursor.description = [Mock(name="table_name")]
        mock_cursor.fetchall.return_value = [{"table_name": "test_table"}]

        tables = connection.get_all_tables()

        # Verify schema parameter
        assert mock_cursor.execute.call_args[0][1] == ("test_schema",)
        assert tables == ["test_table"]

    @patch('database.postgresql_connection.psycopg.connect')
    def test_multiple_foreign_keys_same_table(self, mock_connect, connection, mock_psycopg_connection):
        """Test handling of multiple foreign keys from the same table"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = [
            Mock(name="from_table"), Mock(name="from_column"),
            Mock(name="to_table"), Mock(name="to_column")
        ]
        mock_cursor.fetchall.return_value = [
            {
                "from_table": "orders", "from_column": "user_id",
                "to_table": "users", "to_column": "id"
            },
            {
                "from_table": "orders", "from_column": "product_id",
                "to_table": "products", "to_column": "id"
            },
            {
                "from_table": "orders", "from_column": "shipping_address_id",
                "to_table": "addresses", "to_column": "id"
            }
        ]

        relationships = connection.get_relationships()

        # Should have all three relationships for orders table
        orders_rels = relationships["orders"]
        assert len(orders_rels) == 3

        # Verify each relationship
        user_rel = next(r for r in orders_rels if r["to_table"] == "users")
        product_rel = next(r for r in orders_rels if r["to_table"] == "products")
        address_rel = next(r for r in orders_rels if r["to_table"] == "addresses")

        assert user_rel["from_column"] == "user_id"
        assert product_rel["from_column"] == "product_id"
        assert address_rel["from_column"] == "shipping_address_id"

    @patch('database.postgresql_connection.psycopg.connect')
    def test_empty_schema_info(self, mock_connect, connection, mock_psycopg_connection):
        """Test schema info with no tables"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        mock_cursor.description = [
            Mock(name="table_name"), Mock(name="column_name"), Mock(name="data_type"),
            Mock(name="is_nullable"), Mock(name="column_default"), Mock(name="is_primary_key"),
            Mock(name="is_foreign_key"), Mock(name="foreign_table_name"), Mock(name="foreign_column_name")
        ]
        mock_cursor.fetchall.return_value = []

        schema_info = connection.get_schema_info()

        assert schema_info == []
        assert connection._schema_cache == []

    @patch('database.postgresql_connection.psycopg.connect')
    def test_cache_independence(self, mock_connect, connection, mock_psycopg_connection):
        """Test that different cache types are independent"""
        mock_conn, mock_cursor = mock_psycopg_connection
        mock_connect.return_value = mock_conn

        # Set up mocks for different queries
        def mock_execute_side_effect(query, params=None):
            if "table_name" in query and "information_schema.tables" in query:
                mock_cursor.description = [Mock(name="table_name")]
                mock_cursor.fetchall.return_value = [{"table_name": "users"}]
            elif "FOREIGN KEY" in query:
                mock_cursor.description = [
                    Mock(name="from_table"), Mock(name="from_column"),
                    Mock(name="to_table"), Mock(name="to_column")
                ]
                mock_cursor.fetchall.return_value = []
            else:
                mock_cursor.description = None
                mock_cursor.fetchall.return_value = []

        mock_cursor.execute.side_effect = mock_execute_side_effect

        # Call different methods
        tables = connection.get_all_tables()
        relationships = connection.get_relationships()

        # Verify caches are set independently
        assert connection._tables_cache == ["users"]
        assert connection._relationships_cache == {}
        assert connection._schema_cache is None  # Not called yet

        # Verify they don't interfere with each other
        assert tables == ["users"]
        assert relationships == {}