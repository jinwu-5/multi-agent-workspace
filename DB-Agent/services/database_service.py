from typing import Dict, Any, Optional
from config import get_database_config, DEFAULT_DATABASE
from ai import MongoDBQueryGenerator, PostgreSQLGenerator
from database import create_connection


class DatabaseService:
    def __init__(self, database_name: Optional[str] = None):
        """Initialize DatabaseService with specific database"""
        if database_name is None:
            database_name = DEFAULT_DATABASE

        self.db_name = database_name
        self.db_config = get_database_config(database_name)
        self.db_type = self.db_config["type"]
        self.connection = create_connection(self.db_config)

        # Initialize query generators
        if self.db_type == "mongodb":
            self.query_generator = MongoDBQueryGenerator(self.connection)
        else:
            self.query_generator = PostgreSQLGenerator(self.connection)

    def ask_question(self, question: str, max_retries: int = 3) -> Dict[str, Any]:
        """Main entry point for natural language queries"""
        result = self.query_generator.generate_and_execute(question, max_retries)
        result['database_type'] = self.db_type
        return result
