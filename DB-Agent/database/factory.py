from typing import Dict, Any
from .base import DatabaseConnection
from .postgresql_connection import PostgreSQLConnection
from .mongodb_connection import MongoDBConnection


def create_connection(db_config: Dict[str, Any]) -> DatabaseConnection:
    """
    Create database connection based on configuration
    """
    db_type = db_config.get("type", "").lower()

    if db_type == "mongodb":
        return MongoDBConnection(
            db_config["connection_string"],
            db_config["database"],
            db_config["collection"]
        )
    elif db_type == "postgresql":
        return PostgreSQLConnection(
            db_config["connection_string"],
            db_config.get("schema", "public")
        )
    else:
        raise ValueError(f"Unsupported database type: {db_type}. Supported types: postgresql, mongodb")