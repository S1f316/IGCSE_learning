#!/usr/bin/env python3
"""
查看数据库中指定单元的单词

用法：
    python check_database_words.py [unit_id]

如果不提供 unit_id，默认查看 Unit1 的单词
"""
import os
import sys

# 设置环境变量以确保使用数据库
os.environ.setdefault("USE_DATABASE", "true")

# 项目内导入
from models.database import get_db_session, SystemCard

# 获取要查看的单元ID
unit_id = sys.argv[1] if len(sys.argv) > 1 else "unit1"

session = get_db_session()
try:
    # 查询指定单元的单词
    cards = session.query(SystemCard).filter_by(unit_id=unit_id).order_by(SystemCard.id).all()
    
    if not cards:
        print(f"❌ 单元 {unit_id} 中没有找到单词")
    else:
        print(f"📚 单元 {unit_id} 中的单词 ({len(cards)} 个):")
        print("-" * 100)
        print(f"{'序号':<4} {'卡片ID':<15} {'单词':<20} {'含义'}")
        print("-" * 100)
        
        for i, card in enumerate(cards, 1):
            print(f"{i:<4} {card.id:<15} {card.front:<20} {card.back}")
        
        print("-" * 100)
        print(f"总计: {len(cards)} 个单词")

    # 显示所有单元ID
    units = session.query(SystemCard.unit_id).distinct().all()
    print(f"\n数据库中所有单元ID：{sorted([u[0] for u in units])}")
    
    # 显示总单词数
    total_cards = session.query(SystemCard).count()
    print(f"数据库中总单词数：{total_cards}")

except Exception as e:
    print(f"❌ 查询失败: {e}")
finally:
    session.close() 