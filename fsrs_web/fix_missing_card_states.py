#!/usr/bin/env python3
"""
修复缺失卡片状态的脚本
为所有现有用户创建缺失的系统卡片状态
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

def fix_missing_card_states():
    """为所有用户创建缺失的卡片状态"""
    session = get_db_session()
    try:
        # 获取所有用户
        users = session.query(User).all()
        print(f"找到 {len(users)} 个用户")
        
        # 获取所有系统卡片
        system_cards = session.query(SystemCard).all()
        print(f"找到 {len(system_cards)} 张系统卡片")
        
        total_created = 0
        
        for user in users:
            print(f"检查用户 {user.username} 的卡片状态...")
            user_created = 0
            
            for card in system_cards:
                # 检查是否已存在
                existing = session.query(UserCardState).filter_by(
                    username=user.username, 
                    card_id=card.id
                ).first()
                
                if not existing:
                    # 创建默认状态
                    user_state = UserCardState(
                        username=user.username,
                        card_id=card.id,
                        is_viewed=False,
                        due_date=card.created_at,
                        learning_factor=1.0,
                        is_user_card=False
                    )
                    session.add(user_state)
                    user_created += 1
            
            session.commit()
            print(f"  为用户 {user.username} 创建了 {user_created} 个缺失的卡片状态")
            total_created += user_created
        
        print(f"✅ 总共创建了 {total_created} 个缺失的卡片状态")
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
    print("正在修复缺失的卡片状态...")
    print("-" * 50)
    
    success = fix_missing_card_states()
    if success:
        print("✅ 修复完成！")
    else:
        print("❌ 修复失败！")
        sys.exit(1)

if __name__ == '__main__':
    main() 