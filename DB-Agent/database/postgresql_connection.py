from typing import Dict, Any, List, Optional
import psycopg
from psycopg.rows import dict_row
from .base import DatabaseConnection


class PostgreSQLConnection(DatabaseConnection):
    """PostgreSQL connection with auto-discovery"""

    def __init__(self, connection_string: str, schema_name: str = "public"):
        self.connection_string = connection_string
        self.schema_name = schema_name
        self._tables_cache = None
        self._relationships_cache = None
        self._schema_cache = None

    def query(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Execute SQL query and return results"""
        with psycopg.connect(self.connection_string, autocommit=True, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '30s'")
                cur.execute(sql, params or ())
                rows = cur.fetchall() if cur.description else []
                cols = [d.name for d in cur.description] if cur.description else []
                return {"columns": cols, "rows": rows, "row_count": len(rows)}

    def get_all_tables(self) -> List[str]:
        """Get all table names in the schema"""
        if self._tables_cache is None:
            query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
            result = self.query(query, (self.schema_name,))
            self._tables_cache = [row["table_name"] for row in result["rows"]]
        return self._tables_cache

    def get_schema_info(self) -> List[dict]:
        """Get comprehensive schema info for all tables"""
        if self._schema_cache is not None:
            return self._schema_cache

        query = """
        SELECT 
            t.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key,
            CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END as is_foreign_key,
            fk.foreign_table_name,
            fk.foreign_column_name
        FROM information_schema.tables t
        JOIN information_schema.columns c ON t.table_name = c.table_name AND t.table_schema = c.table_schema
        LEFT JOIN (
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name 
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s
        ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
        LEFT JOIN (
            SELECT 
                kcu.table_name, 
                kcu.column_name,
                ccu.table_name as foreign_table_name,
                ccu.column_name as foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name 
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu 
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s
        ) fk ON c.table_name = fk.table_name AND c.column_name = fk.column_name
        WHERE t.table_schema = %s AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name, c.ordinal_position
        """

        result = self.query(query, (self.schema_name, self.schema_name, self.schema_name))

        schema_info = []
        for row in result["rows"]:
            col_info = {
                "table_name": row["table_name"],
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "is_nullable": row["is_nullable"],
                "is_primary_key": row["is_primary_key"],
                "is_foreign_key": row["is_foreign_key"],
                "foreign_reference": None
            }

            if row["foreign_table_name"] and row["foreign_column_name"]:
                col_info["foreign_reference"] = f"{row['foreign_table_name']}.{row['foreign_column_name']}"

            schema_info.append(col_info)

        self._schema_cache = schema_info
        return schema_info

    def get_relationships(self) -> Dict[str, List[Dict[str, str]]]:
        """Get all table relationships"""
        if self._relationships_cache is not None:
            return self._relationships_cache

        query = """
        SELECT 
            tc.table_name as from_table,
            kcu.column_name as from_column,
            ccu.table_name as to_table,
            ccu.column_name as to_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu 
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu 
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' 
            AND tc.table_schema = %s
        ORDER BY tc.table_name, kcu.column_name
        """

        result = self.query(query, (self.schema_name,))

        relationships = {}
        for row in result["rows"]:
            from_table = row["from_table"]
            if from_table not in relationships:
                relationships[from_table] = []

            relationships[from_table].append({
                "from_column": row["from_column"],
                "to_table": row["to_table"],
                "to_column": row["to_column"]
            })

        self._relationships_cache = relationships
        return relationships

    def get_column_names(self) -> List[str]:
        """Get all column names across all tables"""
        schema = self.get_schema_info()
        return [f"{col['table_name']}.{col['column_name']}" for col in schema]