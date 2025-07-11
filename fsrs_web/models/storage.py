#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据存储模块，用于保存和加载卡片状态
"""

import os
import pickle
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .fsrs import Card, MemoryState, ReviewLog


class CardStorage:
    """卡片数据存储类"""
    
    def __init__(self, storage_file: str = 'card_states.pkl'):
        """初始化存储
        
        Args:
            storage_file: 数据文件路径
        """
        self.storage_file = storage_file
        self.cards: Dict[str, Card] = {}
        self.load()
    
    def load(self) -> None:
        """从文件加载卡片数据"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'rb') as f:
                    self.cards = pickle.load(f)
                print(f"已加载 {len(self.cards)} 张卡片")
            except Exception as e:
                print(f"加载卡片数据失败: {e}")
                # 如果加载失败，创建备份并使用空数据
                if os.path.exists(self.storage_file):
                    backup_file = f"{self.storage_file}.bak"
                    try:
                        os.rename(self.storage_file, backup_file)
                        print(f"已创建备份: {backup_file}")
                    except:
                        pass
                self.cards = {}
        else:
            self.cards = {}
    
    def save(self) -> None:
        """保存卡片数据到文件"""
        try:
            with open(self.storage_file, 'wb') as f:
                pickle.dump(self.cards, f)
            print(f"已保存 {len(self.cards)} 张卡片")
        except Exception as e:
            print(f"保存卡片数据失败: {e}")
    
    def get_card(self, card_id: str) -> Optional[Card]:
        """获取卡片
        
        Args:
            card_id: 卡片ID
            
        Returns:
            卡片对象，如果不存在则返回None
        """
        return self.cards.get(card_id)
    
    def add_card(self, card: Card) -> Card:
        """添加卡片
        
        Args:
            card: 卡片对象
            
        Returns:
            添加的卡片对象
        """
        self.cards[card.id] = card
        self.save()
        return card
    
    def update_card(self, card: Card) -> Card:
        """更新卡片
        
        Args:
            card: 卡片对象
            
        Returns:
            更新后的卡片对象
        """
        self.cards[card.id] = card
        self.save()
        return card
    
    def delete_card(self, card_id: str) -> bool:
        """删除卡片
        
        Args:
            card_id: 卡片ID
            
        Returns:
            是否删除成功
        """
        if card_id in self.cards:
            del self.cards[card_id]
            self.save()
            return True
        return False
    
    def get_all_cards(self) -> List[Card]:
        """获取所有卡片
        
        Returns:
            所有卡片的列表
        """
        return list(self.cards.values())
    
    def get_cards_by_unit(self, unit_id: str) -> List[Card]:
        """获取指定单元的所有卡片
        
        Args:
            unit_id: 单元ID
            
        Returns:
            指定单元的卡片列表
        """
        return [card for card in self.cards.values() if card.unit_id == unit_id]
    
    def get_due_cards(self, current_time: Optional[datetime] = None) -> List[Card]:
        """获取当前需要复习的卡片
        
        Args:
            current_time: 当前时间，如果为None则使用当前时间
            
        Returns:
            需要复习的卡片列表
        """
        actual_time = current_time if current_time is not None else datetime.now()
        return [card for card in self.cards.values() if card.due_date <= actual_time]
    
    def import_vocabulary_from_excel(self, excel_path: str, unit_id: str = 'unit1') -> List[Card]:
        """从Excel导入词汇
        
        Args:
            excel_path: Excel文件路径
            unit_id: 单元ID
            
        Returns:
            导入的卡片列表
        """
        try:
            import pandas as pd
            
            # 读取Excel文件
            df = pd.read_excel(excel_path)
            
            # 跳过第一行，并获取B, C, D, E列 (索引1, 2, 3, 4)
            if len(df.columns) < 5:
                print("Excel文件格式不正确，列数不足")
                return []
            
            # 提取所需列
            word_df = df.iloc[:, 1:5]  # 选择B, C, D, E列
            
            created_cards = []
            now = datetime.now()
            
            # 删除该单元的所有现有卡片
            existing_cards = self.get_cards_by_unit(unit_id)
            for card in existing_cards:
                self.delete_card(card.id)
            
            # 创建新卡片
            for _, row in word_df.iterrows():
                word = row.iloc[0]  # 单词 (B列)
                pos = row.iloc[1]   # 词性 (C列)
                chinese = row.iloc[2]  # 中文翻译 (D列)
                english = row.iloc[3]  # 英文定义 (E列)
                
                # 跳过空行
                if pd.isna(word) or str(word).strip() == '':
                    continue
                
                # 创建卡片正面内容
                front_content = f"""<div class="word-card">
    <h3 class="word">{word}</h3>
    <div class="part-of-speech">{pos if not pd.isna(pos) else ''}</div>
</div>"""
                
                # 创建卡片背面内容
                back_content = f"""<div class="word-card">
    <h3 class="word">{word}</h3>
    <div class="part-of-speech">{pos if not pd.isna(pos) else ''}</div>
    <div class="definition chinese">{chinese if not pd.isna(chinese) else ''}</div>
    <div class="definition english">{english if not pd.isna(english) else ''}</div>
</div>"""
                
                card_id = f"{unit_id}_{str(uuid.uuid4())[:8]}"
                card = Card(
                    id=card_id,
                    unit_id=unit_id,
                    front=front_content,
                    back=back_content,
                    created_at=now,
                    due_date=now,  # 新卡片立即可以学习
                    memory_state=None,
                    review_logs=[]
                )
                self.add_card(card)
                created_cards.append(card)
            
            print(f"已从Excel导入 {len(created_cards)} 张卡片到单元 {unit_id}")
            return created_cards
        
        except Exception as e:
            print(f"导入Excel数据失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def create_sample_cards_for_unit(self, unit_id: str, num_cards: int = 5) -> List[Card]:
        """为指定单元创建示例卡片
        
        Args:
            unit_id: 单元ID
            num_cards: 要创建的卡片数量
            
        Returns:
            创建的卡片列表
        """
        # Unit 1 (Number) 的示例内容
        unit1_samples = [
            {
                "front": "计算 12 × 8 ÷ 4 + 6",
                "back": "30。计算顺序：先乘除，后加减。12 × 8 = 96, 96 ÷ 4 = 24, 24 + 6 = 30"
            },
            {
                "front": "将 3.75 转换为分数",
                "back": "3.75 = 3 + 0.75 = 3 + 3/4 = 15/4"
            },
            {
                "front": "25% 的 80 是多少?",
                "back": "20。计算方法：80 × 0.25 = 20"
            },
            {
                "front": "计算 2^4 × 2^3",
                "back": "2^7 = 128。指数相加：2^(4+3) = 2^7 = 128"
            },
            {
                "front": "将 0.00057 写成标准形式",
                "back": "5.7 × 10^-4"
            },
            {
                "front": "如果比例是 3:5，当第一个数是 18 时，第二个数是多少?",
                "back": "30。解法：18 ÷ 3 × 5 = 30"
            },
            {
                "front": "找出数列 2, 5, 8, 11, ... 的第 10 项",
                "back": "29。这是公差为 3 的等差数列，通项公式为 a_n = 2 + (n-1)*3。第 10 项为 2 + 9*3 = 29"
            },
        ]
        
        # 其他单元的默认样本
        default_samples = [
            {
                "front": f"{unit_id} 示例卡片 {i}",
                "back": f"这是 {unit_id} 的示例答案 {i}"
            }
            for i in range(1, num_cards + 1)
        ]
        
        # 根据单元选择不同的示例
        samples = unit1_samples if unit_id == 'unit1' else default_samples
        samples = samples[:num_cards]  # 限制卡片数量
        
        created_cards = []
        now = datetime.now()
        
        for i, sample in enumerate(samples):
            card_id = f"{unit_id}_{str(uuid.uuid4())[:8]}"
            card = Card(
                id=card_id,
                unit_id=unit_id,
                front=sample["front"],
                back=sample["back"],
                created_at=now,
                due_date=now,  # 新卡片立即可以学习
                memory_state=None,
                review_logs=[]
            )
            self.add_card(card)
            created_cards.append(card)
        
        return created_cards 