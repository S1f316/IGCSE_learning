#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据存储模块，用于保存和加载卡片状态
"""

import os
import json
import pickle
from datetime import datetime
from dataclasses import asdict
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 导入配置
from fsrs_web.config import CARD_STATES_FILE, USERS_FILE, USE_DATABASE

# 数据库操作
database = None
if USE_DATABASE:
    try:
        from fsrs_web.models.database import (
            initialize_db, get_db_session, 
            User, SystemCard, UserCardState, UserFSRSParam,
            migrate_from_files
        )
        database = True
        # 确保数据库表已创建
        initialize_db()
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        database = False

class StorageAdapter:
    """存储适配器，处理文件存储和数据库存储"""
    
    @staticmethod
    def load_users():
        """加载用户数据"""
        if USE_DATABASE and database:
            # 使用数据库存储
            session = get_db_session()
            try:
                users = {}
                for user in session.query(User).all():
                    users[user.username] = {
                        'password': user.password,
                        'email': user.email,
                        'created_at': user.created_at
                    }
                return users
            except Exception as e:
                print(f"从数据库加载用户失败: {e}")
                return {}
            finally:
                session.close()
        else:
            # 使用文件存储
            if os.path.exists(USERS_FILE):
                try:
                    with open(USERS_FILE, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    print(f"加载用户数据失败: {e}")
            return {}
    
    @staticmethod
    def save_users(users):
        """保存用户数据"""
        if USE_DATABASE and database:
            # 使用数据库存储
            session = get_db_session()
            try:
                # 删除所有现有用户
                existing_users = {user.username: user for user in session.query(User).all()}
                
                # 更新或添加用户
                for username, user_data in users.items():
                    if username in existing_users:
                        # 更新现有用户
                        existing_user = existing_users[username]
                        existing_user.password = user_data.get('password', '')
                        existing_user.email = user_data.get('email', '')
                    else:
                        # 添加新用户
                        new_user = User(
                            username=username,
                            password=user_data.get('password', ''),
                            email=user_data.get('email', ''),
                            created_at=user_data.get('created_at', datetime.now())
                        )
                        session.add(new_user)
                
                # 删除不在新数据中的用户
                for username in list(existing_users.keys()):
                    if username not in users:
                        session.delete(existing_users[username])
                        
                session.commit()
            except Exception as e:
                session.rollback()
                print(f"保存用户数据到数据库失败: {e}")
            finally:
                session.close()
        else:
            # 使用文件存储
            try:
                os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
                with open(USERS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(users, f)
            except Exception as e:
                print(f"保存用户数据失败: {e}")
    
    @staticmethod
    def load_cards(system_cards_class, card_state_class, user_fsrs_params_class):
        """加载卡片数据"""
        if USE_DATABASE and database:
            # 使用数据库存储
            session = get_db_session()
            try:
                # 加载系统卡片
                system_cards = {}
                for card in session.query(SystemCard).all():
                    system_card = system_cards_class(
                        id=card.id,
                        unit_id=card.unit_id,
                        front=card.front,
                        back=card.back,
                        created_at=card.created_at,
                        due_date=card.created_at  # 设置默认值
                    )
                    system_cards[card.id] = system_card
                
                # 加载用户卡片状态
                user_card_states = {}
                for user_state in session.query(UserCardState).all():
                    username = user_state.username
                    if username not in user_card_states:
                        user_card_states[username] = {}
                    
                    # 创建记忆状态
                    memory_state = None
                    if user_state.memory_stability is not None and user_state.memory_difficulty is not None:
                        memory_state_class = getattr(sys.modules[system_cards_class.__module__], 'MemoryState')
                        memory_state = memory_state_class(
                            stability=user_state.memory_stability,
                            difficulty=user_state.memory_difficulty
                        )
                    
                    # 获取复习记录
                    review_logs = []
                    if user_state.review_logs:
                        review_log_class = getattr(sys.modules[system_cards_class.__module__], 'ReviewLog')
                        logs_data = json.loads(user_state.review_logs)
                        for log_data in logs_data:
                            # 将字符串时间戳转换为datetime对象
                            if isinstance(log_data['timestamp'], str):
                                timestamp = datetime.fromisoformat(log_data['timestamp'])
                            else:
                                timestamp = log_data['timestamp']
                            
                            log = review_log_class(
                                timestamp=timestamp,
                                rating=log_data['rating'],
                                elapsed_days=log_data['elapsed_days'],
                                scheduled_days=log_data['scheduled_days']
                            )
                            review_logs.append(log)
                    
                    # 创建用户卡片状态
                    card_state = card_state_class(
                        card_id=user_state.card_id or '',
                        is_viewed=user_state.is_viewed,
                        memory_state=memory_state,
                        review_logs=review_logs,
                        due_date=user_state.due_date,
                        learning_factor=user_state.learning_factor,
                        is_user_card=user_state.is_user_card
                    )
                    
                    # 设置用户卡片数据
                    if user_state.is_user_card and user_state.user_card_data:
                        card_state.user_card_data = user_state.get_user_card_data()
                    
                    user_card_states[username][user_state.card_id or user_state.id] = card_state
                
                # 加载用户FSRS参数
                user_fsrs_params = {}
                for user_param in session.query(UserFSRSParam).all():
                    params = user_param.get_params()
                    user_fsrs_params[user_param.username] = user_fsrs_params_class(
                        params=params,
                        last_updated=user_param.last_updated,
                        optimization_count=user_param.optimization_count
                    )
                
                return system_cards, user_card_states, user_fsrs_params
            except Exception as e:
                print(f"从数据库加载卡片数据失败: {e}")
                import traceback
                traceback.print_exc()
                return {}, {}, {}
            finally:
                session.close()
        else:
            # 使用文件存储
            system_cards = {}
            user_card_states = {}
            user_fsrs_params = {}
            
            if os.path.exists(CARD_STATES_FILE):
                try:
                    with open(CARD_STATES_FILE, 'rb') as f:
                        all_data = pickle.load(f)
                        
                        # 检查数据格式
                        if isinstance(all_data, dict):
                            # 检查是否是新格式(包含system_cards和user_card_states)
                            if 'system_cards' in all_data and 'user_card_states' in all_data:
                                system_cards = all_data['system_cards']
                                user_card_states = all_data['user_card_states']
                                # 加载用户FSRS参数
                                if 'user_fsrs_params' in all_data:
                                    user_fsrs_params = all_data['user_fsrs_params']
                except Exception as e:
                    print(f"加载卡片数据失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            return system_cards, user_card_states, user_fsrs_params
    
    @staticmethod
    def save_cards(system_cards, user_card_states, user_fsrs_params):
        """保存卡片数据"""
        if USE_DATABASE and database:
            # 使用数据库存储
            # 这里我们做的不是每次保存所有数据，而是应该单独更新修改的数据
            # 但为了简化迁移过程，我们可以先实现一个完全覆盖的版本
            try:
                # 加载用户数据
                users = StorageAdapter.load_users()
                # 迁移所有数据
                success = migrate_from_files(system_cards, user_card_states, user_fsrs_params, users)
                if success:
                    print("成功将数据保存到数据库")
                else:
                    print("保存数据到数据库失败")
            except Exception as e:
                print(f"保存卡片数据到数据库失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            # 使用文件存储
            try:
                # 确保目录存在
                os.makedirs(os.path.dirname(CARD_STATES_FILE), exist_ok=True)
                
                # 将数据打包为新格式
                all_data = {
                    'system_cards': system_cards,
                    'user_card_states': user_card_states,
                    'user_fsrs_params': user_fsrs_params
                }
                
                with open(CARD_STATES_FILE, 'wb') as f:
                    pickle.dump(all_data, f)
            except Exception as e:
                print(f"保存卡片数据失败: {e}")
                import traceback
                traceback.print_exc()

    @staticmethod
    def migrate_data():
        """将数据从文件迁移到数据库"""
        if not USE_DATABASE or not database:
            print("数据库未启用，无法迁移数据")
            return False
        
        # 检查文件是否存在
        if not os.path.exists(CARD_STATES_FILE) or not os.path.exists(USERS_FILE):
            print("找不到数据文件，无法迁移数据")
            return False
        
        try:
            # 加载文件数据
            from fsrs_web.app import system_cards, user_card_states, user_fsrs_params
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users_data = json.load(f)
            
            # 迁移到数据库
            return migrate_from_files(system_cards, user_card_states, user_fsrs_params, users_data)
        except Exception as e:
            print(f"数据迁移失败: {e}")
            import traceback
            traceback.print_exc()
            return False 