from typing import Optional, Dict, Any
from openai import AzureOpenAI
import json
import asyncio

class BaseAgent:
    """Base class for all agents"""
    
    def __init__(self, name: str, ai_client: AzureOpenAI, deployment_name: str):
        self.name = name
        self.ai_client = ai_client
        self.deployment_name = deployment_name
    
    async def execute(self, context) -> bool:
        """Execute the agent's main task"""
        raise NotImplementedError("Subclasses must implement execute()")
    
    def log(self, context, action: str, result: Any, success: bool = True):
        """Helper to log actions"""
        context.add_log(self.name, action, result, success)
        print(f"[{self.name}] {action}: {result}")
    
    async def call_ai(self, system_prompt: str, user_prompt: str,
                      temperature: float = 0.1, max_tokens: int = 8000,
                      timeout: int = 180) -> str:
        """Call Azure OpenAI with timeout protection"""
        try:
            # Run the synchronous OpenAI call in a thread pool with timeout
            async def _make_request():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: self.ai_client.chat.completions.create(
                        model=self.deployment_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout
                    )
                )

            # Apply asyncio timeout wrapper
            response = await asyncio.wait_for(_make_request(), timeout=timeout)
            return response.choices[0].message.content

        except asyncio.TimeoutError:
            print(f"[{self.name}] ⚠️  AI call timed out after {timeout}s")
            print(f"[{self.name}] Consider breaking this into smaller operations")
            return ""
        except Exception as e:
            print(f"[{self.name}] AI call failed: {e}")
            return ""
    
    def extract_json(self, ai_response: str) -> Optional[Dict]:
        """Extract JSON from AI response"""
        try:
            if "```json" in ai_response:
                json_start = ai_response.find("```json") + 7
                json_end = ai_response.find("```", json_start)
                json_str = ai_response[json_start:json_end].strip()
            else:
                json_start = ai_response.find("{")
                json_end = ai_response.rfind("}") + 1
                json_str = ai_response[json_start:json_end]
            
            return json.loads(json_str)
        except Exception as e:
            print(f"[{self.name}] JSON extraction failed: {e}")
            return None
