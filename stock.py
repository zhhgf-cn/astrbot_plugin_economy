import random
from datetime import datetime
from typing import List, Dict, Optional
from .database import EconomyDB


class StockSystem:
    """股票系统"""

    def __init__(self, db: EconomyDB, max_change: float = 0.10):
        self.db = db
        self.max_change = max_change  # 最大涨跌幅

    def update_all_prices(self) -> List[Dict]:
        """更新所有股票价格，返回更新结果"""
        stocks = self.db.get_all_stocks()
        results = []

        for stock in stocks:
            result = self.update_stock_price(stock["stock_id"])
            results.append(result)

        return results

    def update_stock_price(self, stock_id: str) -> Dict:
        """更新单只股票价格"""
        stock = self.db.get_stock(stock_id)
        if not stock:
            return {"success": False, "message": f"股票 {stock_id} 不存在"}

        old_price = stock["price"]
        base_price = stock["base_price"]
        trend = stock["trend"]

        # 基础随机波动 (-5% ~ +5%)
        base_change = random.uniform(-0.05, 0.05)

        # 趋势加成
        trend_bonus = {"up": 0.02, "down": -0.02, "stable": 0}
        trend_change = trend_bonus.get(trend, 0)

        # 均值回归倾向（价格偏离基准越远，回归倾向越强）
        deviation = (old_price - base_price) / base_price
        mean_reversion = -deviation * 0.1

        # 计算总变化
        total_change = base_change + trend_change + mean_reversion

        # 涨跌幅限制
        total_change = max(-self.max_change, min(self.max_change, total_change))

        # 更新价格
        new_price = old_price * (1 + total_change)
        new_price = max(1, new_price)  # 最低1金币
        new_price = round(new_price, 2)

        # 更新趋势
        if total_change > 0.03:
            new_trend = "up"
        elif total_change < -0.03:
            new_trend = "down"
        else:
            new_trend = "stable"

        # 保存到数据库
        self.db.update_stock_price(stock_id, new_price, new_trend)

        return {
            "success": True,
            "stock_id": stock_id,
            "name": stock["name"],
            "old_price": old_price,
            "new_price": new_price,
            "change": round(total_change * 100, 2),
            "trend": new_trend
        }

    def get_stock_info(self, stock_id: str) -> Optional[Dict]:
        """获取股票详细信息"""
        stock = self.db.get_stock(stock_id)
        if not stock:
            return None

        # 计算涨跌幅
        change = ((stock["price"] - stock["base_price"]) / stock["base_price"]) * 100

        return {
            "stock_id": stock["stock_id"],
            "name": stock["name"],
            "price": stock["price"],
            "base_price": stock["base_price"],
            "change": round(change, 2),
            "trend": stock["trend"],
            "trend_emoji": {"up": "📈", "down": "📉", "stable": "➡️"}.get(stock["trend"], "➡️"),
            "last_update": stock["last_update"]
        }

    def get_all_stocks_info(self) -> List[Dict]:
        """获取所有股票信息"""
        stocks = self.db.get_all_stocks()
        result = []
        for stock in stocks:
            info = self.get_stock_info(stock["stock_id"])
            if info:
                result.append(info)
        return result

    def calculate_portfolio_value(self, user_id: str) -> Dict:
        """计算用户股票资产总值"""
        holdings = self.db.get_user_holdings(user_id)
        total_value = 0
        total_cost = 0
        details = []

        for h in holdings:
            value = h["shares"] * h["current_price"]
            cost = h["shares"] * h["avg_price"]
            profit = value - cost
            profit_rate = (profit / cost * 100) if cost > 0 else 0

            total_value += value
            total_cost += cost

            details.append({
                "stock_id": h["stock_id"],
                "name": h["name"],
                "shares": h["shares"],
                "avg_price": h["avg_price"],
                "current_price": h["current_price"],
                "value": round(value, 2),
                "profit": round(profit, 2),
                "profit_rate": round(profit_rate, 2)
            })

        total_profit = total_value - total_cost
        total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0

        return {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_profit": round(total_profit, 2),
            "total_profit_rate": round(total_profit_rate, 2),
            "details": details
        }
