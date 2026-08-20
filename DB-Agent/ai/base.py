import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from config import get_aoai_client, AOAI_DEPLOYMENT


class BaseQueryGenerator(ABC):
    """Base class for database query generators"""

    def __init__(self, connection):
        self.connection = connection
        self.max_limit = 200

    def _detect_write_operation(self, question: str) -> bool:
        """Detect if the question is asking for a write operation"""
        question_lower = question.lower()
        write_keywords = [
            'delete', 'remove', 'drop', 'insert', 'add',
            'update', 'modify', 'change', 'replace', 'upsert',
            'truncate', 'create', 'alter', 'merge', 'set'
        ]
        return any(keyword in question_lower for keyword in write_keywords)

    def generate_and_execute(self, question: str, max_retries: int = 3) -> Dict[str, Any]:
        """Generate and execute query with retries - main entry point"""

        # Check for write operations first
        if self._detect_write_operation(question):
            return {
                "ok": False,
                "error": f"Write operations are not allowed. This system only supports read-only queries{self._get_read_only_description()}.",
                "error_type": "write_operation_blocked",
                "suggestion": self._get_write_operation_suggestion(),
                "query": None,
                "attempts": 0
            }

        # Check for non-data questions (if implemented by subclass)
        non_data_result = self._check_non_data_question(question)
        if non_data_result:
            return non_data_result

        # Generate query
        query_result = self._generate_query(question)

        # If query generation failed, return the error immediately
        if not query_result.get("ok", True):
            return query_result

        # Extract query components
        query_info = self._extract_query_info(query_result)
        if not query_info["query"]:
            return {
                "ok": False,
                "error": f"No valid {self._get_query_type()} was generated",
                "error_type": "no_query_generated",
                "suggestion": "Please try rephrasing your question.",
                "query": None,
                "attempts": 0
            }

        return self._execute_with_retries(query_info, question, max_retries)

    def _execute_with_retries(self, query_info: Dict[str, Any], question: str, max_retries: int) -> Dict[str, Any]:
        """Execute query with retries"""
        query = query_info["query"]
        parameters = query_info.get("parameters")

        for attempt in range(max_retries + 1):
            try:
                # Pre-execution validation (if needed by subclass)
                self._validate_before_execution(query, parameters)

                # Execute query
                result = self._execute_query(query, parameters)

                return {
                    "ok": True,
                    "query": query,
                    "result": result,
                    "attempts": attempt + 1
                }
            except Exception as e:
                if attempt >= max_retries:
                    return {
                        "ok": False,
                        "query": query,
                        "error": str(e),
                        "attempts": attempt + 1
                    }

                # Try to fix the query
                fixed_info = self._attempt_fix(query, str(e), question, parameters)
                if fixed_info and fixed_info["query"] != query:
                    query = fixed_info["query"]
                    parameters = fixed_info.get("parameters")
                else:
                    break

        return {
            "ok": False,
            "query": query,
            "error": "Max retries exceeded",
            "attempts": max_retries + 1
        }

    def _attempt_fix(self, query: str, error_msg: str, question: str, parameters: Any = None) -> Optional[
        Dict[str, Any]]:
        """Try to fix failed query using AI"""
        try:
            fix_prompt = self._build_fix_prompt(query, error_msg, question, parameters)

            client = get_aoai_client()
            response = client.chat.completions.create(
                model=AOAI_DEPLOYMENT,
                temperature=0,
                messages=[{"role": "user", "content": fix_prompt}],
                response_format={"type": "json_object"}
            )

            return self._parse_fix_response(response.choices[0].message.content, query, parameters)

        except Exception:
            return None

    # Abstract methods that subclasses must implement
    @abstractmethod
    def _generate_query(self, question: str) -> Dict[str, Any]:
        """Generate query from natural language question"""
        pass

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """Build system prompt for AI query generation"""
        pass

    @abstractmethod
    def _build_context(self) -> str:
        """Build database context for AI"""
        pass

    @abstractmethod
    def _execute_query(self, query: str, parameters: Any = None) -> Any:
        """Execute the generated query"""
        pass

    @abstractmethod
    def _extract_query_info(self, query_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract query and parameters from generation result"""
        pass

    @abstractmethod
    def _contains_write_operations(self, query: str) -> bool:
        """Check if query contains write operations"""
        pass

    @abstractmethod
    def _get_query_type(self) -> str:
        """Get the type of query (e.g., 'SQL', 'MongoDB pipeline')"""
        pass

    @abstractmethod
    def _get_read_only_description(self) -> str:
        """Get description of allowed read-only operations"""
        pass

    @abstractmethod
    def _get_write_operation_suggestion(self) -> str:
        """Get suggestion for alternative read operations"""
        pass

    # Optional methods with default implementations
    def _check_non_data_question(self, question: str) -> Optional[Dict[str, Any]]:
        """Check for non-data questions - override if needed"""
        return None

    def _validate_before_execution(self, query: str, parameters: Any = None) -> None:
        """Validate query before execution - override if needed"""
        pass

    def _build_fix_prompt(self, query: str, error_msg: str, question: str, parameters: Any = None) -> str:
        """Build prompt for fixing failed query - can be overridden"""
        return f"""
        Fix this {self._get_query_type()}:
        Query: {query}
        Error: {error_msg}
        Question: {question}
        Context: {self._build_context()}

        Return JSON with the fixed query.
        """

    def _parse_fix_response(self, response_content: str, original_query: str, original_parameters: Any = None) -> Dict[
        str, Any]:
        """Parse AI response for query fix - can be overridden"""
        try:
            result = json.loads(response_content)
            return {
                "query": result.get("query", original_query),
                "parameters": result.get("parameters", original_parameters)
            }
        except:
            return {"query": original_query, "parameters": original_parameters}