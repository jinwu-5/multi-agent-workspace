from fastapi import FastAPI, Depends, Response, HTTPException, Query
from config import verify_api_key, get_available_databases, get_database_config
from model import AskReq
from presentation import render_markdown_result, insight_bullets, get_demo_interface
from services import DatabaseService
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Multi-Database Query API",
    description="Natural language queries for PostgreSQL and MongoDB databases",
    version="3.0.0"
)


@app.get("/", response_class=Response)
def demo_interface():
    return Response(content=get_demo_interface(), media_type="text/html")


@app.get("/databases", dependencies=[Depends(verify_api_key)])
def list_databases():
    """List all configured databases"""
    databases = get_available_databases()
    db_list = []

    for name, config in databases.items():
        db_info = {
            "name": name,
            "type": config["type"],
            "description": config.get("description", "")
        }

        if config["type"] == "postgresql":
            db_info["schema"] = config.get("schema", "public")
        else:  # mongodb
            db_info["collection"] = config.get("collection")

        db_list.append(db_info)

    return {"databases": db_list}


@app.get("/health")
def health(database: Optional[str] = Query(None)):
    """Check database health"""
    if database:
        return _check_single_database(database)
    else:
        return _check_all_databases()


def _check_single_database(database: str):
    """Health check for specific database"""
    try:
        logger.info(f"Checking health for database: {database}")
        db_config = get_database_config(database)
        db_service = DatabaseService(database)

        # Simple connectivity test
        if db_config["type"] == "mongodb":
            db_service.connection.query('[{"$limit": 1}]')
        else:  # postgresql
            tables = getattr(db_service.connection, 'get_all_tables', lambda: [])()
            if tables:
                db_service.connection.query(f"SELECT 1 FROM {tables[0]} LIMIT 1")
            else:
                db_service.connection.query("SELECT 1")

        logger.info(f"Database {database} health check passed")
        return {
            "ok": True,
            "database": database,
            "type": db_config["type"],
            "status": "connected"
        }
    except Exception as e:
        logger.error(f"Database {database} health check failed: {str(e)}", exc_info=True)
        return {
            "ok": False,
            "database": database,
            "status": f"error: {str(e)[:100]}",
            "error_details": str(e)
        }


def _check_all_databases():
    """Health check for all databases"""
    databases_status = {}

    for db_name in get_available_databases():
        try:
            db_config = get_database_config(db_name)
            db_service = DatabaseService(db_name)

            if db_config["type"] == "mongodb":
                db_service.connection.query('[{"$limit": 1}]')
            else:
                tables = getattr(db_service.connection, 'get_all_tables', lambda: [])()
                if tables:
                    db_service.connection.query(f"SELECT 1 FROM {tables[0]} LIMIT 1")
                else:
                    db_service.connection.query("SELECT 1")

            databases_status[db_name] = {
                "status": "connected",
                "type": db_config["type"]
            }
        except Exception as e:
            logger.error(f"Health check failed for {db_name}: {str(e)}")
            databases_status[db_name] = {
                "status": "error",
                "error": str(e)[:100],
                "error_details": str(e)
            }

    return {
        "ok": all(db["status"] == "connected" for db in databases_status.values()),
        "databases": databases_status
    }


@app.post("/ask", dependencies=[Depends(verify_api_key)])
def ask(req: AskReq, database: Optional[str] = Query(None)):
    """Execute natural language query"""
    logger.info(f"Received query: '{req.question}' for database: {database}")

    try:
        db_service = DatabaseService(database)
        result = db_service.ask_question(req.question, req.max_retry_attempts)

        if not result["ok"]:
            # Return error as successful HTTP response with error details
            # This allows the frontend to handle query errors gracefully
            error_response = {
                "ok": False,
                "error": result["error"],
                "error_type": result.get("error_type", "query_failed"),
                "suggestion": result.get("suggestion"),
                "query": result.get("query"),
                "database": database,
                "database_type": result.get("database_type"),
                "attempts": result.get("attempts", 0)
            }
            logger.info(f"Query validation failed: {result['error']}")
            return error_response

        query_result = result["result"]

        if req.as_table:
            # Return as markdown table
            md = render_markdown_result(
                result["query"],
                query_result["columns"],
                query_result["rows"]
            )
            db_info = f"**Database:** {database or 'default'} ({result.get('database_type', 'unknown')})\n\n"
            return Response(content=db_info + md, media_type="text/markdown")

        # Return JSON response for successful queries
        response_data = {
            "ok": True,
            "query": result["query"],
            "database": database,
            "database_type": result.get("database_type"),
            "rows": query_result["rows"],
            "row_count": query_result["row_count"],
            "columns": query_result["columns"],
            "insights": insight_bullets(query_result["columns"], query_result["rows"]),
            "attempts": result.get("attempts", 1),
            "parameters": result.get("parameters", [])
        }

        logger.info(f"Query successful: returned {query_result['row_count']} rows")
        return response_data

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=400, detail={
            "error": error_msg,
            "error_type": "validation_error",
            "debug_info": {
                "database": database,
                "question": getattr(req, 'question', 'unknown')
            }
        })
    except Exception as e:
        import traceback
        error_msg = f"Internal server error: {str(e)}"
        logger.error(f"Unexpected error processing query '{req.question}': {str(e)}", exc_info=True)

        raise HTTPException(status_code=500, detail={
            "error": error_msg,
            "error_type": "internal_error",
            "debug_info": {
                "database": database,
                "question": getattr(req, 'question', 'unknown')
            },
            "traceback": traceback.format_exc()
        })