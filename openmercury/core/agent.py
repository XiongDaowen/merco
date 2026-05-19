"""Agent 主循环与核心逻辑"""


class Agent:
    """AI Agent 核心类，负责对话循环与工具调度"""

    def __init__(self, config=None):
        self.config = config or {}
        self.session = None
        self.tools = {}
        self.skills = {}

    async def run(self, prompt: str) -> str:
        """执行一次 Agent 循环"""
        raise NotImplementedError


class AgentLoop:
    """Agent 循环控制器"""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.history = []

    async def step(self, message: str) -> dict:
        """执行单步循环"""
        raise NotImplementedError
