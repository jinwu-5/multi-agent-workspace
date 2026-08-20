# Multi-Database Query Agent

A FastAPI-based system that converts natural language questions into database queries using AI. Supports both **PostgreSQL** and **MongoDB** with automatic schema discovery.

## Agentic AI Capabilities

This system demonstrates **partially agentic behavior** through several intelligent capabilities:

### Current Agentic Features
- **Goal-oriented**: Autonomously works toward answering user questions with appropriate data queries
- **Multi-step reasoning**: Analyzes questions → identifies relevant tables → generates queries → executes → formats results
- **Error recovery**: Automatically diagnoses failed queries and generates corrected versions
- **Adaptive behavior**: Adjusts approach based on database type and discovered schema structure
- **Tool selection**: Chooses appropriate query methods (SQL vs MongoDB) based on context

### Non-Agentic Limitations
- **No memory**: Each interaction is independent with no learning from previous queries
- **Reactive only**: Responds to requests rather than proactively suggesting analyses
- **Single-turn**: Doesn't engage in conversational refinement of requirements
- **No goal persistence**: Cannot work toward complex analytical objectives over time

**Classification**: This is a **reactive intelligent assistant** rather than a fully autonomous agent. It shows intelligent behavior within its domain but lacks the persistence, learning, and proactive capabilities of true agentic systems.

## Features

- **AI-Powered**: Uses Azure OpenAI to convert natural language to database queries
- **Multi-Database**: Supports PostgreSQL (SQL) and MongoDB (aggregation pipelines)  
- **Auto-Discovery**: Automatically discovers database schemas and relationships
- **Smart Retry**: Automatically attempts to fix failed queries with AI
- **Rich Output**: Returns results as markdown tables or JSON with insights
- **Web Interface**: Interactive demo interface for testing queries
- **Optimized**: Intelligent context building to minimize token usage

## Supported Databases

### PostgreSQL
- Auto-discovers all tables and relationships
- Generates optimized SQL SELECT queries with proper JOINs
- Supports complex aggregations, filtering, and multi-table queries
- Works with any PostgreSQL database (single table or hundreds of tables)

### MongoDB  
- Generates MongoDB aggregation pipelines
- Supports matching, grouping, sorting, projections, and unwinding
- Field-aware pipeline generation with example data

## Quick Start

### 1. Installation
```bash
git clone <repository>
cd multi-database-query-agent
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file:

```bash
# Database Connections
DVDRENTAL_PG_CONN=postgresql://user:password@host:port/dvdrental
AIRBNB_MONGO_CONN=mongodb://user:password@host:port/database

# MongoDB specific (if using MongoDB)
AIRBNB_MONGO_DB=your_database_name
AIRBNB_MONGO_COLLECTION=your_collection_name

# Azure OpenAI (required)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# API Security
APP_API_KEY=your-secure-random-key

# Default database
DEFAULT_DATABASE=dvdrental
```

### 3. Run the Server
```bash
uvicorn main:app --reload --port 8000
```

Visit `http://localhost:8000` for the interactive demo interface!

## API Usage

### Check Available Databases
```bash
curl -X GET "http://localhost:8000/databases" \
  -H "x-api-key: your-secure-key"
```

### Health Check
```bash
curl -X GET "http://localhost:8000/health" \
  -H "x-api-key: your-secure-key"
```

### Natural Language Query
```bash
curl -X POST "http://localhost:8000/ask?database=dvdrental" \
  -H "x-api-key: your-secure-key" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Which customers have rented the most movies?",
    "as_table": true
  }'
```

## Example Queries

### PostgreSQL (DVDRental Database)
- "What's our revenue by film category?"
- "Average payment amount by customer city (top 10)?"
- "Which actors appear in the most horror movies?"
- "Show me rental trends by day of the week"
- "Which films have never been rented?"

### MongoDB (Airbnb Database)  
- "Count listings by property type"
- "What's the average price by room type?"
- "Show me 10 listings in New York"

## Database Configuration

The system automatically discovers database structure. Just provide connection details:

### PostgreSQL Setup
```python
DATABASES = {
    "your_database": {
        "type": "postgresql",
        "connection_string": "postgresql://user:pass@host:port/db",
        "schema": "public",  # optional, defaults to "public"
        "description": "Your database description"
    }
}
```

### MongoDB Setup
```python
DATABASES = {
    "your_database": {
        "type": "mongodb",
        "connection_string": "mongodb://user:pass@host:port/",
        "database": "database_name",
        "collection": "collection_name",
        "description": "Your database description"
    }
}
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Interface │    │   FastAPI API   │    │  Database Service│
│                 │────│                 │────│                 │
│  Natural Lang   │    │   /ask          │    │  PostgreSQL     │
│  Input          │    │   /databases    │    │  MongoDB        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                       ┌─────────────────┐
                       │  AI Generation  │
                       │                 │
                       │  SQL Generator  │
                       │  Mongo Generator│
                       └─────────────────┘
```

### Key Components

- **Database Connections**: Unified interface supporting both PostgreSQL and MongoDB
- **SQL Generator**: AI-powered SQL query generation with auto-discovery
- **MongoDB Generator**: AI-powered aggregation pipeline generation  
- **Database Service**: Coordinates query execution and retry logic
- **Web Interface**: Interactive demo for testing queries

## Development

### Project Structure
```
├── ai/
│   ├── sql_generation.py      # PostgreSQL query generation
│   └── mongodb_generation.py  # MongoDB query generation
├── database/
│   └── database_connections.py # Database connection classes
├── services/
│   └── database_service.py    # Database service coordinator
├── presentation/
│   ├── web_ui.py             # Web interface HTML
│   └── markdown.py           # Result formatting utilities
├── model/
│   └── schemas.py            # API request/response models
├── main.py                   # FastAPI application
├── config.py                # Database and AI configuration
├── requirements.txt         # Python dependencies
└── .env                     # Environment variables
```

### Adding New Databases

1. Add connection details to `config.py`:
```python
"new_database": {
    "type": "postgresql",  # or "mongodb"
    "connection_string": os.getenv("NEW_DB_CONN"),
    "description": "New database description"
}
```

2. Set environment variables in `.env`
3. The system automatically discovers schema and generates appropriate queries

### Token Optimization

The system uses several strategies to minimize AI token usage:
- Schema caching to avoid repeated discovery
- Intelligent context building showing only relevant table information  
- Abbreviated relationship descriptions
- Smart error handling with targeted fixes

## Error Handling

- **Connection Errors**: Automatic retry with exponential backoff
- **Query Errors**: AI-powered query repair attempts
- **Schema Issues**: Graceful fallback to basic queries
- **Timeout Protection**: Configurable query timeouts

## Security

- API key authentication required for all endpoints
- Read-only database operations
- SQL injection protection through parameterized queries
- Connection string encryption in environment variables

## Troubleshooting

### Connection Issues
- Verify connection strings in `.env` file
- Check database permissions (read access required)
- Test connectivity with `/health` endpoint

### Query Issues  
- Review generated queries in API responses
- Check table/collection names in database
- Verify AI model deployment is accessible

### Performance Issues
- Monitor token usage in AI service
- Consider schema optimization for very large databases
- Use query result limits appropriately
