#!/bin/bash

# Startup script for Agentic AI Azure DevOps Web UI

echo "======================================"
echo "Agentic AI Azure DevOps - Web UI"
echo "======================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found!"
    echo "Please run: python -m venv venv"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found!"
    echo "Please create a .env file with your configuration."
    echo "See README.md for details."
    exit 1
fi

# Install/update dependencies
echo "Checking dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Starting web server..."
echo "======================================"
echo "Web UI will be available at:"
echo "  http://localhost:5001"
echo ""
echo "Press Ctrl+C to stop the server"
echo "======================================"
echo ""

# Start the web app
python web_app.py
