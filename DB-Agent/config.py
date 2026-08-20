import os
from dotenv import load_dotenv
from fastapi import Header, HTTPException
from openai import AzureOpenAI
from typing import Dict, Any

load_dotenv()

DATABASES = {
    "dvdrental": {
        "type": "postgresql",
        "connection_string": os.getenv("DVDRENTAL_PG_CONN"),
        "schema": "public",
        "description": "DVD Rental database"
    },
    "airbnb_listings": {
        "type": "mongodb",
        "connection_string": os.getenv("AIRBNB_MONGO_CONN"),
        "database": os.getenv("AIRBNB_MONGO_DB", "mongo"),
        "collection": os.getenv("AIRBNB_MONGO_COLLECTION", "airbnb"),
        "description": "Airbnb Listings MongoDB database"
    }
}

DEFAULT_DATABASE = os.getenv("DEFAULT_DATABASE", "dvdrental")

# Filter configured databases
configured_databases = {
    name: config for name, config in DATABASES.items()
    if config.get("connection_string")
}

if not configured_databases:
    raise RuntimeError("No databases configured. Please set connection strings in .env file.")

# Azure OpenAI configuration
AOAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AOAI_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AOAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AOAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
APP_API_KEY = os.getenv("APP_API_KEY")

def verify_api_key(x_api_key: str = Header(default=None)):
    if not APP_API_KEY:
        raise HTTPException(status_code=500, detail="APP_API_KEY not set on server")
    if x_api_key != APP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing x-api-key")

def get_aoai_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=AOAI_KEY,
        api_version=AOAI_API_VERSION,
        azure_endpoint=AOAI_ENDPOINT,
    )

def get_database_config(database_name: str = None) -> Dict[str, Any]:
    """Get configuration for a specific database"""
    if database_name not in configured_databases:
        raise ValueError(f"Database '{database_name}' not found")

    return configured_databases[database_name]

def get_available_databases() -> Dict[str, Dict[str, Any]]:
    """Get all configured databases"""
    return configured_databases