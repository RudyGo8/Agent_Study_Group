"""
Tool Knowledge Base - Simulates MCP servers with various tools.

This module defines a comprehensive knowledge base of tools organized by domains (servers),
similar to the MCP (Model Context Protocol) ecosystem. Each server represents a platform
or service domain with specific tools.
"""

from typing import List, Dict, Any


class ToolDefinition:
    """Represents a single tool with its metadata."""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], server: str):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.server = server
    
    def to_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function schema format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    def __repr__(self):
        return f"Tool(name={self.name}, server={self.server})"


class ServerDefinition:
    """Represents a server (domain) containing multiple tools."""
    
    def __init__(self, name: str, description: str, tools: List[ToolDefinition]):
        self.name = name
        self.description = description
        self.tools = tools
    
    def __repr__(self):
        return f"Server(name={self.name}, tools={len(self.tools)})"


# Define comprehensive tool knowledge base
def create_tool_knowledge_base() -> List[ServerDefinition]:
    """
    Create a comprehensive tool knowledge base organized by servers.
    
    This simulates the MCP ecosystem with multiple domains:
    - GitHub: Repository management and code operations
    - Filesystem: File system operations
    - Database: Data storage and retrieval
    - Web: HTTP requests and web scraping
    - Analytics: Data analysis and visualization
    - Communication: Email and messaging
    - DevOps: Deployment and monitoring
    - Cloud: Cloud service operations
    """
    
    servers = []
    
    # GitHub Server
    github_tools = [
        ToolDefinition(
            name="github_search_repos",
            description="Search for GitHub repositories using keywords, filters, and sorting options",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g., 'language:python stars:>1000')"},
                    "sort": {"type": "string", "enum": ["stars", "forks", "updated"], "description": "Sort by field"},
                    "per_page": {"type": "integer", "description": "Results per page (max 100)"}
                },
                "required": ["query"]
            },
            server="github"
        ),
        ToolDefinition(
            name="github_create_pr",
            description="Create a pull request in a GitHub repository",
            parameters={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name (owner/repo)"},
                    "title": {"type": "string", "description": "PR title"},
                    "body": {"type": "string", "description": "PR description"},
                    "head": {"type": "string", "description": "Branch to merge from"},
                    "base": {"type": "string", "description": "Branch to merge into"}
                },
                "required": ["repo", "title", "head", "base"]
            },
            server="github"
        ),
        ToolDefinition(
            name="github_list_issues",
            description="List issues in a GitHub repository with filtering options",
            parameters={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name (owner/repo)"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "Issue state"},
                    "labels": {"type": "array", "items": {"type": "string"}, "description": "Filter by labels"}
                },
                "required": ["repo"]
            },
            server="github"
        ),
        ToolDefinition(
            name="github_get_file",
            description="Get contents of a file from a GitHub repository",
            parameters={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name (owner/repo)"},
                    "path": {"type": "string", "description": "File path in repository"},
                    "branch": {"type": "string", "description": "Branch name (default: main)"}
                },
                "required": ["repo", "path"]
            },
            server="github"
        ),
        ToolDefinition(
            name="github_create_issue",
            description="Create a new issue in a GitHub repository",
            parameters={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name (owner/repo)"},
                    "title": {"type": "string", "description": "Issue title"},
                    "body": {"type": "string", "description": "Issue description"},
                    "labels": {"type": "array", "items": {"type": "string"}, "description": "Issue labels"}
                },
                "required": ["repo", "title"]
            },
            server="github"
        )
    ]
    servers.append(ServerDefinition("github", "GitHub repository management and version control operations", github_tools))
    
    # Filesystem Server
    filesystem_tools = [
        ToolDefinition(
            name="fs_read_file",
            description="Read the contents of a file from the local filesystem",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "encoding": {"type": "string", "description": "File encoding (default: utf-8)"}
                },
                "required": ["path"]
            },
            server="filesystem"
        ),
        ToolDefinition(
            name="fs_write_file",
            description="Write content to a file in the local filesystem",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                    "mode": {"type": "string", "enum": ["w", "a"], "description": "Write mode (w=overwrite, a=append)"}
                },
                "required": ["path", "content"]
            },
            server="filesystem"
        ),
        ToolDefinition(
            name="fs_list_directory",
            description="List files and directories in a given path",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list"},
                    "recursive": {"type": "boolean", "description": "List recursively"},
                    "pattern": {"type": "string", "description": "File pattern filter (e.g., '*.py')"}
                },
                "required": ["path"]
            },
            server="filesystem"
        ),
        ToolDefinition(
            name="fs_delete_file",
            description="Delete a file or directory from the filesystem",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete"},
                    "recursive": {"type": "boolean", "description": "Delete directories recursively"}
                },
                "required": ["path"]
            },
            server="filesystem"
        ),
        ToolDefinition(
            name="fs_search_files",
            description="Search for files containing specific text or matching patterns",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search in"},
                    "query": {"type": "string", "description": "Text to search for"},
                    "file_pattern": {"type": "string", "description": "File pattern (e.g., '*.py')"}
                },
                "required": ["path", "query"]
            },
            server="filesystem"
        )
    ]
    servers.append(ServerDefinition("filesystem", "Local filesystem operations for reading, writing, and managing files", filesystem_tools))
    
    # Database Server
    database_tools = [
        ToolDefinition(
            name="db_query",
            description="Execute a SQL query on the database and return results",
            parameters={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute"},
                    "database": {"type": "string", "description": "Database name"},
                    "timeout": {"type": "integer", "description": "Query timeout in seconds"}
                },
                "required": ["sql"]
            },
            server="database"
        ),
        ToolDefinition(
            name="db_insert",
            description="Insert data into a database table",
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "data": {"type": "object", "description": "Data to insert as key-value pairs"},
                    "database": {"type": "string", "description": "Database name"}
                },
                "required": ["table", "data"]
            },
            server="database"
        ),
        ToolDefinition(
            name="db_update",
            description="Update records in a database table",
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "data": {"type": "object", "description": "Data to update"},
                    "where": {"type": "string", "description": "WHERE clause condition"},
                    "database": {"type": "string", "description": "Database name"}
                },
                "required": ["table", "data", "where"]
            },
            server="database"
        ),
        ToolDefinition(
            name="db_delete",
            description="Delete records from a database table",
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "where": {"type": "string", "description": "WHERE clause condition"},
                    "database": {"type": "string", "description": "Database name"}
                },
                "required": ["table", "where"]
            },
            server="database"
        ),
        ToolDefinition(
            name="db_schema",
            description="Get schema information for database tables",
            parameters={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name (optional, returns all if omitted)"},
                    "database": {"type": "string", "description": "Database name"}
                },
                "required": []
            },
            server="database"
        )
    ]
    servers.append(ServerDefinition("database", "Database operations for querying and manipulating structured data", database_tools))
    
    # Web Server
    web_tools = [
        ToolDefinition(
            name="web_get",
            description="Make HTTP GET request to a URL and return the response",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request"},
                    "headers": {"type": "object", "description": "HTTP headers"},
                    "params": {"type": "object", "description": "Query parameters"}
                },
                "required": ["url"]
            },
            server="web"
        ),
        ToolDefinition(
            name="web_post",
            description="Make HTTP POST request to a URL with data",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to post to"},
                    "data": {"type": "object", "description": "Data to send"},
                    "headers": {"type": "object", "description": "HTTP headers"}
                },
                "required": ["url", "data"]
            },
            server="web"
        ),
        ToolDefinition(
            name="web_scrape",
            description="Scrape and extract data from a web page using CSS selectors",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape"},
                    "selector": {"type": "string", "description": "CSS selector for elements to extract"},
                    "attributes": {"type": "array", "items": {"type": "string"}, "description": "Attributes to extract"}
                },
                "required": ["url", "selector"]
            },
            server="web"
        ),
        ToolDefinition(
            name="web_download",
            description="Download a file from a URL to local filesystem",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to download from"},
                    "destination": {"type": "string", "description": "Local path to save file"},
                    "headers": {"type": "object", "description": "HTTP headers"}
                },
                "required": ["url", "destination"]
            },
            server="web"
        )
    ]
    servers.append(ServerDefinition("web", "HTTP operations for making requests and scraping web content", web_tools))
    
    # Analytics Server
    analytics_tools = [
        ToolDefinition(
            name="analytics_summarize",
            description="Calculate summary statistics for a dataset",
            parameters={
                "type": "object",
                "properties": {
                    "data": {"type": "array", "description": "Array of numeric values"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "Metrics to calculate (mean, median, std, etc.)"}
                },
                "required": ["data"]
            },
            server="analytics"
        ),
        ToolDefinition(
            name="analytics_visualize",
            description="Create visualizations from data (charts, graphs)",
            parameters={
                "type": "object",
                "properties": {
                    "data": {"type": "object", "description": "Data to visualize"},
                    "chart_type": {"type": "string", "enum": ["line", "bar", "scatter", "pie"], "description": "Type of chart"},
                    "title": {"type": "string", "description": "Chart title"},
                    "output_path": {"type": "string", "description": "Path to save chart image"}
                },
                "required": ["data", "chart_type"]
            },
            server="analytics"
        ),
        ToolDefinition(
            name="analytics_correlation",
            description="Calculate correlation between variables in a dataset",
            parameters={
                "type": "object",
                "properties": {
                    "data": {"type": "object", "description": "Dataset with variables as keys"},
                    "method": {"type": "string", "enum": ["pearson", "spearman"], "description": "Correlation method"}
                },
                "required": ["data"]
            },
            server="analytics"
        ),
        ToolDefinition(
            name="analytics_predict",
            description="Make predictions using machine learning models",
            parameters={
                "type": "object",
                "properties": {
                    "model_type": {"type": "string", "description": "Type of ML model (linear, tree, etc.)"},
                    "features": {"type": "array", "description": "Feature values for prediction"},
                    "trained_model_path": {"type": "string", "description": "Path to trained model file"}
                },
                "required": ["features"]
            },
            server="analytics"
        )
    ]
    servers.append(ServerDefinition("analytics", "Data analysis and visualization tools for statistical operations", analytics_tools))
    
    # Communication Server
    communication_tools = [
        ToolDefinition(
            name="comm_send_email",
            description="Send an email message to recipients",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "array", "items": {"type": "string"}, "description": "Recipient email addresses"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body content"},
                    "attachments": {"type": "array", "items": {"type": "string"}, "description": "File paths to attach"}
                },
                "required": ["to", "subject", "body"]
            },
            server="communication"
        ),
        ToolDefinition(
            name="comm_send_slack",
            description="Send a message to a Slack channel or user",
            parameters={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name or user ID"},
                    "message": {"type": "string", "description": "Message content"},
                    "thread_ts": {"type": "string", "description": "Thread timestamp for replies"}
                },
                "required": ["channel", "message"]
            },
            server="communication"
        ),
        ToolDefinition(
            name="comm_read_email",
            description="Read emails from inbox with filtering options",
            parameters={
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "description": "Email folder (inbox, sent, etc.)"},
                    "unread_only": {"type": "boolean", "description": "Only return unread emails"},
                    "limit": {"type": "integer", "description": "Maximum number of emails to return"}
                },
                "required": []
            },
            server="communication"
        ),
        ToolDefinition(
            name="comm_schedule_meeting",
            description="Schedule a meeting in calendar",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Meeting title"},
                    "start_time": {"type": "string", "description": "Start time (ISO format)"},
                    "duration": {"type": "integer", "description": "Duration in minutes"},
                    "attendees": {"type": "array", "items": {"type": "string"}, "description": "Attendee emails"}
                },
                "required": ["title", "start_time", "attendees"]
            },
            server="communication"
        )
    ]
    servers.append(ServerDefinition("communication", "Email, messaging, and calendar tools for communication", communication_tools))
    
    # DevOps Server
    devops_tools = [
        ToolDefinition(
            name="devops_deploy",
            description="Deploy application to specified environment",
            parameters={
                "type": "object",
                "properties": {
                    "environment": {"type": "string", "enum": ["dev", "staging", "production"], "description": "Target environment"},
                    "version": {"type": "string", "description": "Version to deploy"},
                    "rollback": {"type": "boolean", "description": "Enable auto-rollback on failure"}
                },
                "required": ["environment", "version"]
            },
            server="devops"
        ),
        ToolDefinition(
            name="devops_monitor",
            description="Get monitoring metrics for services and infrastructure",
            parameters={
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name to monitor"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "Metrics to retrieve (cpu, memory, etc.)"},
                    "timerange": {"type": "string", "description": "Time range (e.g., '1h', '24h')"}
                },
                "required": ["service"]
            },
            server="devops"
        ),
        ToolDefinition(
            name="devops_logs",
            description="Query and filter application logs",
            parameters={
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name"},
                    "level": {"type": "string", "enum": ["debug", "info", "warning", "error"], "description": "Log level filter"},
                    "query": {"type": "string", "description": "Text to search in logs"},
                    "limit": {"type": "integer", "description": "Maximum number of log entries"}
                },
                "required": ["service"]
            },
            server="devops"
        ),
        ToolDefinition(
            name="devops_run_pipeline",
            description="Trigger a CI/CD pipeline execution",
            parameters={
                "type": "object",
                "properties": {
                    "pipeline": {"type": "string", "description": "Pipeline name or ID"},
                    "branch": {"type": "string", "description": "Git branch to build"},
                    "parameters": {"type": "object", "description": "Pipeline parameters"}
                },
                "required": ["pipeline"]
            },
            server="devops"
        )
    ]
    servers.append(ServerDefinition("devops", "DevOps tools for deployment, monitoring, and CI/CD operations", devops_tools))
    
    # Cloud Server
    cloud_tools = [
        ToolDefinition(
            name="cloud_create_vm",
            description="Create a virtual machine in the cloud",
            parameters={
                "type": "object",
                "properties": {
                    "instance_type": {"type": "string", "description": "VM instance type (e.g., 't2.micro')"},
                    "region": {"type": "string", "description": "Cloud region"},
                    "image_id": {"type": "string", "description": "OS image ID"},
                    "tags": {"type": "object", "description": "Tags for the VM"}
                },
                "required": ["instance_type", "region"]
            },
            server="cloud"
        ),
        ToolDefinition(
            name="cloud_list_resources",
            description="List cloud resources (VMs, storage, databases)",
            parameters={
                "type": "object",
                "properties": {
                    "resource_type": {"type": "string", "enum": ["vm", "storage", "database", "network"], "description": "Type of resource"},
                    "region": {"type": "string", "description": "Cloud region"},
                    "filters": {"type": "object", "description": "Filter criteria"}
                },
                "required": ["resource_type"]
            },
            server="cloud"
        ),
        ToolDefinition(
            name="cloud_upload_storage",
            description="Upload files to cloud storage",
            parameters={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string", "description": "Storage bucket name"},
                    "file_path": {"type": "string", "description": "Local file path"},
                    "destination": {"type": "string", "description": "Destination path in bucket"},
                    "public": {"type": "boolean", "description": "Make file publicly accessible"}
                },
                "required": ["bucket", "file_path"]
            },
            server="cloud"
        ),
        ToolDefinition(
            name="cloud_manage_firewall",
            description="Configure cloud firewall rules",
            parameters={
                "type": "object",
                "properties": {
                    "resource_id": {"type": "string", "description": "Resource ID to configure"},
                    "action": {"type": "string", "enum": ["add", "remove"], "description": "Action to perform"},
                    "rule": {"type": "object", "description": "Firewall rule specification"}
                },
                "required": ["resource_id", "action", "rule"]
            },
            server="cloud"
        )
    ]
    servers.append(ServerDefinition("cloud", "Cloud infrastructure management for VMs, storage, and networking", cloud_tools))
    
    return servers


def get_all_tools(servers: List[ServerDefinition]) -> List[ToolDefinition]:
    """Get flat list of all tools from all servers."""
    all_tools = []
    for server in servers:
        all_tools.extend(server.tools)
    return all_tools


def count_tokens_in_schema(schema: Dict[str, Any]) -> int:
    """Rough estimation of tokens in a tool schema (approximately 1 token per 4 characters)."""
    import json
    schema_str = json.dumps(schema)
    return len(schema_str) // 4


def calculate_total_tokens(tools: List[ToolDefinition]) -> int:
    """Calculate total tokens required to inject all tool schemas."""
    total = 0
    for tool in tools:
        total += count_tokens_in_schema(tool.to_schema())
    return total
