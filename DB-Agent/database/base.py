from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class DatabaseConnection(ABC):
    """Abstract base class for database connections"""

    @abstractmethod
    def query(self, query: str, params: Optional[dict] = None) -> Dict[str, Any]:
        """Execute a query and return results"""
        pass

    @abstractmethod
    def get_schema_info(self) -> List[dict]:
        """Get schema information for the database"""
        pass

    @abstractmethod
    def get_column_names(self) -> List[str]:
        """Get all column names"""
        pass