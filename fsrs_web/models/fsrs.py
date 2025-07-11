#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
增强版FSRS (Free Spaced Repetition Scheduler) 算法实现
包含自适应参数调整、记忆状态预测和个性化难度调整功能
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Union, Tuple, Any
from datetime import datetime, timedelta
import json
import os


@dataclass
class MemoryState:
    """记忆状态，包含稳定性和难度两个参数"""
    stability: float  # 记忆的稳定性
    difficulty: float  # 卡片的难度
    
    def __str__(self):
        return f"稳定性: {self.stability:.2f}, 难度: {self.difficulty:.2f}"


@dataclass
class ReviewLog:
    """复习记录"""
    timestamp: datetime  # 复习时间
    rating: int  # 1: again, 2: hard, 3: good, 4: easy
    elapsed_days: float  # 距离上次复习的天数
    scheduled_days: int  # 计划的复习间隔天数


@dataclass
class Card:
    """卡片模型"""
    id: str  # 卡片唯一标识符
    unit_id: str  # 所属单元ID
    front: str  # 正面内容
    back: str  # 背面内容
    created_at: datetime  # 创建时间
    due_date: datetime  # 下次复习日期
    memory_state: Optional[MemoryState] = None  # 记忆状态
    review_logs: List[ReviewLog] = field(default_factory=list)  # 复习历史
    tags: List[str] = field(default_factory=list)  # 卡片标签，用于个性化调整
    learning_factor: float = 1.0  # 学习因子，用于个性化调整
    
    @property
    def is_new(self) -> bool:
        """判断是否为新卡片"""
        return len(self.review_logs) == 0
    
    @property
    def average_rating(self) -> float:
        """计算平均评分"""
        if not self.review_logs:
            return 0.0
        return sum(log.rating for log in self.review_logs) / len(self.review_logs)
    
    @property
    def retention_rate(self) -> float:
        """计算记忆保留率"""
        if not self.review_logs:
            return 0.0
        good_ratings = sum(1 for log in self.review_logs if log.rating >= 3)
        return good_ratings / len(self.review_logs)


class FSRSOptimizer:
    """FSRS参数优化器"""
    
    def __init__(self, learning_rate: float = 0.01, regularization: float = 0.1):
        """初始化优化器
        
        Args:
            learning_rate: 学习率
            regularization: 正则化系数
        """
        self.learning_rate = learning_rate
        self.regularization = regularization
    
    def compute_loss(self, cards: List[Card], params: List[float]) -> float:
        """计算损失函数
        
        Args:
            cards: 卡片列表
            params: FSRS参数
            
        Returns:
            损失值
        """
        loss = 0.0
        total_reviews = 0
        
        # 临时FSRS实例，用于计算预测值
        temp_fsrs = FSRS(params=params)
        
        for card in cards:
            if len(card.review_logs) < 2:
                continue
                
            for i in range(1, len(card.review_logs)):
                prev_log = card.review_logs[i-1]
                curr_log = card.review_logs[i]
                
                # 计算实际间隔天数
                elapsed_days = curr_log.elapsed_days
                
                # 计算预测的保留率
                if card.memory_state and prev_log.timestamp:
                    stability = card.memory_state.stability
                    predicted_retention = temp_fsrs._forgetting_curve(stability, elapsed_days)
                    
                    # 实际评分转换为二元结果（记得/忘记）
                    actual_result = 1.0 if curr_log.rating >= 3 else 0.0
                    
                    # 计算二元交叉熵损失
                    if 0 < predicted_retention < 1 and 0 < actual_result < 1:
                        loss -= actual_result * math.log(predicted_retention) + (1 - actual_result) * math.log(1 - predicted_retention)
                        total_reviews += 1
        
        # 添加L2正则化
        l2_reg = self.regularization * sum(p*p for p in params)
        
        # 平均损失
        return (loss / max(1, total_reviews)) + l2_reg
    
    def optimize(self, cards: List[Card], initial_params: List[float], 
                iterations: int = 100) -> List[float]:
        """优化FSRS参数
        
        Args:
            cards: 卡片列表
            initial_params: 初始参数
            iterations: 迭代次数
            
        Returns:
            优化后的参数
        """
        params = initial_params.copy()
        best_params = params.copy()
        best_loss = float('inf')
        
        for i in range(iterations):
            # 计算当前损失
            current_loss = self.compute_loss(cards, params)
            
            if current_loss < best_loss:
                best_loss = current_loss
                best_params = params.copy()
            
            # 计算梯度
            gradients = []
            for j in range(len(params)):
                eps = 1e-5
                params_plus = params.copy()
                params_plus[j] += eps
                
                loss_plus = self.compute_loss(cards, params_plus)
                gradient = (loss_plus - current_loss) / eps
                gradients.append(gradient)
            
            # 更新参数
            for j in range(len(params)):
                params[j] -= self.learning_rate * gradients[j]
                
            # 确保参数在合理范围内
            for j in range(len(params)):
                params[j] = max(0.01, min(10.0, params[j]))
                
            # 如果损失变化很小，提前结束
            if i > 10 and abs(current_loss - best_loss) < 1e-6:
                break
                
        return best_params


class FSRS:
    """FSRS算法实现"""
    
    # FSRS 默认参数
    DEFAULT_PARAMS = [
        0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94,
        2.18, 0.05, 0.34, 1.26, 0.29, 2.61
    ]
    
    # 记忆状态初始值
    INIT_STABILITY = 1.0
    INIT_DIFFICULTY = 5.0
    
    # 参数保存路径
    PARAMS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'fsrs_params.json')
    
    def __init__(self, 
                 desired_retention: float = 0.9, 
                 maximum_interval: int = 36500,
                 params: Optional[List[float]] = None,
                 enable_adaptive_params: bool = True):
        """初始化FSRS算法
        
        Args:
            desired_retention: 期望的记忆保留率，通常为0.9
            maximum_interval: 最大复习间隔天数
            params: 算法参数，如果为None则使用默认参数
            enable_adaptive_params: 是否启用自适应参数
        """
        self.desired_retention = desired_retention
        self.maximum_interval = maximum_interval
        self.enable_adaptive_params = enable_adaptive_params
        
        # 尝试加载保存的参数
        loaded_params = self._load_params() if enable_adaptive_params else None
        self.w = loaded_params if loaded_params else (params if params is not None else self.DEFAULT_PARAMS)
        
        # 初始化优化器
        self.optimizer = FSRSOptimizer()
        
        # 记录最近的复习数据，用于自适应调整
        self.recent_reviews = []
        self.optimization_threshold = 50  # 收集这么多复习记录后进行优化
    
    def _load_params(self) -> Optional[List[float]]:
        """从文件加载参数"""
        try:
            if os.path.exists(self.PARAMS_FILE):
                with open(self.PARAMS_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('params')
        except Exception as e:
            print(f"加载参数失败: {e}")
        return None
    
    def _save_params(self):
        """保存参数到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.PARAMS_FILE), exist_ok=True)
            
            with open(self.PARAMS_FILE, 'w') as f:
                json.dump({'params': self.w}, f)
        except Exception as e:
            print(f"保存参数失败: {e}")
    
    def init_card(self, card: Card) -> Card:
        """初始化卡片的记忆状态"""
        if card.is_new:
            card.memory_state = MemoryState(
                stability=self.INIT_STABILITY,
                difficulty=self.INIT_DIFFICULTY
            )
        return card
    
    def next_interval(self, stability: float, learning_factor: float = 1.0) -> int:
        """计算下一个复习间隔
        
        Args:
            stability: 记忆稳定性
            learning_factor: 学习因子，用于个性化调整
            
        Returns:
            下一个复习间隔天数
        """
        # 计算精确间隔，考虑学习因子
        interval = stability * math.log(self.desired_retention) * -1.0 * learning_factor
        
        # 添加随机波动 (±5%)
        fuzz = random.uniform(0.95, 1.05)
        interval *= fuzz
        
        # 限制最大间隔
        interval = min(interval, self.maximum_interval)
        
        # 向上取整，确保至少为1天
        return max(1, round(interval))
    
    def _update_difficulty(self, difficulty: float, rating: int) -> float:
        """更新难度
        
        Args:
            difficulty: 当前难度
            rating: 评分 (1-4)
            
        Returns:
            更新后的难度
        """
        # 难度调整因子
        difficulty_factor = {
            1: self.w[4],  # Again
            2: self.w[5],  # Hard
            3: self.w[6],  # Good
            4: self.w[7],  # Easy
        }
        
        # 更新难度
        factor = difficulty_factor.get(rating, self.w[6])
        next_difficulty = difficulty + self.w[3] * (factor - difficulty)
        
        # 限制难度范围
        return max(1.0, min(10.0, next_difficulty))
    
    def _update_stability(self, stability: float, difficulty: float, 
                         rating: int, elapsed_days: float) -> float:
        """更新稳定性
        
        Args:
            stability: 当前稳定性
            difficulty: 当前难度
            rating: 评分 (1-4)
            elapsed_days: 已过去天数
            
        Returns:
            更新后的稳定性
        """
        # 计算遗忘率
        decay = self._forgetting_curve(stability, elapsed_days)
        
        # 根据评分更新稳定性
        if rating == 1:  # Again
            new_stability = self.w[0] * stability * decay
        elif rating == 2:  # Hard
            new_stability = stability * (1 + self.w[1] * decay)
        elif rating == 3:  # Good
            new_stability = stability * (1 + self.w[2] * decay)
        else:  # Easy
            new_stability = stability * (1 + self.w[2] * decay * 2.0)
        
        # 确保稳定性至少为1天
        return max(1.0, new_stability)
    
    def _forgetting_curve(self, stability: float, elapsed_days: float) -> float:
        """遗忘曲线，计算给定稳定性和经过天数下的记忆保留率
        
        Args:
            stability: 记忆稳定性
            elapsed_days: 经过的天数
            
        Returns:
            记忆保留率
        """
        if elapsed_days <= 0:
            return 1.0
        return math.exp(-elapsed_days / stability)
    
    def _calculate_learning_factor(self, card: Card) -> float:
        """计算卡片的学习因子
        
        基于卡片的历史表现、标签等计算个性化的学习因子
        
        Args:
            card: 卡片
            
        Returns:
            学习因子，默认为1.0，大于1表示需要更长间隔，小于1表示需要更短间隔
        """
        # 如果卡片已经有学习因子，使用它作为基础
        factor = card.learning_factor
        
        # 根据历史评分调整因子
        if len(card.review_logs) >= 3:
            avg_rating = card.average_rating
            if avg_rating > 3.5:  # 评分很高，可以增加间隔
                factor *= 1.1
            elif avg_rating < 2.5:  # 评分较低，需要减少间隔
                factor *= 0.9
        
        # 根据标签调整因子
        if 'difficult' in card.tags:
            factor *= 0.85  # 困难内容减少15%的间隔
        elif 'easy' in card.tags:
            factor *= 1.15  # 简单内容增加15%的间隔
        
        # 限制因子范围
        return max(0.5, min(1.5, factor))
    
    def review_card(self, card: Card, rating: int, review_time: Optional[datetime] = None) -> Card:
        """复习卡片，更新记忆状态
        
        Args:
            card: 待复习的卡片
            rating: 复习评分 (1-4)
            review_time: 复习时间，如果为None则使用当前时间
            
        Returns:
            更新后的卡片
        """
        # 确保有复习时间
        actual_review_time = review_time if review_time is not None else datetime.now()
        
        # 如果是新卡片，先初始化
        if card.is_new:
            card = self.init_card(card)
            elapsed_days = 0
            scheduled_days = 0
        else:
            # 计算实际间隔天数
            last_review_time = card.review_logs[-1].timestamp if card.review_logs else card.created_at
            elapsed_days = (actual_review_time - last_review_time).total_seconds() / (24 * 3600)
            
            # 计划间隔
            scheduled_days = (card.due_date - last_review_time).days
        
        # 确保记忆状态已初始化
        if card.memory_state is None:
            card.memory_state = MemoryState(stability=self.INIT_STABILITY, difficulty=self.INIT_DIFFICULTY)
        
        # 更新难度和稳定性
        current_difficulty = card.memory_state.difficulty
        current_stability = card.memory_state.stability
        
        new_difficulty = self._update_difficulty(current_difficulty, rating)
        new_stability = self._update_stability(current_stability, new_difficulty, rating, elapsed_days)
        
        # 更新记忆状态
        card.memory_state = MemoryState(
            stability=new_stability,
            difficulty=new_difficulty
        )
        
        # 计算个性化学习因子
        learning_factor = self._calculate_learning_factor(card)
        card.learning_factor = learning_factor  # 更新卡片的学习因子
        
        # 计算下次复习间隔
        next_interval_days = self.next_interval(new_stability, learning_factor)
        card.due_date = actual_review_time + timedelta(days=next_interval_days)
        
        # 记录本次复习
        review_log = ReviewLog(
            timestamp=actual_review_time,
            rating=rating,
            elapsed_days=elapsed_days,
            scheduled_days=scheduled_days
        )
        card.review_logs.append(review_log)
        
        # 收集复习数据用于自适应优化
        if self.enable_adaptive_params:
            self.recent_reviews.append((card, review_log))
            
            # 当收集足够多的复习记录时，尝试优化参数
            if len(self.recent_reviews) >= self.optimization_threshold:
                self._try_optimize_params()
        
        return card
    
    def _try_optimize_params(self):
        """尝试优化FSRS参数"""
        try:
            # 收集所有卡片
            cards = []
            for card, _ in self.recent_reviews:
                if card not in cards and len(card.review_logs) >= 2:
                    cards.append(card)
            
            # 如果有足够的卡片数据，进行优化
            if len(cards) >= 10:
                print(f"开始优化FSRS参数，使用 {len(cards)} 张卡片的数据...")
                
                # 优化参数
                new_params = self.optimizer.optimize(cards, self.w, iterations=50)
                
                # 如果优化成功，更新参数
                if new_params and len(new_params) == len(self.w):
                    self.w = new_params
                    self._save_params()
                    print("FSRS参数优化完成并保存")
            
            # 清空收集的复习记录
            self.recent_reviews = []
        except Exception as e:
            print(f"参数优化失败: {e}")
    
    def get_due_cards(self, cards: List[Card], current_time: Optional[datetime] = None) -> List[Card]:
        """获取当前需要复习的卡片
        
        Args:
            cards: 所有卡片列表
            current_time: 当前时间，如果为None则使用当前时间
            
        Returns:
            需要复习的卡片列表
        """
        actual_time = current_time if current_time is not None else datetime.now()
        return [card for card in cards if card.due_date <= actual_time]
    
    def predict_retention(self, card: Card, days_in_future: int) -> float:
        """预测未来某天的记忆保留率
        
        Args:
            card: 卡片
            days_in_future: 未来天数
            
        Returns:
            预测的记忆保留率 (0-1)
        """
        if not card.memory_state:
            return 0.0
        
        stability = card.memory_state.stability
        return self._forgetting_curve(stability, days_in_future)
    
    def predict_recall_probability(self, cards: List[Card], days: List[int]) -> Dict[str, List[float]]:
        """预测多张卡片在未来多个时间点的记忆概率
        
        Args:
            cards: 卡片列表
            days: 未来天数列表
            
        Returns:
            卡片ID到记忆概率列表的映射
        """
        results = {}
        for card in cards:
            if card.memory_state:
                probs = [self.predict_retention(card, day) for day in days]
                results[card.id] = probs
        return results
    
    def estimate_workload(self, cards: List[Card], days: int = 30) -> List[int]:
        """估计未来一段时间内每天的复习量
        
        Args:
            cards: 所有卡片列表
            days: 预测的天数
            
        Returns:
            每天预计需要复习的卡片数量列表
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        workload = [0] * days
        
        for card in cards:
            if card.due_date:
                due_day = (card.due_date - today).days
                if 0 <= due_day < days:
                    workload[due_day] += 1
        
        return workload 