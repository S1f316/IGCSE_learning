#!/usr/bin/env python3
"""
修复用户卡片状态的单元信息
确保用户卡片状态与系统卡片的单元保持一致
"""
import os
import sys

# 设置环境变量
os.environ['USE_DATABASE'] = 'true'
os.environ['DATABASE_URL'] = 'postgresql://chusheng_db_5djd_user:CEVrhJEIfditwICZpC4xfRwW0hXxFzJo@dpg-d1ov19ur433s73cpu850-a.singapore-postgres.render.com/chusheng_db_5djd'

try:
    from models.database import get_db_session, SystemCard, User, UserCardState
except ImportError as e:
    print(f"导入失败: {e}")
    sys.exit(1)

def fix_user_card_states():
    """修复用户卡片状态的单元信息"""
    session = get_db_session()
    try:
        # 获取所有系统卡片
        system_cards = session.query(SystemCard).all()
        print(f"✅ 从数据库中获取了 {len(system_cards)} 张系统卡片")
        
        # 创建卡片ID到单元的映射
        card_id_to_unit = {}
        for card in system_cards:
            card_id_to_unit[card.id] = card.unit_id
        
        # 获取所有用户
        users = session.query(User).all()
        print(f"✅ 从数据库中获取了 {len(users)} 个用户")
        
        # 修复每个用户的卡片状态
        total_fixed = 0
        for user in users:
            user_fixed = 0
            print(f"正在处理用户 {user.username} 的卡片状态...")
            
            # 获取用户的所有卡片状态
            user_states = session.query(UserCardState).filter_by(username=user.username).all()
            print(f"  用户 {user.username} 有 {len(user_states)} 个卡片状态")
            
            # 检查是否有缺失的系统卡片
            user_card_ids = {state.card_id for state in user_states if not state.is_user_card}
            missing_card_ids = set(card_id_to_unit.keys()) - user_card_ids
            
            # 为缺失的系统卡片创建状态
            for card_id in missing_card_ids:
                card = session.query(SystemCard).filter_by(id=card_id).first()
                if card:
                    new_state = UserCardState(
                        username=user.username,
                        card_id=card_id,
                        is_viewed=False,
                        due_date=card.created_at,
                        learning_factor=1.0,
                        is_user_card=False
                    )
                    session.add(new_state)
                    user_fixed += 1
            
            # 更新现有卡片状态的单元
            for state in user_states:
                if not state.is_user_card and state.card_id in card_id_to_unit:
                    card = session.query(SystemCard).filter_by(id=state.card_id).first()
                    if card and card.unit_id != state.card_id.split('_')[0]:
                        print(f"  修复卡片 {state.card_id} 的单元: {state.card_id.split('_')[0]} -> {card.unit_id}")
                        user_fixed += 1
            
            if user_fixed > 0:
                print(f"  为用户 {user.username} 修复了 {user_fixed} 个卡片状态")
            total_fixed += user_fixed
        
        # 提交更改
        session.commit()
        print(f"\n✅ 总共修复了 {total_fixed} 个卡片状态")
        
        # 验证结果
        print("\n验证结果:")
        for user in users:
            # 统计用户卡片状态的单元分布
            user_states = session.query(UserCardState).filter_by(username=user.username).all()
            user_unit_counts = {}
            for state in user_states:
                if not state.is_user_card:
                    card = session.query(SystemCard).filter_by(id=state.card_id).first()
                    if card:
                        if card.unit_id not in user_unit_counts:
                            user_unit_counts[card.unit_id] = 0
                        user_unit_counts[card.unit_id] += 1
            
            print(f"用户 {user.username} 的卡片单元分布:")
            for unit_id, count in sorted(user_unit_counts.items()):
                print(f"  {unit_id}: {count} 张卡片")
        
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ 修复卡片状态失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

def main():
    print("正在修复用户卡片状态的单元信息...")
    print("-" * 50)
    
    success = fix_user_card_states()
    if success:
        print("✅ 修复完成！")
    else:
        print("❌ 修复失败！")
        sys.exit(1)

if __name__ == '__main__':
    main() 