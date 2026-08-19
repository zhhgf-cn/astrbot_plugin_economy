from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class SignTool(FunctionTool[AstrAgentContext]):
    """执行每日签到，获取金币奖励。"""

    name: str = "do_sign"
    description: str = "帮用户执行每日签到，获取金币奖励"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "要签到的用户ID",
                },
            },
            "required": ["user_id"],
        }
    )

    db = None  # 将在 main.py 中设置
    sign_reward = 10  # 签到奖励
    sign_bonus = 5  # 连续签到奖励

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        user_id = kwargs["user_id"]
        result = self.db.do_sign(user_id, self.sign_reward, self.sign_bonus)
        return result["message"]
