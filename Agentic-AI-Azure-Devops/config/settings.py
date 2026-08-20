import os
from dotenv import load_dotenv

load_dotenv()


class SystemConfig:
    """System configuration"""

    def __init__(self):
        # Azure AI
        self.azure_endpoint = os.getenv("AZURE_AI_ENDPOINT")
        self.azure_key = os.getenv("AZURE_AI_KEY")
        self.deployment_name = os.getenv("AZURE_AI_DEPLOYMENT")
        self.api_version = os.getenv("AZURE_API_VERSION")
        self.embedding_deployment_name = os.getenv("AZURE_AI_EMBEDDING_DEPLOYMENT")

        # Azure DevOps
        self.organization_url = os.getenv("AZURE_DEVOPS_ORG_URL")
        self.pat_token = os.getenv("AZURE_DEVOPS_PAT")
        self.default_project = os.getenv("AZURE_DEVOPS_PROJECT")
        self.repository_id = os.getenv("AZURE_DEVOPS_REPOSITORY_ID")

        # Paths - Now reads from .env with fallback to current directory
        self.repository_path = os.getenv("REPOSITORY_PATH", os.getcwd())
        self.rag_persist_directory = os.path.join(self.repository_path, ".rag_db")

        self._validate()

    def _validate(self):
        """Validate configuration"""
        required = {
            "AZURE_AI_ENDPOINT": self.azure_endpoint,
            "AZURE_AI_KEY": self.azure_key,
            "AZURE_AI_EMBEDDING_DEPLOYMENT": self.embedding_deployment_name,
            "AZURE_DEVOPS_ORG_URL": self.organization_url,
            "AZURE_DEVOPS_PAT": self.pat_token
        }

        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {missing}")

        print("✓ Configuration validated")
        print(f"✓ Repository path: {self.repository_path}")
        print(f"✓ Embedding deployment: {self.embedding_deployment_name}")
