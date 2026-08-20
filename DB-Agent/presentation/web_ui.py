import os
from dotenv import load_dotenv

load_dotenv()


def get_demo_interface() -> str:
    """Generate the HTML for the interactive demo interface with database selection."""

    api_key = os.getenv("APP_API_KEY", "")

    if not api_key:
        return """
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 100px;">
            <h1 style="color: red;">Configuration Error</h1>
            <p>APP_API_KEY is not configured in environment variables.</p>
            <p>Please set APP_API_KEY in your .env file and restart the server.</p>
        </body>
        </html>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Multi-Database Query Agent</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/marked/4.3.0/marked.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github.min.css">
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; 
            max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa;
        }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .database-selector {{
            background: white; padding: 20px; border-radius: 8px; margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .database-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px; margin-top: 15px;
        }}
        .database-card {{
            border: 2px solid #e1e5e9; border-radius: 8px; padding: 15px;
            cursor: pointer; transition: all 0.3s; background: #fafbfc;
            margin-bottom: 8px;
        }}
        .database-card:hover {{
            border-color: #0066cc; background: #f0f7ff;
            transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }}
        .database-card.selected {{
            border-color: #0066cc; background: #e7f3ff;
            box-shadow: 0 0 0 3px rgba(0,102,204,0.2);
        }}
        .database-name {{
            font-weight: 600; font-size: 18px; margin-bottom: 5px;
            color: #0066cc;
        }}
        .database-type {{
            display: inline-block; padding: 3px 8px; border-radius: 12px;
            font-size: 12px; font-weight: 500; margin-bottom: 8px;
        }}
        .database-type.postgresql {{
            background: #336791; color: white;
        }}
        .database-type.mongodb {{
            background: #13aa52; color: white;
        }}
        .database-info {{
            color: #666; font-size: 14px; line-height: 1.4;
        }}
        .database-status {{
            margin-top: 8px; font-size: 12px;
        }}
        .status-connected {{ color: #13aa52; }}
        .status-error {{ color: #dc3545; }}
        .examples {{ 
            background: white; padding: 20px; border-radius: 8px; margin: 20px 0; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .input-section {{ 
            background: white; padding: 20px; border-radius: 8px; margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .selected-db-indicator {{
            background: #e7f3ff; padding: 10px 15px; border-radius: 6px;
            margin-bottom: 15px; display: none; align-items: center; gap: 10px;
        }}
        .selected-db-indicator.visible {{ display: flex; }}
        .chat {{ 
            background: white; border-radius: 8px; height: 500px; 
            padding: 20px; overflow-y: auto; margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .input-row {{ display: flex; gap: 10px; align-items: center; }}
        #question {{ 
            flex: 1; padding: 12px; border: 2px solid #e1e5e9; border-radius: 6px;
            font-size: 16px; outline: none;
        }}
        #question:focus {{ border-color: #0066cc; }}
        #question:disabled {{ background: #f5f5f5; cursor: not-allowed; }}
        button {{ 
            padding: 12px 24px; background: #0066cc; color: white; border: none;
            border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: 600;
            transition: background 0.2s;
        }}
        button:hover:not(:disabled) {{ background: #0052a3; }}
        button:disabled {{ background: #ccc; cursor: not-allowed; }}
        .user-message {{ 
            background: #0066cc; color: white; padding: 12px 16px; 
            margin: 10px 0; border-radius: 18px 18px 4px 18px; max-width: 80%;
            word-wrap: break-word;
        }}
        .agent-message {{ 
            background: #f1f3f5; padding: 16px; margin: 10px 0; 
            border-radius: 18px 18px 18px 4px; max-width: 90%;
            word-wrap: break-word;
        }}
        .loading {{ 
            background: #fff3cd; padding: 12px; border-radius: 8px; 
            border-left: 4px solid #ffc107; margin: 10px 0;
        }}
        .error {{ 
            background: #f8d7da; padding: 16px; border-radius: 8px; 
            border-left: 4px solid #dc3545; margin: 10px 0; color: #721c24;
        }}
        .error-details {{
            background: #f8f9fa; padding: 12px; border-radius: 4px;
            margin-top: 10px; font-family: monospace; font-size: 12px;
            border: 1px solid #e1e5e9; white-space: pre-wrap;
            max-height: 300px; overflow-y: auto;
        }}
        .error-summary {{
            font-weight: bold; margin-bottom: 10px;
        }}
        .error-expandable {{
            cursor: pointer; color: #0066cc; text-decoration: underline;
            font-size: 12px; margin-top: 8px;
        }}
        .error-expandable:hover {{ color: #0052a3; }}
        .query-error {{
            background: #fff3cd; padding: 15px; border-radius: 8px; 
            border-left: 4px solid #ffc107; margin: 15px 0; color: #856404;
        }}
        table {{ 
            width: 100%; border-collapse: collapse; margin: 15px 0; 
            background: white; border-radius: 6px; overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{ 
            padding: 10px 12px; text-align: left; border-bottom: 1px solid #e1e5e9; 
            word-wrap: break-word;
        }}
        th {{ background: #f8f9fa; font-weight: 600; color: #495057; }}
        tr:hover {{ background: #f8f9fa; }}
        code {{ 
            background: #f1f3f5; padding: 2px 6px; border-radius: 4px; 
            font-family: 'Monaco', 'Consolas', monospace; font-size: 14px;
        }}
        pre {{ 
            background: #f8f9fa; padding: 16px; border-radius: 6px; 
            overflow-x: auto; border: 1px solid #e1e5e9; margin: 15px 0;
            white-space: pre-wrap; line-height: 1.5;
        }}
        pre code {{
            background: transparent; padding: 0; border-radius: 0;
            white-space: pre-wrap; word-wrap: break-word;
        }}
        .example-btn {{
            background: #f8f9fa; border: 1px solid #e1e5e9; padding: 8px 12px;
            border-radius: 20px; cursor: pointer; margin: 4px; display: inline-block;
            font-size: 14px; color: #495057; transition: all 0.2s;
        }}
        .example-btn:hover {{ background: #e9ecef; transform: translateY(-1px); }}
        h3 {{ color: #0066cc; margin: 20px 0 10px 0; }}
        h4 {{ color: #333; margin: 15px 0 8px 0; }}
        ul {{ margin: 10px 0; padding-left: 20px; }}
        li {{ margin: 5px 0; }}
        .no-database-warning {{
            background: #fff3cd; padding: 15px; border-radius: 8px;
            border-left: 4px solid #ffc107; margin: 20px 0;
            display: none;
        }}
        .no-database-warning.visible {{ display: block; }}
        .refresh-btn {{
            background: #28a745; padding: 8px 16px; font-size: 14px;
            margin-left: 10px;
        }}
        .refresh-btn:hover {{ background: #218838; }}
        .json-result {{
            background: #f8f9fa; border: 1px solid #e1e5e9; border-radius: 6px;
            padding: 16px; margin: 15px 0; overflow-x: auto;
            font-family: 'Monaco', 'Consolas', monospace; font-size: 13px;
            white-space: pre-wrap; max-height: 400px; overflow-y: auto;
            line-height: 1.4;
        }}
        .mongo-query {{
            background: #e8f5e8; border: 1px solid #13aa52; border-radius: 6px;
            padding: 16px; margin: 15px 0; font-family: 'Monaco', 'Consolas', monospace;
            font-size: 14px; white-space: pre-wrap;
        }}
        .sql-query {{
            background: #e6f3ff; border: 1px solid #336791; border-radius: 6px;
            padding: 16px; margin: 15px 0; font-family: 'Monaco', 'Consolas', monospace;
            font-size: 14px; white-space: pre-wrap;
        }}
        .tips-section {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 20px; border-radius: 8px; margin: 20px 0;
        }}
        .tips-section h3 {{ color: white; margin-top: 0; }}
        .tip-item {{ 
            background: rgba(255,255,255,0.1); padding: 10px; border-radius: 6px; 
            margin: 8px 0; font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Multi-Database Query Agent</h1>
        <p>Select a database and ask questions in natural language!</p>
    </div>

    <div class="database-selector">
        <h3>📊 Available Databases</h3>
        <div id="database-grid" class="database-grid">
            <!-- Databases will be loaded here -->
        </div>
        <button class="refresh-btn" onclick="loadDatabases()">🔄 Refresh Databases</button>
    </div>

    <div class="no-database-warning" id="no-database-warning">
        Please select a database first before asking questions.
    </div>

    <div class="tips-section">
        <h3>Query Guidelines</h3>
        <div class="tip-item">This system is read-only - ask questions to retrieve and analyze data</div>
        <div class="tip-item">Write operations (INSERT, UPDATE, DELETE) are not allowed</div>
        <div class="tip-item">Use phrases like "show me", "find", "count", "list", "get", "analyze"</div>
        <div class="tip-item">Be specific about what data you want to see</div>
    </div>

    <div class="examples">
        <h3>Try these examples:</h3>
        <div class="example-btn" onclick="setQuestion('Show me 5 records')">Show me 5 records</div>
        <div class="example-btn" onclick="setQuestion('What are the most common categories?')">What are the most common categories?</div>
        <div class="example-btn" onclick="setQuestion('Count records by type')">Count records by type</div>
        <div class="example-btn" onclick="setQuestion('Find records from 2020')">Find records from 2020</div>
    </div>

    <div class="input-section">
        <div class="selected-db-indicator" id="selected-db-indicator">
            <strong>Selected Database:</strong>
            <span id="selected-db-name"></span>
            <span id="selected-db-type"></span>
        </div>
        <div class="input-row">
            <input type="text" id="question" placeholder="Select a database first, then ask a question..." disabled />
            <button id="ask-btn" onclick="askQuestion()" disabled>Ask</button>
        </div>
    </div>

    <div id="chat" class="chat"></div>

    <script>
        let selectedDatabase = null;
        let availableDatabases = [];
        let isProcessing = false;

        // Get API key from server configuration
        const API_KEY = '{api_key}';

        // Load databases on page load
        window.onload = function() {{
            loadDatabases();
        }};

        function createErrorDiv(message, details = null, isExpandable = false) {{
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error';

            let content = `<div class="error-summary">⚠️ Error: ${{escapeHtml(message)}}</div>`;

            if (details) {{
                if (isExpandable) {{
                    const detailsId = 'error-details-' + Date.now();
                    content += `
                        <div class="error-expandable" onclick="toggleErrorDetails('${{detailsId}}')">
                            Click to show technical details
                        </div>
                        <div id="${{detailsId}}" class="error-details" style="display: none;">
                            ${{escapeHtml(details)}}
                        </div>
                    `;
                }} else {{
                    content += `<div class="error-details">${{escapeHtml(details)}}</div>`;
                }}
            }}

            errorDiv.innerHTML = content;
            return errorDiv;
        }}

        function toggleErrorDetails(detailsId) {{
            const details = document.getElementById(detailsId);
            const toggle = details.previousElementSibling;

            if (details.style.display === 'none') {{
                details.style.display = 'block';
                toggle.textContent = 'Click to hide technical details';
            }} else {{
                details.style.display = 'none';
                toggle.textContent = 'Click to show technical details';
            }}
        }}

        function setLoadingState(loading) {{
            isProcessing = loading;
            const askBtn = document.getElementById('ask-btn');
            const questionInput = document.getElementById('question');

            if (loading) {{
                askBtn.disabled = true;
                askBtn.textContent = 'Processing...';
                questionInput.disabled = true;
            }} else {{
                askBtn.disabled = !selectedDatabase;
                askBtn.textContent = 'Ask';
                questionInput.disabled = !selectedDatabase;
            }}
        }}

        async function loadDatabases() {{
            const grid = document.getElementById('database-grid');
            grid.innerHTML = '<div style="text-align: center; width: 100%;">Loading databases...</div>';

            try {{
                const response = await fetch('/databases', {{
                    headers: {{
                        'x-api-key': API_KEY
                    }}
                }});

                if (!response.ok) {{
                    const errorText = await response.text();
                    throw new Error(`HTTP ${{response.status}}: ${{errorText}}`);
                }}

                const data = await response.json();
                availableDatabases = data.databases;

                // Check health of each database
                const healthPromises = availableDatabases.map(db => 
                    checkDatabaseHealth(db.name).then(health => ({{
                        ...db,
                        health: health
                    }}))
                );

                const databasesWithHealth = await Promise.all(healthPromises);
                displayDatabases(databasesWithHealth);

            }} catch (error) {{
                console.error('Error loading databases:', error);
                grid.innerHTML = `<div style="color: red; text-align: center; width: 100%;">Error loading databases: ${{escapeHtml(error.message)}}</div>`;
            }}
        }}

        async function checkDatabaseHealth(dbName) {{
            try {{
                const response = await fetch(`/health?database=${{dbName}}`, {{
                    headers: {{
                        'x-api-key': API_KEY
                    }}
                }});
                const data = await response.json();
                return data.ok ? 'connected' : 'error';
            }} catch (error) {{
                console.error(`Health check failed for ${{dbName}}:`, error);
                return 'error';
            }}
        }}

        function displayDatabases(databases) {{
            const grid = document.getElementById('database-grid');

            if (!databases || databases.length === 0) {{
                grid.innerHTML = '<div style="text-align: center; width: 100%;">No databases configured</div>';
                return;
            }}

            grid.innerHTML = databases.map(db => {{
                const typeClass = db.type === 'mongodb' ? 'mongodb' : 'postgresql';
                const statusClass = db.health === 'connected' ? 'status-connected' : 'status-error';
                const statusIcon = db.health === 'connected' ? '✅' : '❌';
                const statusText = db.health === 'connected' ? 'Connected' : 'Connection Error';

                return `
                    <div class="database-card" onclick="selectDatabase('${{db.name}}')" data-db-name="${{db.name}}">
                        <div class="database-name">${{db.name}}</div>
                        <span class="database-type ${{typeClass}}">${{db.type.toUpperCase()}}</span>
                        <div class="database-info">
                            ${{db.description || 'No description available'}}
                            ${{db.table ? `<br><strong>Table:</strong> ${{db.table}}` : ''}}
                            ${{db.collection ? `<br><strong>Collection:</strong> ${{db.collection}}` : ''}}
                        </div>
                        <div class="database-status ${{statusClass}}">
                            ${{statusIcon}} ${{statusText}}
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function selectDatabase(dbName) {{
            if (isProcessing) return; // Prevent database selection while processing

            selectedDatabase = dbName;

            document.querySelectorAll('.database-card').forEach(card => {{
                if (card.dataset.dbName === dbName) {{
                    card.classList.add('selected');
                }} else {{
                    card.classList.remove('selected');
                }}
            }});

            const db = availableDatabases.find(d => d.name === dbName);

            const indicator = document.getElementById('selected-db-indicator');
            const nameSpan = document.getElementById('selected-db-name');
            const typeSpan = document.getElementById('selected-db-type');

            nameSpan.textContent = dbName;
            typeSpan.textContent = `(${{db.type}})`;
            typeSpan.className = `database-type ${{db.type}}`;
            indicator.classList.add('visible');

            document.getElementById('question').disabled = false;
            document.getElementById('question').placeholder = `Ask anything about the ${{dbName}} database...`;
            document.getElementById('ask-btn').disabled = false;

            document.getElementById('no-database-warning').classList.remove('visible');
            document.getElementById('question').focus();
        }}

        function setQuestion(text) {{
            if (!selectedDatabase || isProcessing) {{
                if (!selectedDatabase) {{
                    document.getElementById('no-database-warning').classList.add('visible');
                }}
                return;
            }}
            document.getElementById('question').value = text;
            document.getElementById('question').focus();
        }}

        async function askQuestion() {{
            if (!selectedDatabase || isProcessing) {{
                if (!selectedDatabase) {{
                    document.getElementById('no-database-warning').classList.add('visible');
                }}
                return;
            }}

            const question = document.getElementById('question').value.trim();
            if (!question) return;

            const chat = document.getElementById('chat');
            chat.innerHTML += `<div class="user-message"><strong>You:</strong> ${{escapeHtml(question)}}</div>`;

            const selectedDb = availableDatabases.find(d => d.name === selectedDatabase);
            const queryType = selectedDb.type === 'mongodb' ? 'MongoDB pipeline' : 'SQL';

            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading';
            loadingDiv.innerHTML = `🤖 Agent is analyzing your question and generating ${{queryType}}...`;
            chat.appendChild(loadingDiv);
            chat.scrollTop = chat.scrollHeight;

            // Set loading state - disable button and input
            setLoadingState(true);

            try {{
                const response = await fetch(`/ask?database=${{selectedDatabase}}`, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'x-api-key': API_KEY
                    }},
                    body: JSON.stringify({{
                        question: question, 
                        as_table: selectedDb.type === 'postgresql'
                    }})
                }});

                loadingDiv.remove();

                if (response.ok) {{
                    const selectedDb = availableDatabases.find(d => d.name === selectedDatabase);

                    if (selectedDb.type === 'postgresql' && response.headers.get('content-type')?.includes('text/markdown')) {{
                        // Handle PostgreSQL markdown response
                        const markdownResult = await response.text();
                        const resultDiv = document.createElement('div');

                        marked.setOptions({{
                            highlight: function(code, lang) {{
                                if (lang && hljs.getLanguage(lang)) {{
                                    return hljs.highlight(code, {{language: lang}}).value;
                                }}
                                return hljs.highlightAuto(code).value;
                            }}
                        }});

                        resultDiv.className = 'agent-message';
                        resultDiv.innerHTML = `<strong>🤖 Agent:</strong><br><br>${{marked.parse(markdownResult)}}`;
                        chat.appendChild(resultDiv);
                    }} else {{
                        // Handle JSON response
                        const result = await response.json();
                        const resultDiv = document.createElement('div');
                        resultDiv.className = 'agent-message';

                        let content = '<strong>🤖 Agent:</strong><br><br>';

                        // Check if the result contains an error (even with 200 status)
                        if (result.error || !result.ok) {{
                            // Display error message instead of query results
                            content += `<div class="query-error">`;
                            content += `<div style="font-weight: bold; margin-bottom: 8px;">❌ ${{escapeHtml(result.error || 'Query failed')}}</div>`;

                            if (result.suggestion) {{
                                content += `<div style="margin-top: 10px;"><strong>💡 Suggestion:</strong> ${{escapeHtml(result.suggestion)}}</div>`;
                            }}

                            if (result.error_type) {{
                                content += `<div style="margin-top: 8px; font-size: 12px; color: #856404;">Error type: ${{escapeHtml(result.error_type)}}</div>`;
                            }}
                            content += `</div>`;
                        }} else {{
                            // Handle successful query results
                            if (result.database_type === 'mongodb') {{
                                content += '<h4>MongoDB Aggregation Pipeline:</h4>';
                                content += `<div class="mongo-query">${{escapeHtml(result.query)}}</div>`;
                                content += `<h4>Result (${{result.row_count}} document${{result.row_count !== 1 ? 's' : ''}}):</h4>`;
                                content += `<div class="json-result">${{escapeHtml(JSON.stringify(result.rows, null, 2))}}</div>`;
                            }} else {{
                                content += '<h4>SQL Query:</h4>';
                                content += `<div class="sql-query">${{escapeHtml(result.query)}}</div>`;
                                content += '<h4>Result (JSON):</h4>';
                                content += `<div class="json-result">${{escapeHtml(JSON.stringify(result.rows, null, 2))}}</div>`;
                            }}

                            if (result.insights && result.insights.length > 0) {{
                                content += '<h4>Insights:</h4><ul>';
                                result.insights.forEach(insight => {{
                                    content += `<li>${{escapeHtml(insight)}}</li>`;
                                }});
                                content += '</ul>';
                            }}
                        }}

                        resultDiv.innerHTML = content;
                        chat.appendChild(resultDiv);
                    }}
                }} else {{
                    // Enhanced error handling for HTTP errors
                    const errorText = await response.text();
                    console.error('Error response:', {{status: response.status, text: errorText}});

                    let errorDiv;

                    try {{
                        const errorJson = JSON.parse(errorText);
                        let errorMessage = 'Unknown error occurred';
                        let details = null;

                        if (typeof errorJson.detail === 'object') {{
                            errorMessage = errorJson.detail.error || errorJson.detail.message || 'Server error';

                            let detailParts = [];
                            if (errorJson.detail.error_type) {{
                                detailParts.push(`Error Type: ${{errorJson.detail.error_type}}`);
                            }}
                            if (errorJson.detail.debug_info) {{
                                detailParts.push(`Debug Info: ${{JSON.stringify(errorJson.detail.debug_info, null, 2)}}`);
                            }}
                            if (errorJson.detail.traceback) {{
                                detailParts.push(`Traceback:\\n${{errorJson.detail.traceback}}`);
                            }}
                            if (detailParts.length > 0) {{
                                details = detailParts.join('\\n\\n');
                            }}
                        }} else if (typeof errorJson.detail === 'string') {{
                            errorMessage = errorJson.detail;
                        }} else if (errorJson.error) {{
                            errorMessage = errorJson.error;

                            let detailParts = [];
                            if (errorJson.query) {{
                                detailParts.push(`Generated Query:\\n${{errorJson.query}}`);
                            }}
                            if (errorJson.debug_info) {{
                                detailParts.push(`Debug Info:\\n${{JSON.stringify(errorJson.debug_info, null, 2)}}`);
                            }}
                            if (errorJson.attempts) {{
                                detailParts.push(`Retry Attempts: ${{errorJson.attempts}}`);
                            }}
                            if (detailParts.length > 0) {{
                                details = detailParts.join('\\n\\n');
                            }}
                        }}

                        errorDiv = createErrorDiv(errorMessage, details, details && details.length > 200);
                    }} catch (parseError) {{
                        console.error('Failed to parse error response:', parseError);
                        const details = `Raw Response (HTTP ${{response.status}}):\\n${{errorText}}\\n\\nJSON Parse Error:\\n${{parseError.message}}`;
                        errorDiv = createErrorDiv('Server response could not be parsed', details, true);
                    }}

                    chat.appendChild(errorDiv);
                }}

                chat.scrollTop = chat.scrollHeight;
                document.getElementById('question').value = '';

            }} catch (error) {{
                loadingDiv.remove();
                console.error('Network error:', error);

                const details = `Request Details:\\nURL: /ask?database=${{selectedDatabase}}\\nMethod: POST\\nError: ${{error.message}}\\n\\nThis usually indicates a network connectivity issue or the server is not responding.`;
                const errorDiv = createErrorDiv('Network connection failed', details, true);
                chat.appendChild(errorDiv);
                chat.scrollTop = chat.scrollHeight;
            }} finally {{
                // Always re-enable the button and input after processing
                setLoadingState(false);
            }}
        }}

        function escapeHtml(unsafe) {{
            if (typeof unsafe !== 'string') {{
                unsafe = String(unsafe);
            }}
            return unsafe
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }}

        document.getElementById('question').addEventListener('keypress', function(e) {{
            if (e.key === 'Enter' && !e.shiftKey && !isProcessing) {{
                e.preventDefault();
                askQuestion();
            }}
        }});
    </script>
</body>
</html>"""