"""
RAG Service with Azure OpenAI Embeddings
"""

import os
import json
import pickle
import hashlib
from typing import List, Dict, Any
from pathlib import Path
from openai import AzureOpenAI
import numpy as np


class CodebaseRAG:
    """RAG System using Azure OpenAI embeddings"""
    
    def __init__(self, repository_path: str, azure_client: AzureOpenAI,
                 persist_directory: str = None, embedding_deployment: str = None):
        self.repository_path = repository_path
        self.persist_directory = persist_directory or os.path.join(repository_path, ".rag_db")
        self.azure_client = azure_client
        self.embedding_deployment = embedding_deployment
        self.repository_signature = None
        self.skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv',
                          'dist', 'build', '.rag_db', '.pytest_cache', '.workflow_states'}
        self.skip_extensions = {'.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe',
                                '.jpg', '.png', '.gif', '.ico', '.pdf', '.zip'}
        
        os.makedirs(self.persist_directory, exist_ok=True)

        self.chunks = []
        self.embeddings = []
        self.metadata_file = os.path.join(self.persist_directory, "metadata.json")
        self.embeddings_file = os.path.join(self.persist_directory, "embeddings.pkl")

        print("[RAG] RAG System initialized (Azure OpenAI embeddings)")
        if not self.embedding_deployment:
            raise ValueError("Embedding deployment name is required for Azure OpenAI embeddings")
    
    def _is_allowed_file_path(self, path: Path) -> bool:
        """Check if file path should be considered for indexing"""
        if any(skip_dir in path.parts for skip_dir in self.skip_dirs):
            return False
        if path.suffix in self.skip_extensions:
            return False
        return True

    def _should_index_file(self, file_path: str) -> bool:
        """Determine if a file should be indexed"""
        path = Path(file_path)

        if not self._is_allowed_file_path(path):
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(100)
            return True
        except:
            return False

    def _load_metadata(self) -> Dict[str, Any]:
        """Load cached metadata if available"""
        if not os.path.exists(self.metadata_file):
            return {}
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as exc:
            print(f"[RAG] Failed to load metadata: {exc}")
            return {}

    def _compute_repository_signature(self) -> str:
        """Compute a hash representing the current repository state"""
        hash_obj = hashlib.md5()

        try:
            for root, dirs, files in os.walk(self.repository_path):
                dirs[:] = [d for d in dirs if d not in self.skip_dirs]
                for file in files:
                    file_path = os.path.join(root, file)
                    path = Path(file_path)
                    if not self._is_allowed_file_path(path):
                        continue

                    rel_path = os.path.relpath(file_path, self.repository_path).encode('utf-8', 'ignore')
                    hash_obj.update(rel_path)

                    try:
                        stat_info = os.stat(file_path)
                    except OSError:
                        continue

                    hash_obj.update(str(stat_info.st_mtime_ns).encode('utf-8'))
                    hash_obj.update(str(stat_info.st_size).encode('utf-8'))
        except Exception as exc:
            print(f"[RAG] Signature computation failed: {exc}")
            return ""

        return hash_obj.hexdigest()
    
    def _chunk_file(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Split file into indexable chunks"""
        chunks = []
        lines = content.split('\n')
        
        current_chunk = []
        current_lines = 0
        
        for i, line in enumerate(lines):
            current_chunk.append(line)
            current_lines += 1
            
            is_definition = any(kw in line for kw in ['def ', 'class ', 'function ', 'const ', 'export '])
            
            if (is_definition and current_lines > 10) or current_lines >= 50:
                chunk_text = '\n'.join(current_chunk)
                chunks.append({
                    'content': chunk_text,
                    'file_path': file_path,
                    'start_line': i - current_lines + 1,
                    'end_line': i,
                    'lines': current_lines
                })
                current_chunk = []
                current_lines = 0
        
        if current_chunk:
            chunks.append({
                'content': '\n'.join(current_chunk),
                'file_path': file_path,
                'start_line': len(lines) - current_lines,
                'end_line': len(lines),
                'lines': current_lines
            })
        
        return chunks
    
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding from Azure OpenAI"""
        try:
            response = self.azure_client.embeddings.create(
                input=text[:8000],
                model=self.embedding_deployment
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"[RAG] Embedding error: {e}")
            return [0.0] * 1536
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-10)
    
    def _cache_exists(self) -> bool:
        """Check if embeddings cache exists"""
        return os.path.exists(self.embeddings_file) and os.path.exists(self.metadata_file)
    
    def _save_cache(self, repository_signature: str):
        """Save embeddings and metadata to disk"""
        with open(self.embeddings_file, 'wb') as f:
            pickle.dump({
                'chunks': self.chunks,
                'embeddings': self.embeddings
            }, f)

        with open(self.metadata_file, 'w') as f:
            json.dump({
                'total_chunks': len(self.chunks),
                'indexed_files': len(set(c['file_path'] for c in self.chunks)),
                'repository_path': self.repository_path,
                'repository_signature': repository_signature
            }, f, indent=2)

        print(f"[RAG] Cache saved: {len(self.chunks)} chunks")

    def _load_cache(self, metadata: Dict[str, Any] = None):
        """Load embeddings from cache"""
        with open(self.embeddings_file, 'rb') as f:
            data = pickle.load(f)
            self.chunks = data['chunks']
            self.embeddings = data['embeddings']

        if metadata:
            self.repository_signature = metadata.get('repository_signature')

        print(f"[RAG] Loaded from cache: {len(self.chunks)} chunks")

    def index_repository(self, force_reindex: bool = False) -> int:
        """Index repository with smart caching"""
        pre_index_signature = self._compute_repository_signature()
        cache_metadata = self._load_metadata() if self._cache_exists() else {}

        # Check if cache exists and matches repository state
        if not force_reindex and cache_metadata:
            cached_signature = cache_metadata.get('repository_signature')
            cached_path = cache_metadata.get('repository_path')

            if cached_signature and cached_path == self.repository_path and cached_signature == pre_index_signature:
                print("[RAG] Using cached embeddings")
                self._load_cache(cache_metadata)
                return len(self.chunks)

            if cached_signature:
                print("[RAG] Repository changes detected, rebuilding embeddings cache")
            else:
                print("[RAG] Cache missing repository signature, rebuilding embeddings cache")

        # Full reindex
        print(f"\n[RAG] {'Re-indexing' if force_reindex else 'Indexing'} repository: {self.repository_path}")

        self.chunks = []
        self.embeddings = []
        indexed_files = 0

        for root, dirs, files in os.walk(self.repository_path):
            dirs[:] = [d for d in dirs if d not in self.skip_dirs]
            for file in files:
                file_path = os.path.join(root, file)

                if not self._should_index_file(file_path):
                    continue

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    rel_path = os.path.relpath(file_path, self.repository_path)
                    chunks = self._chunk_file(content, rel_path)

                    for chunk in chunks:
                        embedding = self._get_embedding(chunk['content'])
                        self.chunks.append(chunk)
                        self.embeddings.append(embedding)

                    indexed_files += 1

                    if indexed_files % 10 == 0:
                        print(f"[RAG] Indexed {indexed_files} files, {len(self.chunks)} chunks...")

                except Exception as e:
                    print(f"[RAG] Error indexing {file_path}: {e}")

        print(f"\n[RAG] ✓ Indexing complete!")
        print(f"[RAG]   Files indexed: {indexed_files}")
        print(f"[RAG]   Total chunks: {len(self.chunks)}")

        final_signature = self._compute_repository_signature()
        if not final_signature:
            final_signature = pre_index_signature

        self.repository_signature = final_signature
        self._save_cache(final_signature)
        return len(self.chunks)
    
    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant code chunks using embeddings"""
        if len(self.chunks) == 0:
            print("[RAG] Warning: No indexed chunks")
            return []
        
        query_embedding = self._get_embedding(query)
        
        similarities = [
            self._cosine_similarity(query_embedding, emb)
            for emb in self.embeddings
        ]
        
        top_indices = np.argsort(similarities)[-n_results:][::-1]
        
        results = []
        for idx in top_indices:
            chunk = self.chunks[idx]
            results.append({
                'content': chunk['content'],
                'file_path': chunk['file_path'],
                'start_line': chunk['start_line'],
                'end_line': chunk['end_line'],
                'file_type': Path(chunk['file_path']).suffix,
                'similarity': similarities[idx]
            })
        
        return results
    
    def analyze_project(self) -> Dict[str, Any]:
        """Analyze project to determine language and frameworks"""
        file_types = {}
        
        for chunk in self.chunks:
            file_type = Path(chunk['file_path']).suffix
            file_types[file_type] = file_types.get(file_type, 0) + 1
        
        language_counts = {
            'python': file_types.get('.py', 0),
            'javascript': file_types.get('.js', 0) + file_types.get('.jsx', 0),
            'typescript': file_types.get('.ts', 0) + file_types.get('.tsx', 0),
            'java': file_types.get('.java', 0),
            'csharp': file_types.get('.cs', 0),
            'go': file_types.get('.go', 0),
            'rust': file_types.get('.rs', 0),
        }
        
        primary_language = max(language_counts.items(), key=lambda x: x[1])[0] if language_counts else 'unknown'
        
        # Detect frameworks
        frameworks = set()
        for chunk in self.chunks[:100]:  # Sample first 100 chunks
            content_lower = chunk['content'].lower()
            if 'import react' in content_lower or 'from react' in content_lower:
                frameworks.add('React')
            if 'import flask' in content_lower or 'from flask' in content_lower:
                frameworks.add('Flask')
            if 'import django' in content_lower or 'from django' in content_lower:
                frameworks.add('Django')
            if 'import express' in content_lower:
                frameworks.add('Express')
        
        return {
            'primary_language': primary_language,
            'language_distribution': language_counts,
            'frameworks': list(frameworks),
            'total_files': len(set(c['file_path'] for c in self.chunks)),
            'total_chunks': len(self.chunks)
        }
    
    def get_project_structure(self) -> Dict[str, Any]:
        """Get project structure summary"""
        file_types = {}
        for chunk in self.chunks:
            ft = Path(chunk['file_path']).suffix
            file_types[ft] = file_types.get(ft, 0) + 1
        
        return {
            "total_files": len(set(c['file_path'] for c in self.chunks)),
            "total_chunks": len(self.chunks),
            "file_types": file_types
        }
