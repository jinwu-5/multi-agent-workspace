import json
import re
from typing import Any, Dict, Optional
from ai import BaseQueryGenerator
from config import get_aoai_client, AOAI_DEPLOYMENT


class MongoDBQueryGenerator(BaseQueryGenerator):
    """MongoDB aggregation pipeline generator"""

    def __init__(self, connection):
        super().__init__(connection)
        self.collection_name = connection.collection_name

    def _check_non_data_question(self, question: str) -> Optional[Dict[str, Any]]:
        """Check for non-data questions specific to MongoDB"""
        if self._detect_non_data_question(question):
            return {
                "ok": False,
                "error": "This doesn't appear to be a database query. Please ask questions about retrieving or analyzing data from the database.",
                "error_type": "non_data_question",
                "suggestion": f"Try asking about the available data, like 'Show me records from {self.collection_name}' or 'What fields are available?'",
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
            'collection', 'document', 'field', 'database', 'aggregate',
            'match', 'group', 'sort', 'limit', 'pipeline'
        ]

        # Add collection name as a keyword if available
        if self.collection_name:
            data_keywords.append(self.collection_name.lower())

        # If no data-related keywords found, likely not a database question
        has_data_keywords = any(keyword in question_lower for keyword in data_keywords)

        return not has_data_keywords

    def _generate_query(self, question: str) -> Dict[str, Any]:
        """Generate MongoDB aggregation pipeline from natural language question"""
        system_prompt = self._build_system_prompt()

        user_msg = f"""
        Question: {question}
        Generate MongoDB pipeline to answer this.

        If the question asks for fields that don't exist in the available schema, return an error explaining what's missing.

        Return JSON: {{"pipeline": [...], "rationale": "..."}} for valid queries
        OR {{"error": "explanation of what went wrong", "suggestion": "helpful alternative"}} for invalid requests

        Examples:
        - Show 5 records: {{"pipeline": [{{"$limit": 5}}]}}
        - Show records: {{"pipeline": [{{"$limit": 200}}]}}
        - Count by field: {{"pipeline": [{{"$group": {{"_id": "$field", "count": {{"$sum": 1}}}}}}, {{"$sort": {{"count": -1}}}}]}}
        - Find with condition: {{"pipeline": [{{"$match": {{"field": "value"}}}}, {{"$limit": 200}}]}}
        - Missing field error: {{"error": "The collection does not contain field 'payment_amount'. Available fields include: field1, field2, field3", "suggestion": "Try asking about available fields instead."}}
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
            print("MongoDB result: ", result)

            # Check if AI returned an error response
            if "error" in result:
                return {
                    "ok": False,
                    "error": result["error"],
                    "error_type": "field_not_found",
                    "suggestion": result.get("suggestion", "Please check available fields and try again."),
                    "query": None,
                    "attempts": 0
                }

            # Handle successful pipeline generation
            if "pipeline" in result:
                # Check for write operations in the pipeline
                pipeline = result["pipeline"]
                if self._contains_write_operations(json.dumps(pipeline)):
                    return {
                        "ok": False,
                        "error": "Generated pipeline contains write operations which are not allowed.",
                        "error_type": "unsafe_pipeline_generated",
                        "suggestion": "Please rephrase your question to request data retrieval only.",
                        "query": None,
                        "attempts": 0
                    }

                # Apply limit if needed
                pipeline = self._ensure_limit_applied(pipeline)
                result["query"] = json.dumps(pipeline)
                result["pipeline"] = pipeline
                return result
            else:
                return {
                    "ok": False,
                    "error": "AI response did not contain a valid pipeline or error message",
                    "error_type": "invalid_ai_response",
                    "suggestion": "Please try rephrasing your question.",
                    "query": None,
                    "attempts": 0
                }

        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to generate MongoDB pipeline: {str(e)}",
                "error_type": "generation_exception",
                "suggestion": "Please try rephrasing your question or check if the requested fields exist in the collection.",
                "query": None,
                "attempts": 0
            }

    def _build_system_prompt(self) -> str:
        """Build system prompt for MongoDB AI"""
        return f"""
        You are a MongoDB expert. Generate aggregation pipelines for read-only queries ONLY.

        CRITICAL RULES:
        - Collection: {self.collection_name}
        - Use only: $match, $project, $group, $sort, $limit, $unwind
        - NEVER use write operations like $out, $merge, or any update/delete operations
        - NO write operations whatsoever
        - Add $limit (max {self.max_limit}) for raw results - this is mandatory for queries without aggregation
        - Use $regex with $options: "i" for case-insensitive text search
        - For queries that return individual documents (not aggregated), always include $limit: {self.max_limit} or less
        - For aggregated results (like counts, groups), limit is optional but recommended

        If asked for write operations like deleting, updating, or inserting data,
        respond with an error explaining that only read operations are allowed.

        Fields: {self._build_context()}
        """

    def _build_context(self) -> str:
        """Build MongoDB schema context for AI"""
        schema = self.connection.get_schema_info()
        fields = []

        for field in schema[:20]:
            examples = field.get("examples", [])
            examples_str = ", ".join(str(e)[:20] for e in examples[:2])
            field_desc = f"{field['column_name']}:{field['data_type']}"
            if examples_str:
                field_desc += f" (e.g. {examples_str})"
            fields.append(field_desc)

        return f"Collection: {self.connection.collection_name} -> " + ", ".join(fields)

    def _execute_query(self, query: str, parameters: Any = None) -> Any:
        """Execute MongoDB pipeline"""
        return self.connection.query(query)

    def _extract_query_info(self, query_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract pipeline from generation result"""
        return {
            "query": query_result.get("query", ""),
            "parameters": None
        }

    def _contains_write_operations(self, query: str) -> bool:
        """Check if pipeline contains write operations"""
        try:
            pipeline = json.loads(query)
            write_stages = ['$out', '$merge', '$replace', '$update', '$delete']

            for stage in pipeline:
                if isinstance(stage, dict):
                    for key in stage.keys():
                        if key in write_stages:
                            return True
            return False
        except:
            return False

    def _get_query_type(self) -> str:
        return "MongoDB pipeline"

    def _get_read_only_description(self) -> str:
        return ""

    def _get_write_operation_suggestion(self) -> str:
        return "Try asking for data retrieval instead, like 'Show me documents' or 'Find records where...'"

    def _ensure_limit_applied(self, pipeline: list) -> list:
        """Ensure pipeline has appropriate limit for non-aggregated queries"""
        if not pipeline:
            return [{"$limit": self.max_limit}]

        # Check if this is an aggregation query (has $group, $count, etc.)
        has_aggregation = any(
            isinstance(stage, dict) and any(
                key in stage for key in ["$group", "$count", "$bucket", "$bucketAuto"]
            ) for stage in pipeline
        )

        # Check if pipeline already has a $limit
        has_limit = any(
            isinstance(stage, dict) and "$limit" in stage
            for stage in pipeline
        )

        # If no aggregation and no limit, add one
        if not has_aggregation and not has_limit:
            pipeline.append({"$limit": self.max_limit})

        # If there's a limit but it's too high, cap it
        for i, stage in enumerate(pipeline):
            if isinstance(stage, dict) and "$limit" in stage:
                current_limit = stage["$limit"]
                if isinstance(current_limit, int) and current_limit > self.max_limit:
                    pipeline[i] = {"$limit": self.max_limit}

        return pipeline

    def _build_fix_prompt(self, query: str, error_msg: str, question: str, parameters: Any = None) -> str:
        """Build MongoDB-specific fix prompt"""
        schema = self.connection.get_schema_info()
        field_names = [f["column_name"] for f in schema]

        return f"""
        Fix this MongoDB pipeline:
        Pipeline: {query}
        Error: {error_msg}
        Available fields: {', '.join(field_names[:20])}
        Question: {question}

        IMPORTANT: Ensure the fixed pipeline has appropriate limits (max {self.max_limit} for non-aggregated results).

        Return only the fixed pipeline as JSON array.
        """

    def _parse_fix_response(self, response_content: str, original_query: str, original_parameters: Any = None) -> Dict[
        str, Any]:
        """Parse MongoDB fix response"""
        content = response_content.strip()
        if content.startswith('['):
            try:
                fixed_pipeline = json.loads(content)
                fixed_pipeline = self._ensure_limit_applied(fixed_pipeline)
                return {"query": json.dumps(fixed_pipeline), "parameters": None}
            except:
                return {"query": content, "parameters": None}
        return {"query": original_query, "parameters": None}