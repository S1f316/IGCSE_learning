#!/usr/bin/env python3
"""
添加新系统卡片的脚本
用法：
  python scripts/add_system_card.py <unit_id> <front_content> <back_content>
  
示例：
  python scripts/add_system_card.py unit1 "新单词" "新单词的解释"
"""
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / 'fsrs_web'))

# 设置环境变量
os.environ['USE_DATABASE'] = 'true'
os.environ['DATABASE_URL'] = 'postgresql://chusheng_db_5djd_user:CEVrhJEIfditwICZpC4xfRwW0hXxFzJo@dpg-d1ov19ur433s73cpu850-a.singapore-postgres.render.com/chusheng_db_5djd'

try:
    from models.database import get_db_session, SystemCard, User, UserCardState
    from app import create_card_states_for_all_users
except ImportError as e:
    print(f"导入失败: {e}")
    sys.exit(1)

def add_system_card(unit_id, front, back):
    """添加新的系统卡片"""
    # 生成卡片ID
    card_id = f"{unit_id}_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now()
    
    session = get_db_session()
    try:
        # 检查卡片是否已存在
        existing = session.query(SystemCard).filter_by(id=card_id).first()
        if existing:
            print(f"卡片 {card_id} 已存在")
            return False
        
        # 创建新系统卡片
        system_card = SystemCard(
            id=card_id,
            unit_id=unit_id,
            front=front,
            back=back,
            created_at=created_at
        )
        session.add(system_card)
        session.commit()
        
        print(f"✅ 成功创建系统卡片: {card_id}")
        print(f"   单元: {unit_id}")
        print(f"   正面: {front[:50]}...")
        print(f"   背面: {back[:50]}...")
        
        # 为所有现有用户创建该卡片的默认状态
        success = create_card_states_for_all_users(card_id, unit_id, front, back, created_at)
        if success:
            print(f"✅ 为所有用户创建了卡片 {card_id} 的默认状态")
        else:
            print(f"❌ 为用户创建卡片状态失败")
        
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ 添加系统卡片失败: {e}")
        return False
    finally:
        session.close()

def main():
    if len(sys.argv) != 4:
        print("用法: python scripts/add_system_card.py <unit_id> <front_content> <back_content>")
        print("示例: python scripts/add_system_card.py unit1 '新单词' '新单词的解释'")
        sys.exit(1)
    
    unit_id = sys.argv[1]
    front = sys.argv[2]
    back = sys.argv[3]
    
    print(f"正在添加系统卡片...")
    print(f"单元: {unit_id}")
    print(f"正面: {front}")
    print(f"背面: {back}")
    print("-" * 50)
    
    success = add_system_card(unit_id, front, back)
    if success:
        print("✅ 系统卡片添加完成！")
    else:
        print("❌ 系统卡片添加失败！")
        sys.exit(1)

if __name__ == '__main__':
    main() 