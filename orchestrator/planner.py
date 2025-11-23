import json
import os
import re
from typing import Any, Dict, Optional, List
import httpx
from prompt import get_planner_system_prompt

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


class PlannerLLM:
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1"
        self.model = "gpt-4o"
        self.temperature = 0.3

    async def plan(self, user_task: str) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": get_planner_system_prompt()},
                {"role": "user", "content": user_task},
            ],
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=60)) as hc:
            r = await hc.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        text = data["choices"][0]["message"]["content"]
        plan = _extract_json(text)

        if plan is None:
            # safe fallback plan
            return {
                "goal": user_task[:80],
                "subtasks": [
                    {
                        "id": "s1",
                        "agent": "web",
                        "task": user_task,
                        "output_key": "result"
                    }
                ]
            }
        return plan


def validate_plan(plan: Dict[str, Any], allowed_agents: List[str]) -> Dict[str, Any]:
    """Sanitize planner output to avoid crashes."""
    subtasks = plan.get("subtasks", [])
    if not isinstance(subtasks, list) or len(subtasks) == 0:
        return {
            "goal": plan.get("goal", ""),
            "subtasks": [
                {"id": "s1", "agent": "web", "task": plan.get("goal", ""), "output_key": "result"}
            ],
        }

    clean = []
    for i, st in enumerate(subtasks, start=1):
        agent = (st.get("agent") or "web").lower()
        if agent not in allowed_agents:
            agent = "web"
        clean.append({
            "id": st.get("id") or f"s{i}",
            "agent": agent,
            "task": st.get("task") or "",
            "output_key": st.get("output_key") or (st.get("id") or f"s{i}")
        })

    return {"goal": plan.get("goal", ""), "subtasks": clean}
