import json
import re
from typing import Any, Dict, Optional
from ai import BaseQueryGenerator
from config import get_aoai_client, AOAI_DEPLOYMENT


class PostgreSQLGenerator(BaseQueryGenerator):
    """PostgreSQL query generator"""

    def __init__(self, connection):
        super().__init__(connection)
        self.schema_info = connection.get_schema_info()
        self.tables = connection.get_all_tables() if hasattr(connection, 'get_all_tables') else []
        self.relationships = connection.get_relationships() if hasattr(connection, 'get_relationships') else {}

    def _check_non_data_question(self, question: str) -> Optional[Dict[str, Any]]:
        """Check for non-data questions specific to PostgreSQL"""
        if self._detect_non_data_question(question):
            return {
                "ok": False,
                "error": "This doesn't appear to be a database query. Please ask questions about retrieving or analyzing data from the database.",
                "error_type": "non_data_question",
                "suggestion": f"Try asking about the available data, like 'Show me records from {self.tables[0] if self.tables else 'the database'}' or 'What tables are available?'",
                "query": None,
                "attempts": 0
            }
        return None

    def _detect_non_data_question(self, question: str) -> bool:
        """Detect if the question is not actually about querying database data"""
        question_lower = question.lower().strip()

        # Simple greetings or non-database queries
        non_data_patterns = [
            r'^hello\s*world?\s*$',
            r'^hi\s*$',
            r'^hey\s*$',
            r'^hello\s*$',
            r'^test\s*$',
            r'^ping\s*$',
            r'what.*your.*name',
            r'who.*are.*you',
            r'how.*are.*you',
            r'what.*time.*is.*it',
            r'what.*weather',
        ]

        for pattern in non_data_patterns:
            if re.search(pattern, question_lower):
                return True

        # Check if question contains any database-related keywords
        data_keywords = [
            'show', 'find', 'get', 'select', 'count', 'list', 'search',
            'how many', 'what are', 'which', 'where', 'records', 'data',
            'table', 'column', 'row', 'database', 'customers', 'orders',
            'films', 'actors', 'rental', 'payment', 'category', 'staff'
        ]

        # Also check if question mentions any actual table names
        table_keywords = [table.lower() for table in self.tables] if self.tables else []
        all_data_keywords = data_keywords + table_keywords

        # If no data-related keywords found, likely not a database question
        has_data_keywords = any(keyword in question_lower for keyword in all_data_keywords)

        return not has_data_keywords

    def _generate_query(self, question: str) -> Dict[str, Any]:
        """Generate SQL query from natural language question"""
        system_prompt = self._build_system_prompt()

        user_msg = f"""
        Question: {question}

        Generate SQL to answer this question about the database.
        Available tables: {', '.join(self.tables)}

        If the question is not about querying database data, return an error explaining that 
        only database queries are supported.

        Return JSON: {{"sql": "...", "parameters": [...], "rationale": "...", "tables_used": [...]}}
        OR {{"error": "explanation of what went wrong", "suggestion": "helpful alternative"}} for invalid requests
        """

        try:
            client = get_aoai_client()
            response = client.chat.completions.create(
                model=AOAI_DEPLOYMENT,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            print("PostgreSQL result: ", result)

            # Check if AI returned an error response
            if "error" in result:
                return {
                    "ok": False,
                    "error": result["error"],
                    "error_type": result.get("error_type", "ai_rejected_query"),
                    "suggestion": result.get("suggestion", "Please ask a question about querying the database."),
                    "query": None,
                    "attempts": 0
                }

            # Handle successful SQL generation
            if "sql" in result:
                if "parameters" not in result:
                    result["parameters"] = []
                if "tables_used" not in result:
                    result["tables_used"] = []

                # Double-check that AI didn't generate write operations
                sql = result.get("sql", "")
                if self._contains_write_operations(sql):
                    return {
                        "ok": False,
                        "error": "Generated query contains write operations which are not allowed.",
                        "error_type": "unsafe_sql_generated",
                        "suggestion": "Please rephrase your question to request data retrieval only.",
                        "query": None,
                        "attempts": 0
                    }

                result["sql"] = self._validate_sql(result["sql"])
                return result
            else:
                return {
                    "ok": False,
                    "error": "AI response did not contain valid SQL or error message",
                    "error_type": "invalid_ai_response",
                    "suggestion": "Please try rephrasing your question about the database.",
                    "query": None,
                    "attempts": 0
                }

        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to generate SQL query: {str(e)}",
                "error_type": "generation_exception",
                "suggestion": "Please try rephrasing your question about the database.",
                "query": None,
                "attempts": 0
            }

    def _build_system_prompt(self) -> str:
        """Build system prompt for PostgreSQL AI"""
        context = self._build_context()

        return f"""
        You are an expert SQL assistant for a PostgreSQL database.

        CRITICAL RULES:
        - ONLY generate SELECT queries (read-only operations)
        - NEVER generate INSERT, UPDATE, DELETE, DROP, TRUNCATE, or any write operations
        - If asked for write operations, you should not generate any SQL
        - Use %s for parameters 
        - Add LIMIT for raw data queries (max {self.max_limit})
        - Use proper JOINs when multiple tables are needed
        - Use table aliases for readability
        - Always qualify column names with aliases when joining tables

        If the user asks for write operations like deleting, updating, or inserting data, 
        respond with an error explaining that only read operations are allowed.

        If the question doesn't seem to be about querying database data (like greetings, 
        general questions, or non-database topics), respond with an error explaining 
        that only database queries are supported.

        {context}
        """

    def _build_context(self) -> str:
        """Build PostgreSQL database context"""
        if not self.tables:
            return "Database structure unknown"

        # Group schema by table
        tables_info = {}
        for col in self.schema_info:
            table = col.get('table_name', 'unknown')
            if table not in tables_info:
                tables_info[table] = []

            col_desc = f"{col['column_name']}:{col['data_type']}"
            if col.get('is_primary_key'):
                col_desc += "(PK)"
            if col.get('foreign_reference'):
                col_desc += f"->FK({col['foreign_reference']})"
            tables_info[table].append(col_desc)

        context_parts = [f"Database has {len(self.tables)} tables: {', '.join(self.tables)}"]

        # Show all table details
        for table in self.tables:
            if table in tables_info:
                cols = tables_info[table][:15]
                context_parts.append(f"\n{table}: {', '.join(cols)}")

        # Add relationships
        if self.relationships:
            rel_parts = []
            for from_table, relations in self.relationships.items():
                for rel in relations:
                    rel_parts.append(f"{from_table}.{rel['from_column']}→{rel['to_table']}.{rel['to_column']}")
            if rel_parts:
                context_parts.append(f"\nJoins: {', '.join(rel_parts)}")

        return "\n".join(context_parts)

    def _execute_query(self, query: str, parameters: Any = None) -> Any:
        """Execute SQL query"""
        return self.connection.query(query, tuple(parameters) if parameters else None)

    def _validate_before_execution(self, query: str, parameters: Any = None) -> None:
        """Validate SQL with EXPLAIN before execution"""
        self.connection.query("EXPLAIN " + query, tuple(parameters) if parameters else None)

    def _extract_query_info(self, query_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract SQL and parameters from generation result"""
        return {
            "query": query_result.get("sql", ""),
            "parameters": query_result.get("parameters", [])
        }

    def _contains_write_operations(self, query: str) -> bool:
        """Check if SQL contains write operations"""
        query_upper = query.upper()
        write_patterns = [
            r'\bDELETE\b', r'\bINSERT\b', r'\bUPDATE\b', r'\bDROP\b',
            r'\bTRUNCATE\b', r'\bCREATE\b', r'\bALTER\b', r'\bREPLACE\b'
        ]

        for pattern in write_patterns:
            if re.search(pattern, query_upper):
                return True
        return False

    def _get_query_type(self) -> str:
        return "SQL"

    def _get_read_only_description(self) -> str:
        return " (SELECT statements)"

    def _get_write_operation_suggestion(self) -> str:
        return "Try asking for data retrieval instead, like 'Show me records' or 'Find data where...'"

    def _validate_sql(self, sql: str) -> str:
        """Clean up and validate SQL"""
        sql = sql.strip().rstrip(";")
        return self._add_limit_if_needed(sql)

    def _add_limit_if_needed(self, sql: str) -> str:
        """Add LIMIT if missing for non-aggregated queries"""
        sql = sql.strip().rstrip(";")

        # Don't add limit if query already has one or contains aggregation
        if (not re.search(r"\blimit\s+\d+\b", sql, re.IGNORECASE) and
                not re.search(r"\b(group\s+by|count|sum|avg|max|min)\b", sql, re.IGNORECASE)):
            sql += f" LIMIT {self.max_limit}"

        return sql

    def _build_fix_prompt(self, query: str, error_msg: str, question: str, parameters: Any = None) -> str:
        """Build PostgreSQL-specific fix prompt"""
        schema_text = ", ".join(
            f"{c.get('table_name', '')}.{c['column_name']}:{c['data_type']}" for c in self.schema_info[:30])

        return f"""
        Fix this SQL query:
        SQL: {query}
        Error: {error_msg}
        Question: {question}
        Schema: {schema_text}

        Return JSON: {{"sql": "...", "parameters": [...]}}
        """