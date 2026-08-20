from typing import Dict, Any, List, Optional
import json
from pymongo import MongoClient
from bson import Decimal128
from datetime import datetime
from .base import DatabaseConnection


class MongoDBConnection(DatabaseConnection):
    """MongoDB connection with document analysis capabilities"""

    def __init__(self, connection_string: str, database_name: str, collection_name: str):
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.collection = self.db[collection_name]
        self.collection_name = collection_name
        self.database_name = database_name

    def _convert_mongo_types(self, obj):
        """Convert MongoDB-specific types to JSON-serializable types"""
        if isinstance(obj, dict):
            return {key: self._convert_mongo_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_mongo_types(item) for item in obj]
        elif isinstance(obj, Decimal128):
            return float(str(obj))
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return str(obj)
        else:
            return obj

    def query(self, pipeline: str, params: Optional[dict] = None) -> Dict[str, Any]:
        """Execute MongoDB aggregation pipeline"""
        try:
            pipeline_dict = json.loads(pipeline)
            results = list(self.collection.aggregate(pipeline_dict, maxTimeMS=10000))
            results = [self._convert_mongo_types(doc) for doc in results]

            columns = []
            if results:
                first_doc = results[0]
                columns = self._extract_columns(first_doc)

            return {
                "columns": columns,
                "rows": results,
                "row_count": len(results)
            }
        except Exception as e:
            raise Exception(f"MongoDB query failed: {str(e)}")

    def _extract_columns(self, doc: dict, prefix: str = "") -> List[str]:
        """Extract column names, flattening nested objects"""
        columns = []
        for key, value in doc.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict) and key != "_id":
                columns.extend(self._extract_columns(value, full_key))
            else:
                columns.append(full_key)
        return columns

    def get_schema_info(self) -> List[dict]:
        """Analyze collection structure by sampling documents"""
        try:
            sample_docs = list(self.collection.aggregate([
                {"$sample": {"size": 100}},
                {"$project": {"_id": 0}}
            ]))

            if not sample_docs:
                return []

            field_info = {}
            for doc in sample_docs:
                self._analyze_document(doc, field_info)

            schema = []
            for field_name, info in field_info.items():
                type_counts = {}
                for type_name in info["types"]:
                    type_counts[type_name] = type_counts.get(type_name, 0) + 1

                primary_type = max(type_counts.keys(), key=lambda x: type_counts[x])

                schema.append({
                    "column_name": field_name,
                    "data_type": self._map_python_type_to_mongo(primary_type),
                    "examples": info["examples"][:3]
                })

            return schema
        except Exception as e:
            print(f"Error analyzing schema: {e}")
            return []

    def _analyze_document(self, doc: dict, field_info: dict, prefix: str = ""):
        """Recursively analyze document structure"""
        for field, value in doc.items():
            full_field = f"{prefix}.{field}" if prefix else field

            if full_field not in field_info:
                field_info[full_field] = {"types": [], "examples": []}

            value_type = type(value).__name__
            field_info[full_field]["types"].append(value_type)

            if len(field_info[full_field]["examples"]) < 5:
                example_value = str(value)[:50] if len(str(value)) > 50 else str(value)
                field_info[full_field]["examples"].append(example_value)

            if isinstance(value, dict):
                self._analyze_document(value, field_info, full_field)

    def _map_python_type_to_mongo(self, python_type: str) -> str:
        """Map Python types to MongoDB-friendly type names"""
        type_mapping = {
            "str": "string",
            "int": "int32",
            "float": "double",
            "bool": "boolean",
            "datetime": "date",
            "ObjectId": "objectId",
            "list": "array",
            "dict": "object"
        }
        return type_mapping.get(python_type, python_type)

    def get_column_names(self) -> List[str]:
        """Get all column names across the collection"""
        schema = self.get_schema_info()
        return [field["column_name"] for field in schema]