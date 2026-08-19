from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class BalanceTool(FunctionTool[AstrAgentContext]):
    """金币操作工具，支持查询余额和管理员调整余额。"""

    name: str = "balance_operation"
    description: str = "金币操作：查询用户余额，或管理员调整用户金币（增加/减少/设置）"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["query", "add", "remove", "set"],
                    "description": "操作类型：query查询余额，add增加金币(管理员)，remove减少金币(管理员)，set设置金币(管理员)",
                },
                "user_id": {
                    "type": "string",
                    "description": "目标用户ID",
                },
                "amount": {
                    "type": "integer",
                    "description": "金币数量（add/remove/set操作时需要）",
                },
            },
            "required": ["action", "user_id"],
        }
    )

    db = None  # 将在 main.py 中设置
    admin_ids = []  # 管理员列表

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        action = kwargs["action"]
        user_id = kwargs["user_id"]

        if action == "query":
            return self._query_balance(user_id)
        elif action == "add":
            return self._add_coins(kwargs)
        elif action == "remove":
            return self._remove_coins(kwargs)
        elif action == "set":
            return self._set_coins(kwargs)
        else:
            return "未知操作"

    def _query_balance(self, user_id: str) -> str:
        """查询用户余额"""
        coins = self.db.get_coins(user_id)
        return f"用户 {user_id} 的金币余额为: {coins} 金币"

    def _add_coins(self, kwargs: dict) -> str:
        """增加用户金币（管理员）"""
        operator_id = kwargs.get("operator_id", "")
        if operator_id not in self.admin_ids:
            return "只有管理员才能增加用户金币"

        user_id = kwargs["user_id"]
        amount = kwargs.get("amount", 0)
        if amount <= 0:
            return "增加数量必须大于0"

        new_balance = self.db.add_coins(user_id, amount)
        return f"操作成功! 给 {user_id} 增加 {amount} 金币，当前余额: {new_balance}"

    def _remove_coins(self, kwargs: dict) -> str:
        """减少用户金币（管理员）"""
        operator_id = kwargs.get("operator_id", "")
        if operator_id not in self.admin_ids:
            return "只有管理员才能减少用户金币"

        user_id = kwargs["user_id"]
        amount = kwargs.get("amount", 0)
        if amount <= 0:
            return "减少数量必须大于0"

        current = self.db.get_coins(user_id)
        if current < amount:
            return f"用户 {user_id} 当前余额 {current}，不足以扣除 {amount}"

        self.db.remove_coins(user_id, amount)
        new_balance = self.db.get_coins(user_id)
        return f"操作成功! 扣除 {user_id} {amount} 金币，当前余额: {new_balance}"

    def _set_coins(self, kwargs: dict) -> str:
        """设置用户金币数量（管理员）"""
        operator_id = kwargs.get("operator_id", "")
        if operator_id not in self.admin_ids:
            return "只有管理员才能设置用户金币"

        user_id = kwargs["user_id"]
        amount = kwargs.get("amount", 0)
        if amount < 0:
            return "金币数量不能为负数"

        self.db.set_coins(user_id, amount)
        return f"操作成功! 设置 {user_id} 的金币为 {amount}"
