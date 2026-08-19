import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any


class EconomyDB:
    """经济系统数据库"""

    def __init__(self, plugin_name: str):
        db_dir = Path(__file__).parent / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_dir / "economy.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        """初始化数据库表"""
        c = self.conn.cursor()

        # 用户表
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            coins INTEGER DEFAULT 0,
            total_sign INTEGER DEFAULT 0,
            last_sign TEXT DEFAULT ''
        )''')

        # 商店商品表
        c.execute('''CREATE TABLE IF NOT EXISTS shop (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            stock INTEGER DEFAULT 999,
            description TEXT DEFAULT '',
            effect TEXT DEFAULT '',
            effect_value TEXT DEFAULT '',
            added_by TEXT DEFAULT ''
        )''')

        # 股票表
        c.execute('''CREATE TABLE IF NOT EXISTS stocks (
            stock_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            base_price REAL NOT NULL,
            trend TEXT DEFAULT 'stable',
            last_update TEXT DEFAULT ''
        )''')

        # 用户股票持仓表
        c.execute('''CREATE TABLE IF NOT EXISTS stock_holdings (
            user_id TEXT NOT NULL,
            stock_id TEXT NOT NULL,
            shares INTEGER DEFAULT 0,
            avg_price REAL DEFAULT 0,
            PRIMARY KEY (user_id, stock_id)
        )''')

        # 股票交易记录表
        c.execute('''CREATE TABLE IF NOT EXISTS stock_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            stock_id TEXT NOT NULL,
            action TEXT NOT NULL,
            shares INTEGER NOT NULL,
            price REAL NOT NULL,
            total INTEGER NOT NULL,
            timestamp TEXT NOT NULL
        )''')

        self.conn.commit()

    def close(self):
        """关闭数据库连接"""
        self.conn.close()

    # ==================== 用户相关 ====================

    def get_user(self, user_id: str) -> Optional[Dict]:
        """获取用户信息"""
        c = self.conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_or_create_user(self, user_id: str) -> Dict:
        """获取或创建用户"""
        user = self.get_user(user_id)
        if not user:
            c = self.conn.cursor()
            c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            self.conn.commit()
            user = self.get_user(user_id)
        return user

    def get_coins(self, user_id: str) -> int:
        """获取用户金币"""
        user = self.get_user(user_id)
        return user["coins"] if user else 0

    def add_coins(self, user_id: str, amount: int) -> int:
        """增加用户金币，返回新余额"""
        self.get_or_create_user(user_id)
        c = self.conn.cursor()
        c.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
        self.conn.commit()
        return self.get_coins(user_id)

    def remove_coins(self, user_id: str, amount: int) -> bool:
        """扣除用户金币，返回是否成功"""
        current = self.get_coins(user_id)
        if current < amount:
            return False
        c = self.conn.cursor()
        c.execute("UPDATE users SET coins = coins - ? WHERE user_id=?", (amount, user_id))
        self.conn.commit()
        return True

    def set_coins(self, user_id: str, amount: int):
        """设置用户金币"""
        self.get_or_create_user(user_id)
        c = self.conn.cursor()
        c.execute("UPDATE users SET coins = ? WHERE user_id=?", (amount, user_id))
        self.conn.commit()

    # ==================== 签到相关 ====================

    def can_sign(self, user_id: str) -> bool:
        """检查用户今天是否可以签到"""
        user = self.get_user(user_id)
        if not user:
            return True
        last_sign = user["last_sign"]
        if not last_sign:
            return True
        today = datetime.now().strftime("%Y-%m-%d")
        return last_sign != today

    def do_sign(self, user_id: str, reward: int, bonus: int = 0) -> Dict:
        """执行签到，返回签到结果"""
        if not self.can_sign(user_id):
            return {"success": False, "message": "今天已经签到过了"}

        user = self.get_or_create_user(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 计算连续签到
        continuous = user["total_sign"]
        if user["last_sign"] == yesterday:
            continuous += 1
        else:
            continuous = 1

        # 计算奖励
        total_reward = reward
        if continuous > 0 and continuous % 7 == 0:
            total_reward += bonus

        # 更新用户数据
        c = self.conn.cursor()
        c.execute('''UPDATE users SET 
            coins = coins + ?,
            total_sign = total_sign + 1,
            last_sign = ?
            WHERE user_id=?''', (total_reward, today, user_id))
        self.conn.commit()

        new_balance = self.get_coins(user_id)
        return {
            "success": True,
            "reward": total_reward,
            "continuous": continuous,
            "new_balance": new_balance,
            "message": f"签到成功! 获得 {total_reward} 金币，当前余额: {new_balance}"
        }

    def get_sign_info(self, user_id: str) -> Dict:
        """获取用户签到信息"""
        user = self.get_or_create_user(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        can_sign = user["last_sign"] != today
        return {
            "total_sign": user["total_sign"],
            "last_sign": user["last_sign"],
            "can_sign": can_sign
        }

    # ==================== 商店相关 ====================

    def get_shop_items(self, category: str = None) -> List[Dict]:
        """获取商店商品列表"""
        c = self.conn.cursor()
        if category:
            c.execute("SELECT * FROM shop WHERE effect=? AND stock > 0", (category,))
        else:
            c.execute("SELECT * FROM shop WHERE stock > 0")
        return [dict(row) for row in c.fetchall()]

    def get_shop_item(self, item_id: int) -> Optional[Dict]:
        """获取单个商品信息"""
        c = self.conn.cursor()
        c.execute("SELECT * FROM shop WHERE item_id=?", (item_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def add_shop_item(self, name: str, price: int, description: str,
                      stock: int = 999, effect: str = "", effect_value: str = "",
                      added_by: str = "") -> int:
        """添加商品到商店，返回商品ID"""
        c = self.conn.cursor()
        c.execute('''INSERT INTO shop (name, price, description, stock, effect, effect_value, added_by)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (name, price, description, stock, effect, effect_value, added_by))
        self.conn.commit()
        return c.lastrowid

    def remove_shop_item(self, item_id: int) -> bool:
        """从商店移除商品"""
        c = self.conn.cursor()
        c.execute("DELETE FROM shop WHERE item_id=?", (item_id,))
        self.conn.commit()
        return c.rowcount > 0

    def buy_shop_item(self, item_id: int, user_id: str) -> Dict:
        """购买商品"""
        item = self.get_shop_item(item_id)
        if not item:
            return {"success": False, "message": "商品不存在"}

        if item["stock"] <= 0:
            return {"success": False, "message": "商品已售罄"}

        if not self.remove_coins(user_id, item["price"]):
            return {"success": False, "message": f"金币不足，需要 {item['price']} 金币"}

        # 扣减库存
        c = self.conn.cursor()
        c.execute("UPDATE shop SET stock = stock - 1 WHERE item_id=?", (item_id,))
        self.conn.commit()

        return {
            "success": True,
            "item": item,
            "new_balance": self.get_coins(user_id),
            "message": f"购买 {item['name']} 成功! 花费 {item['price']} 金币"
        }

    def update_shop_stock(self, item_id: int, stock: int) -> bool:
        """更新商品库存"""
        c = self.conn.cursor()
        c.execute("UPDATE shop SET stock = ? WHERE item_id=?", (stock, item_id))
        self.conn.commit()
        return c.rowcount > 0

    # ==================== 股票相关 ====================

    def get_all_stocks(self) -> List[Dict]:
        """获取所有股票"""
        c = self.conn.cursor()
        c.execute("SELECT * FROM stocks")
        return [dict(row) for row in c.fetchall()]

    def get_stock(self, stock_id: str) -> Optional[Dict]:
        """获取单只股票信息"""
        c = self.conn.cursor()
        c.execute("SELECT * FROM stocks WHERE stock_id=?", (stock_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def add_stock(self, stock_id: str, name: str, price: float) -> bool:
        """添加新股票"""
        c = self.conn.cursor()
        try:
            c.execute('''INSERT INTO stocks (stock_id, name, price, base_price, last_update)
                         VALUES (?, ?, ?, ?, ?)''',
                      (stock_id, name, price, price, datetime.now().isoformat()))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_stock_price(self, stock_id: str, price: float, trend: str) -> bool:
        """更新股票价格"""
        c = self.conn.cursor()
        c.execute('''UPDATE stocks SET price=?, trend=?, last_update=? WHERE stock_id=?''',
                  (price, trend, datetime.now().isoformat(), stock_id))
        self.conn.commit()
        return c.rowcount > 0

    def remove_stock(self, stock_id: str) -> bool:
        """删除股票"""
        c = self.conn.cursor()
        c.execute("DELETE FROM stocks WHERE stock_id=?", (stock_id,))
        self.conn.commit()
        return c.rowcount > 0

    # ==================== 持仓相关 ====================

    def get_user_holdings(self, user_id: str) -> List[Dict]:
        """获取用户所有持仓"""
        c = self.conn.cursor()
        c.execute('''SELECT h.*, s.name, s.price as current_price 
                     FROM stock_holdings h 
                     JOIN stocks s ON h.stock_id = s.stock_id
                     WHERE h.user_id=? AND h.shares > 0''', (user_id,))
        return [dict(row) for row in c.fetchall()]

    def get_user_holding(self, user_id: str, stock_id: str) -> Optional[Dict]:
        """获取用户单只股票持仓"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM stock_holdings 
                     WHERE user_id=? AND stock_id=?''', (user_id, stock_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def buy_stock(self, user_id: str, stock_id: str, shares: int, price: float) -> Dict:
        """买入股票"""
        stock = self.get_stock(stock_id)
        if not stock:
            return {"success": False, "message": "股票不存在"}

        total_cost = int(price * shares)
        if not self.remove_coins(user_id, total_cost):
            return {"success": False, "message": f"金币不足，需要 {total_cost} 金币"}

        # 更新持仓
        holding = self.get_user_holding(user_id, stock_id)
        c = self.conn.cursor()

        if holding:
            # 计算新的平均买入价
            old_total = holding["avg_price"] * holding["shares"]
            new_total = old_total + price * shares
            new_shares = holding["shares"] + shares
            avg_price = new_total / new_shares

            c.execute('''UPDATE stock_holdings 
                         SET shares=?, avg_price=? 
                         WHERE user_id=? AND stock_id=?''',
                      (new_shares, avg_price, user_id, stock_id))
        else:
            c.execute('''INSERT INTO stock_holdings (user_id, stock_id, shares, avg_price)
                         VALUES (?, ?, ?, ?)''', (user_id, stock_id, shares, price))

        # 记录交易
        c.execute('''INSERT INTO stock_history 
                     (user_id, stock_id, action, shares, price, total, timestamp)
                     VALUES (?, ?, 'buy', ?, ?, ?, ?)''',
                  (user_id, stock_id, shares, price, total_cost, datetime.now().isoformat()))

        self.conn.commit()

        return {
            "success": True,
            "total_cost": total_cost,
            "new_balance": self.get_coins(user_id),
            "message": f"买入 {stock['name']} x{shares} 成功! 花费 {total_cost} 金币"
        }

    def sell_stock(self, user_id: str, stock_id: str, shares: int, price: float) -> Dict:
        """卖出股票"""
        holding = self.get_user_holding(user_id, stock_id)
        if not holding or holding["shares"] < shares:
            return {"success": False, "message": "持仓不足"}

        stock = self.get_stock(stock_id)
        total_income = int(price * shares)

        # 更新持仓
        c = self.conn.cursor()
        new_shares = holding["shares"] - shares
        if new_shares == 0:
            c.execute("DELETE FROM stock_holdings WHERE user_id=? AND stock_id=?",
                      (user_id, stock_id))
        else:
            c.execute("UPDATE stock_holdings SET shares=? WHERE user_id=? AND stock_id=?",
                      (new_shares, user_id, stock_id))

        # 记录交易
        c.execute('''INSERT INTO stock_history 
                     (user_id, stock_id, action, shares, price, total, timestamp)
                     VALUES (?, ?, 'sell', ?, ?, ?, ?)''',
                  (user_id, stock_id, shares, price, total_income, datetime.now().isoformat()))

        self.conn.commit()

        # 增加金币
        new_balance = self.add_coins(user_id, total_income)

        return {
            "success": True,
            "total_income": total_income,
            "new_balance": new_balance,
            "message": f"卖出 {stock['name']} x{shares} 成功! 获得 {total_income} 金币"
        }

    def get_stock_history(self, user_id: str, limit: int = 10) -> List[Dict]:
        """获取用户交易记录"""
        c = self.conn.cursor()
        c.execute('''SELECT * FROM stock_history 
                     WHERE user_id=? ORDER BY timestamp DESC LIMIT ?''', (user_id, limit))
        return [dict(row) for row in c.fetchall()]

    # ==================== 排行榜相关 ====================

    def get_coins_ranking(self, limit: int = 10) -> List[Dict]:
        """获取金币排行榜"""
        c = self.conn.cursor()
        c.execute("SELECT user_id, coins FROM users ORDER BY coins DESC LIMIT ?", (limit,))
        return [dict(row) for row in c.fetchall()]

    def get_stock_ranking(self, limit: int = 10) -> List[Dict]:
        """获取股票资产排行榜"""
        c = self.conn.cursor()
        c.execute('''
            SELECT user_id, SUM(shares * current_price) as total_value
            FROM (
                SELECT h.user_id, h.shares, h.stock_id, s.price as current_price
                FROM stock_holdings h
                JOIN stocks s ON h.stock_id = s.stock_id
                WHERE h.shares > 0
            )
            GROUP BY user_id
            ORDER BY total_value DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in c.fetchall()]

    def get_total_assets_ranking(self, limit: int = 10) -> List[Dict]:
        """获取总资产排行榜（金币+股票）"""
        c = self.conn.cursor()
        c.execute('''
            SELECT 
                u.user_id,
                u.coins + COALESCE(s.stock_value, 0) as total_assets
            FROM users u
            LEFT JOIN (
                SELECT user_id, SUM(shares * price) as stock_value
                FROM stock_holdings h
                JOIN stocks s ON h.stock_id = s.stock_id
                WHERE h.shares > 0
                GROUP BY user_id
            ) s ON u.user_id = s.user_id
            ORDER BY total_assets DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in c.fetchall()]
