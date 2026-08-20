# Multi-Agent Azure DevOps System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An AI-powered system that automates software development workflows by orchestrating specialized agents to transform Azure DevOps work items into tested, production-ready code with automated PR creation.

## Overview

This system uses multiple AI agents working together to:
1. Fetch work items from Azure DevOps  
2. Analyze requirements and create execution plans  
3. Generate implementation code matching your project's language and style  
4. Write unit tests  
5. Commit changes and create pull requests  

## Components

### Agents
- **Orchestrator Agent** - Fetches work items, analyzes requirements, creates detailed execution plans  
- **DevOps Agent** - Manages Git operations (branching, commits, push, PR creation)  
- **Code Agent** - Generates implementation code based on requirements and existing patterns  
- **Test Agent** - Generates unit and integration tests  

### Services
- **RAG System** - Indexes codebase to provide context-aware code generation  
- **MCP Manager** - Manages connections to Azure DevOps and filesystem MCP servers  
- **State Manager** - Saves/loads workflow state for cost-efficient testing  

## Setup

### Prerequisites
- Python 3.10+  
- Azure OpenAI API access  
- Azure DevOps account with PAT token  
- Node.js (for MCP servers)  


## Components

### Agents
- **Orchestrator Agent** - Fetches work items, analyzes requirements, creates detailed execution plans  
- **DevOps Agent** - Manages Git operations (branching, commits, push, PR creation)  
- **Code Agent** - Generates implementation code based on requirements and existing patterns  
- **Test Agent** - Generates unit and integration tests  

### Services
- **RAG System** - Indexes codebase to provide context-aware code generation  
- **MCP Manager** - Manages connections to Azure DevOps and filesystem MCP servers  
- **State Manager** - Saves/loads workflow state for cost-efficient testing  

## Setup

### Prerequisites
- Python 3.13+  
- Azure OpenAI API access  
- Azure DevOps account with PAT token  
- Node.js (for MCP servers)  

### Installation

    # Clone repository
    cd Agentic-AI-Azure-Devops

    # Create virtual environment
    python -m venv .venv
    source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

    # Install dependencies
    pip install -r requirements.txt

### Configuration
Create a `.env` file:

    # Azure AI
    AZURE_AI_ENDPOINT=your_endpoint
    AZURE_AI_KEY=your_key
    AZURE_AI_DEPLOYMENT=your_deployment_name
    AZURE_API_VERSION=your_deployment_version
    AZURE_AI_EMBEDDING_DEPLOYMENT=your_embedding_deployment_name

    # Azure DevOps
    AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your_org
    AZURE_DEVOPS_PAT=your_personal_access_token
    AZURE_DEVOPS_PROJECT=your_project_name

    # Repository (optional, defaults to current directory)
    REPOSITORY_PATH=/path/to/your/project
    AZURE_DEVOPS_REPOSITORY_ID=your_repo_id
## Usage

### Web UI (Recommended)

Start the web interface for an easy-to-use experience:

    ./start_ui.sh

Or manually:

    source venv/bin/activate
    python web_app.py

Then open your browser to `http://localhost:5001`

The Web UI provides:
- Clean, modern interface
- Real-time workflow output
- Visual phase indicators
- Progress tracking
- Automatic summary of results
- Pull request links

### Command Line

    python run_complete_workflow.py

This will:
- Fetch work item from Azure DevOps
- Analyze and create execution plan
- Create feature branch
- Generate all implementation files
- Generate test files
- Commit changes locally
- Push to remote
- Create pull request  

### Test Individual Agents (Cost Efficient)

    # Save initial state once (expensive)
    python run_complete_workflow.py

    # Manage saved states
    python manage_states.py list
    python manage_states.py delete state_name


## Key Features

### Flexible Validation
- Validates implementations against acceptance criteria
- Uses 80% threshold - workflow continues if 4 out of 5 criteria are met
- Allows partial criteria and test failures with warnings
- Doesn't block PR creation for minor issues
- All validation results included in PR for manual review

### State Management
- Saves workflow state at each phase
- Enables cheap iteration without re-running expensive operations
- Persists context across sessions

### RAG Integration
- Indexes existing codebase
- Provides relevant code patterns to agents
- Ensures generated code matches project style

### Multi-Agent Orchestration
- Each agent specializes in specific tasks
- Shared context enables agent coordination
- Modular architecture for easy extension  

## Limitations

### Current Issues
- **Language Detection** - May generate code in wrong language if work item is frontend-focused but project is backend (needs improvement)  
- **RAG** - Uses simple keyword search instead of semantic embeddings  
- **File Paths** - Requires proper MCP configuration for correct file placement  

### Cost Considerations
- Each full workflow run costs ~$0.50–2.00 in Azure OpenAI API calls  
- Use state management to avoid repeated expensive operations  
- Test with smaller work items first  

## Troubleshooting
- **Files created in wrong location** → Verify `REPOSITORY_PATH` in `.env`, run from correct directory  
- **Authentication errors** → Verify PAT token has required permissions, check Azure OpenAI credentials  
- **MCP connection failures** → Ensure Node.js is installed, MCP servers install automatically via `npx`  

## Future Enhancements
- Clean up + Generalization 
- Pull the code repo directly from Azure DevOps 
- Move agent interactions creation into docker
- Implement test driven development as an option
- Add LangGraph for complex workflow orchestration for better coordination between agents

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for the full text.

    MIT License

    Copyright (c) 2026 Jin Wu

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
