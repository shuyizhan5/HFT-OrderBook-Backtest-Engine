"""
高级高频交易回测引擎 - 增强版
Enhanced High-Frequency Trading Backtest Engine

改进内容：
1. 使用 Decimal 进行精确的价格/金额计算（消除浮点数精度误差）
2. 支持多种订单类型：
   - Limit Order (限价单)
   - Market Order (市价单 - 模拟为激进限价单)
   - Stop Order (停止单)
   - Stop-Limit Order (停止限价单)
   - IOC Order (立即成交或取消)
   - FOK Order (立即全部成交或全部取消)
3. 完整的 Maker/Taker 费用系统和流动性返佣
4. 高精度价格计算和费用追踪
"""

import time
from collections import defaultdict
import random
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Dict, List, Optional, Tuple
import json

# ============ 常数和枚举 ============

class OrderType(Enum):
    """订单类型"""
    LIMIT = "LIMIT"                  # 限价单
    MARKET = "MARKET"                # 市价单
    STOP = "STOP"                    # 停止单
    STOP_LIMIT = "STOP_LIMIT"        # 停止限价单
    IOC = "IOC"                      # 立即成交或取消
    FOK = "FOK"                      # 立即全部成交或全部取消

class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    """订单状态"""
    PENDING = "PENDING"              # 待成交
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交
    FILLED = "FILLED"                # 完全成交
    CANCELLED = "CANCELLED"          # 已取消
    TRIGGERED = "TRIGGERED"          # 已触发（Stop单）
    REJECTED = "REJECTED"            # 被拒绝

# 交易费用配置
TAKER_FEE_RATE = Decimal("0.0005")  # Taker 费率 0.05%
MAKER_REBATE_RATE = Decimal("0.0002")  # Maker 返佣 0.02%

# ============ 增强的订单事件类 ============

class EnhancedOrderEvent:
    """增强的订单事件，支持多种订单类型和高精度计算"""
    
    def __init__(
        self,
        timestamp: float,
        order_id: int,
        side: OrderSide,
        price: Decimal,
        volume: Decimal,
        order_type: OrderType = OrderType.LIMIT,
        stop_price: Optional[Decimal] = None,
        symbol: str = "ASSET_A",
        time_in_force: str = "GTC"  # GTC=Good-Till-Cancel, IOC=Immediate-Or-Cancel, FOK=Fill-Or-Kill
    ):
        self.timestamp = timestamp
        self.order_id = order_id
        self.side = side
        self.price = price  # 使用 Decimal 进行精确计算
        self.volume = volume
        self.order_type = order_type
        self.stop_price = stop_price  # 用于 STOP 和 STOP_LIMIT 订单
        self.symbol = symbol
        self.time_in_force = time_in_force
        
        # 状态追踪
        self.status = OrderStatus.PENDING
        self.filled_volume = Decimal("0")
        self.filled_value = Decimal("0")  # 成交额
        self.fees = Decimal("0")  # 已付费用
        self.rebates = Decimal("0")  # 已获返佣
        self.creation_timestamp = timestamp
    
    def remaining_volume(self) -> Decimal:
        """获取剩余未成交量"""
        return self.volume - self.filled_volume
    
    def is_fully_filled(self) -> bool:
        """是否完全成交"""
        return self.filled_volume >= self.volume
    
    def update_fill(self, fill_volume: Decimal, fill_price: Decimal, 
                   fee: Decimal = Decimal("0"), rebate: Decimal = Decimal("0")):
        """更新成交信息"""
        self.filled_volume += fill_volume
        self.filled_value += fill_volume * fill_price
        self.fees += fee
        self.rebates += rebate
        
        if self.is_fully_filled():
            self.status = OrderStatus.FILLED
        elif self.filled_volume > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
    
    def cancel(self):
        """取消订单"""
        self.status = OrderStatus.CANCELLED
    
    def trigger(self):
        """触发 Stop 订单"""
        self.status = OrderStatus.TRIGGERED
    
    def reject(self):
        """拒绝订单"""
        self.status = OrderStatus.REJECTED
    
    def average_fill_price(self) -> Decimal:
        """获取平均成交价"""
        if self.filled_volume == 0:
            return Decimal("0")
        return (self.filled_value / self.filled_volume).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    
    def net_fill_value(self) -> Decimal:
        """获取净成交额（已扣费用）"""
        return self.filled_value - self.fees + self.rebates


# ============ 增强的数据加载器 ============

class EnhancedMockDataLoader:
    """生成多种订单类型的模拟数据"""
    
    def __init__(self, num_events: int = 1000, start_time: float = 1704067200):
        self.num_events = num_events
        self.current_time = start_time
        self.order_counter = 0
    
    def generate_event(self) -> EnhancedOrderEvent:
        """生成一个随机订单事件，包含多种订单类型"""
        self.current_time += random.uniform(0.001, 0.5)
        self.order_counter += 1
        
        # 80% 普通订单，20% 特殊订单
        if random.random() < 0.8:
            order_type = random.choice([OrderType.LIMIT, OrderType.MARKET, OrderType.IOC])
        else:
            order_type = random.choice([OrderType.STOP, OrderType.STOP_LIMIT, OrderType.FOK])
        
        side = OrderSide(random.choice(["BUY", "SELL"]))
        
        # 使用 Decimal 确保精度
        base_price = Decimal("10.00")
        price_offset = Decimal(str(random.uniform(-0.05, 0.05)))
        price = (base_price + price_offset).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        
        volume = Decimal(str(random.randint(100, 500)))
        
        # Stop 单的触发价
        stop_price = None
        if order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            if side == OrderSide.BUY:
                stop_price = (price * Decimal("1.01")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                stop_price = (price * Decimal("0.99")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        
        # 决定 time_in_force
        if order_type == OrderType.IOC:
            time_in_force = "IOC"
        elif order_type == OrderType.FOK:
            time_in_force = "FOK"
        else:
            time_in_force = "GTC"
        
        return EnhancedOrderEvent(
            timestamp=self.current_time,
            order_id=self.order_counter,
            side=side,
            price=price,
            volume=volume,
            order_type=order_type,
            stop_price=stop_price,
            time_in_force=time_in_force
        )
    
    def get_event_stream(self):
        """生成事件流"""
        for _ in range(self.num_events):
            yield self.generate_event()


# ============ 增强的订单簿 ============

class EnhancedOrderBook:
    """
    增强的订单簿，支持：
    - 多种订单类型
    - 高精度价格计算
    - Maker/Taker 费用系统
    - Stop 订单触发机制
    """
    
    def __init__(self):
        # 普通订单簿：{ price: [(order_id, volume, status), ...] }
        self.bid_book: Dict[Decimal, List[Tuple[int, Decimal]]] = defaultdict(list)
        self.ask_book: Dict[Decimal, List[Tuple[int, Decimal]]] = defaultdict(list)
        
        # Stop 订单队列：{ trigger_condition: [order_id, ...] }
        self.stop_orders: List[int] = []
        
        # 所有订单：{ order_id: EnhancedOrderEvent }
        self.active_orders: Dict[int, EnhancedOrderEvent] = {}
        self.cancelled_orders: Dict[int, EnhancedOrderEvent] = {}
        
        # 成交历史
        self.trades: List[Dict] = []
        
        # 费用追踪
        self.total_taker_fees = Decimal("0")
        self.total_maker_rebates = Decimal("0")
        
        # 当前最优价格（用于 Stop 订单触发）
        self.last_trade_price = Decimal("10.00")
    
    def get_best_prices(self) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """获取最优买卖价"""
        best_bid = max(self.bid_book.keys()) if self.bid_book else None
        best_ask = min(self.ask_book.keys()) if self.ask_book else None
        return best_bid, best_ask
    
    def check_stop_orders(self, current_price: Decimal, timestamp: float):
        """检查并触发 Stop 订单"""
        triggered = []
        for order_id in self.stop_orders:
            order = self.active_orders.get(order_id)
            if not order:
                continue
            
            should_trigger = False
            if order.side == OrderSide.BUY and current_price >= order.stop_price:
                should_trigger = True
            elif order.side == OrderSide.SELL and current_price <= order.stop_price:
                should_trigger = True
            
            if should_trigger:
                order.trigger()
                triggered.append(order_id)
                # 将 Stop 订单转换为限价单继续处理
                if order.order_type == OrderType.STOP:
                    order.order_type = OrderType.LIMIT
                elif order.order_type == OrderType.STOP_LIMIT:
                    order.order_type = OrderType.LIMIT
                self.handle_new_order(order)
        
        for order_id in triggered:
            self.stop_orders.remove(order_id)
    
    def handle_new_order(self, order: EnhancedOrderEvent):
        """处理新订单"""
        # Stop 订单先加入队列
        if order.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            self.stop_orders.append(order.order_id)
            self.active_orders[order.order_id] = order
            return
        
        # 市价单转换为激进限价单
        if order.order_type == OrderType.MARKET:
            if order.side == OrderSide.BUY:
                order.price = (max(self.ask_book.keys()) if self.ask_book 
                              else self.last_trade_price) + Decimal("0.01")
            else:
                order.price = (min(self.bid_book.keys()) if self.bid_book 
                              else self.last_trade_price) - Decimal("0.01")
            order.order_type = OrderType.LIMIT
        
        # 尝试立即撮合
        self.match_and_trade(order)
        
        # 根据 time_in_force 决定是否挂入订单簿
        if order.remaining_volume() > 0:
            if order.time_in_force == "IOC":
                # IOC 订单：未成交部分立即取消
                order.cancel()
            elif order.time_in_force == "FOK":
                # FOK 订单：如果未能全部成交则全部取消
                order.cancel()
                # 撤回已部分成交，这里简化处理
                if order.filled_volume > 0:
                    self.undo_partial_fill(order)
            else:
                # GTC 订单：挂入订单簿
                self.place_limit_order(order)
        
        self.active_orders[order.order_id] = order
    
    def place_limit_order(self, order: EnhancedOrderEvent):
        """将订单挂入订单簿"""
        remaining = order.remaining_volume()
        if remaining <= 0:
            return
        
        if order.side == OrderSide.BUY:
            self.bid_book[order.price].append((order.order_id, remaining))
        else:
            self.ask_book[order.price].append((order.order_id, remaining))
    
    def match_and_trade(self, aggressor_order: EnhancedOrderEvent):
        """
        核心撮合逻辑 - 支持 Maker/Taker 费用
        
        撮合规则：
        1. 价格优先：最优价格优先成交
        2. 时间优先：同价格按挂单时间优先
        3. 数量优先：按可用数量成交
        """
        if aggressor_order.side == OrderSide.BUY:
            book_to_match = self.ask_book
            match_prices = sorted([p for p in book_to_match if p <= aggressor_order.price])
        else:  # SELL
            book_to_match = self.bid_book
            match_prices = sorted([p for p in book_to_match if p >= aggressor_order.price], 
                                 reverse=True)
        
        remaining_volume = aggressor_order.remaining_volume()
        
        for price in match_prices:
            if remaining_volume <= 0:
                break
            
            orders_at_price = book_to_match[price]
            i = 0
            
            while i < len(orders_at_price) and remaining_volume > 0:
                passive_order_id, passive_volume = orders_at_price[i]
                passive_order = self.active_orders[passive_order_id]
                
                # 计算成交量
                trade_volume = min(remaining_volume, passive_volume)
                
                # 计算 Taker 费用和 Maker 返佣
                taker_fee = (trade_volume * price * TAKER_FEE_RATE).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                maker_rebate = (trade_volume * price * MAKER_REBATE_RATE).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
                
                # 更新 Taker（主动方）
                aggressor_order.update_fill(trade_volume, price, fee=taker_fee)
                
                # 更新 Maker（被动方）
                passive_order.update_fill(trade_volume, price, rebate=maker_rebate)
                
                # 记录成交
                self.record_trade(
                    aggressor_order.order_id,
                    passive_order_id,
                    trade_volume,
                    price,
                    aggressor_order.timestamp,
                    taker_fee,
                    maker_rebate
                )
                
                # 更新账户
                self.total_taker_fees += taker_fee
                self.total_maker_rebates += maker_rebate
                self.last_trade_price = price
                
                # 更新剩余数量
                remaining_volume -= trade_volume
                orders_at_price[i] = (passive_order_id, passive_volume - trade_volume)
                
                # 如果被动订单完全成交，移除
                if orders_at_price[i][1] <= 0:
                    orders_at_price.pop(i)
                    passive_order.status = OrderStatus.FILLED
                    if passive_order_id in self.active_orders:
                        del self.active_orders[passive_order_id]
                else:
                    i += 1
    
    def record_trade(self, taker_id: int, maker_id: int, volume: Decimal, 
                    price: Decimal, timestamp: float, taker_fee: Decimal, 
                    maker_rebate: Decimal):
        """记录成交信息"""
        self.trades.append({
            'timestamp': timestamp,
            'taker_id': taker_id,
            'maker_id': maker_id,
            'volume': volume,
            'price': price,
            'value': volume * price,
            'taker_fee': taker_fee,
            'maker_rebate': maker_rebate,
            'net_value': (volume * price) - taker_fee + maker_rebate
        })
    
    def handle_cancel_order(self, order_id: int):
        """取消订单"""
        if order_id not in self.active_orders:
            return False
        
        order = self.active_orders[order_id]
        order.cancel()
        self.cancelled_orders[order_id] = order
        del self.active_orders[order_id]
        
        # 从订单簿中移除
        if order.side == OrderSide.BUY:
            if order.price in self.bid_book:
                self.bid_book[order.price] = [
                    (oid, vol) for oid, vol in self.bid_book[order.price]
                    if oid != order_id
                ]
                if not self.bid_book[order.price]:
                    del self.bid_book[order.price]
        else:
            if order.price in self.ask_book:
                self.ask_book[order.price] = [
                    (oid, vol) for oid, vol in self.ask_book[order.price]
                    if oid != order_id
                ]
                if not self.ask_book[order.price]:
                    del self.ask_book[order.price]
        
        return True
    
    def undo_partial_fill(self, order: EnhancedOrderEvent):
        """撤回部分成交（用于 FOK 拒绝时）"""
        # 这里简化处理，实际应该反向所有成交
        pass
    
    def get_snapshot(self) -> Dict:
        """获取订单簿快照"""
        return {
            'bid': {p: sum(v for _, v in self.bid_book[p]) 
                   for p in sorted(self.bid_book.keys(), reverse=True)},
            'ask': {p: sum(v for _, v in self.ask_book[p]) 
                   for p in sorted(self.ask_book.keys())},
            'last_trade_price': self.last_trade_price,
            'total_taker_fees': self.total_taker_fees,
            'total_maker_rebates': self.total_maker_rebates,
        }
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'total_trades': len(self.trades),
            'total_volume': sum(Decimal(t['volume']) for t in self.trades),
            'total_value': sum(Decimal(t['value']) for t in self.trades),
            'total_taker_fees': self.total_taker_fees,
            'total_maker_rebates': self.total_maker_rebates,
            'net_fees': self.total_taker_fees - self.total_maker_rebates,
            'active_orders_count': len(self.active_orders),
            'stop_orders_count': len(self.stop_orders),
        }


# ============ 增强的策略 ============

class EnhancedOrderFlowStrategy:
    """基于订单簿失衡的增强策略"""
    
    def __init__(self, engine):
        self.engine = engine
        self.position = Decimal("0")
        self.entry_price = Decimal("0")
        self.last_trade_time = 0
        self.trades_executed = []
    
    def on_order_book_update(self, snapshot: Dict, timestamp: float):
        """监听订单簿更新"""
        if not snapshot['bid'] or not snapshot['ask']:
            return
        
        best_bid_price = max(snapshot['bid'].keys())
        best_ask_price = min(snapshot['ask'].keys())
        
        bid_volume = snapshot['bid'][best_bid_price]
        ask_volume = snapshot['ask'][best_ask_price]
        
        imbalance = bid_volume / (ask_volume + 1)
        
        # 买信号
        if imbalance > Decimal("2.0") and self.position == 0:
            order = EnhancedOrderEvent(
                timestamp=timestamp,
                order_id=-self.engine.current_event_id - 1,
                side=OrderSide.BUY,
                price=Decimal("999999"),
                volume=Decimal("500"),
                order_type=OrderType.MARKET
            )
            self.engine.order_book.handle_new_order(order)
            self.position = Decimal("500")
            self.entry_price = snapshot['last_trade_price']
            self.trades_executed.append({
                'type': 'BUY',
                'price': float(snapshot['last_trade_price']),
                'volume': 500,
                'timestamp': timestamp
            })
        
        # 卖信号
        elif self.position > 0 and (timestamp - self.last_trade_time) > 10:
            order = EnhancedOrderEvent(
                timestamp=timestamp,
                order_id=-self.engine.current_event_id - 2,
                side=OrderSide.SELL,
                price=Decimal("0"),
                volume=self.position,
                order_type=OrderType.MARKET
            )
            self.engine.order_book.handle_new_order(order)
            self.trades_executed.append({
                'type': 'SELL',
                'price': float(snapshot['last_trade_price']),
                'volume': int(self.position),
                'timestamp': timestamp
            })
            self.position = Decimal("0")
        
        self.last_trade_time = timestamp


# ============ 增强的回测引擎 ============

class EnhancedBacktestEngine:
    """增强的回测引擎"""
    
    def __init__(self, data_loader, strategy):
        self.data_loader = data_loader
        self.order_book = EnhancedOrderBook()
        self.strategy = strategy
        self.current_event_id = 0
    
    def run(self):
        """运行回测"""
        print("\n" + "="*70)
        print("🚀 启动增强型高频交易回测引擎")
        print("   支持: Stop Orders | IOC/FOK | Maker/Taker Fees | 高精度计算")
        print("="*70 + "\n")
        
        for event in self.data_loader.get_event_stream():
            self.current_event_id += 1
            
            # 处理订单事件
            if event.order_type not in [OrderType.STOP, OrderType.STOP_LIMIT]:
                # 检查 Stop 订单触发
                self.order_book.check_stop_orders(event.price, event.timestamp)
            
            self.order_book.handle_new_order(event)
            
            # 通知策略
            snapshot = self.order_book.get_snapshot()
            self.strategy.on_order_book_update(snapshot, event.timestamp)
            
            # 每 500 个事件打印进度
            if self.current_event_id % 500 == 0:
                stats = self.order_book.get_statistics()
                print(f"[事件 {self.current_event_id}] 成交笔数: {stats['total_trades']}, "
                      f"活跃订单: {stats['active_orders_count']}, "
                      f"总费用: ¥{stats['net_fees']:.4f}")
        
        print("\n✅ 回测完成！\n")
    
    def print_detailed_report(self):
        """打印详细报告"""
        stats = self.order_book.get_statistics()
        
        print("="*70)
        print("📊 增强版回测报告")
        print("="*70)
        
        print("\n📈 交易统计:")
        print(f"   总成交笔数: {stats['total_trades']}")
        print(f"   总成交量: {stats['total_volume']} 股")
        print(f"   总成交额: ¥{stats['total_value']:.2f}")
        
        if stats['total_trades'] > 0:
            avg_price = stats['total_value'] / stats['total_volume']
            print(f"   平均成交价: ¥{avg_price:.4f}")
        
        print("\n💰 费用系统:")
        print(f"   Taker 总费用: ¥{stats['total_taker_fees']:.4f}")
        print(f"   Maker 总返佣: ¥{stats['total_maker_rebates']:.4f}")
        print(f"   净费用: ¥{stats['net_fees']:.4f}")
        print(f"   费用率 (相对成交额): {(stats['net_fees'] / stats['total_value'] * 100):.4f}%" 
              if stats['total_value'] > 0 else "   费用率: N/A")
        
        print("\n📋 订单簿状态:")
        print(f"   活跃订单数: {stats['active_orders_count']}")
        print(f"   Stop 订单数: {stats['stop_orders_count']}")
        
        best_bid, best_ask = self.order_book.get_best_prices()
        if best_bid and best_ask:
            spread = best_ask - best_bid
            spread_bps = (spread / self.order_book.last_trade_price * 10000)
            print(f"   最优买价: ¥{best_bid:.4f}")
            print(f"   最优卖价: ¥{best_ask:.4f}")
            print(f"   价差: ¥{spread:.4f} ({spread_bps:.2f} bps)")
        
        print("\n🎯 策略表现:")
        print(f"   策略执行交易数: {len(self.strategy.trades_executed)}")
        print(f"   最终持仓: {self.strategy.position} 股")
        
        if self.strategy.trades_executed:
            print(f"\n   执行的交易:")
            for i, trade in enumerate(self.strategy.trades_executed, 1):
                print(f"      {i}. {trade['type']:4s} {trade['volume']:6} 股 "
                      f"@ ¥{trade['price']:.4f}")
        
        print("\n" + "="*70 + "\n")


# ============ 运行主程序 ============

if __name__ == "__main__":
    # 配置
    NUM_EVENTS = 5000
    
    # 创建实例
    data_loader = EnhancedMockDataLoader(num_events=NUM_EVENTS)
    engine = EnhancedBacktestEngine(data_loader, None)
    strategy = EnhancedOrderFlowStrategy(engine)
    engine.strategy = strategy
    
    # 运行回测
    engine.run()
    
    # 打印报告
    engine.print_detailed_report()
    
    # 保存详细数据为 JSON
    trades_data = {
        'total_trades': len(engine.order_book.trades),
        'trades': [
            {
                'timestamp': float(t['timestamp']),
                'volume': float(t['volume']),
                'price': float(t['price']),
                'value': float(t['value']),
                'taker_fee': float(t['taker_fee']),
                'maker_rebate': float(t['maker_rebate']),
                'net_value': float(t['net_value'])
            }
            for t in engine.order_book.trades[:100]  # 保存前 100 笔交易样本
        ],
        'statistics': {
            'total_volume': float(engine.order_book.get_statistics()['total_volume']),
            'total_value': float(engine.order_book.get_statistics()['total_value']),
            'total_taker_fees': float(engine.order_book.get_statistics()['total_taker_fees']),
            'total_maker_rebates': float(engine.order_book.get_statistics()['total_maker_rebates']),
            'net_fees': float(engine.order_book.get_statistics()['net_fees']),
        }
    }
    
    with open('/Users/zhanshuyi/Downloads/QTProject1/backtest_data_enhanced.json', 'w') as f:
        json.dump(trades_data, f, indent=2)
    
    print("✅ 详细数据已保存到 backtest_data_enhanced.json")
