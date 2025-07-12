import json
import pickle
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Float, Integer, LargeBinary, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import DATABASE_URL

# 创建数据库引擎
engine = create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# 用户表
class User(Base):
    __tablename__ = 'users'
    
    username = Column(String(50), primary_key=True)
    password = Column(String(100), nullable=False)
    email = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    
    # 关系
    cards = relationship("UserCardState", back_populates="user", cascade="all, delete-orphan")
    fsrs_params = relationship("UserFSRSParam", back_populates="user", uselist=False, cascade="all, delete-orphan")

# 系统卡片表
class SystemCard(Base):
    __tablename__ = 'system_cards'
    
    id = Column(String(50), primary_key=True)
    unit_id = Column(String(20), nullable=False)
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    # 关系
    user_states = relationship("UserCardState", back_populates="system_card")
    
# 用户卡片状态表
class UserCardState(Base):
    __tablename__ = 'user_card_states'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), ForeignKey('users.username'), nullable=False)
    card_id = Column(String(50), ForeignKey('system_cards.id'))
    is_viewed = Column(Boolean, default=False)
    memory_stability = Column(Float, nullable=True)
    memory_difficulty = Column(Float, nullable=True)
    due_date = Column(DateTime, nullable=True)
    learning_factor = Column(Float, default=1.0)
    is_user_card = Column(Boolean, default=False)
    user_card_data = Column(Text, nullable=True)  # JSON格式存储用户自定义卡片
    review_logs = Column(Text, nullable=True)  # JSON格式存储复习记录
    
    # 关系
    user = relationship("User", back_populates="cards")
    system_card = relationship("SystemCard", back_populates="user_states")
    
    def get_review_logs(self):
        """获取复习记录"""
        if not self.review_logs:
            return []
        return json.loads(self.review_logs)
    
    def set_review_logs(self, logs):
        """设置复习记录"""
        self.review_logs = json.dumps([{
            'timestamp': log.timestamp.isoformat() if hasattr(log.timestamp, 'isoformat') else log.timestamp,
            'rating': log.rating,
            'elapsed_days': log.elapsed_days,
            'scheduled_days': log.scheduled_days
        } for log in logs])
    
    def get_user_card_data(self):
        """获取用户卡片数据"""
        if not self.user_card_data:
            return None
        data = json.loads(self.user_card_data)
        
        # 将字符串日期转换为datetime对象
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
            
        return data
    
    def set_user_card_data(self, data):
        """设置用户卡片数据"""
        if data:
            # 处理datetime对象
            if 'created_at' in data and hasattr(data['created_at'], 'isoformat'):
                data = dict(data)
                data['created_at'] = data['created_at'].isoformat()
                
            self.user_card_data = json.dumps(data)
        else:
            self.user_card_data = None

# 用户FSRS参数表
class UserFSRSParam(Base):
    __tablename__ = 'user_fsrs_params'
    
    username = Column(String(50), ForeignKey('users.username'), primary_key=True)
    params = Column(Text, nullable=True)  # JSON格式存储参数
    last_updated = Column(DateTime, default=datetime.now)
    optimization_count = Column(Integer, default=0)
    
    # 关系
    user = relationship("User", back_populates="fsrs_params")
    
    def get_params(self):
        """获取FSRS参数"""
        if not self.params:
            return None
        return json.loads(self.params)
    
    def set_params(self, params):
        """设置FSRS参数"""
        if params:
            self.params = json.dumps(params)
        else:
            self.params = None

def initialize_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(engine)

def get_db_session():
    """获取数据库会话"""
    return Session()

# 数据迁移: 从文件到数据库
def migrate_from_files(system_cards_data, user_card_states_data, user_fsrs_params_data, users_data):
    """从文件数据迁移到数据库"""
    session = get_db_session()
    try:
        # 清空现有数据
        session.query(UserCardState).delete()
        session.query(SystemCard).delete()
        session.query(UserFSRSParam).delete()
        session.query(User).delete()
        
        # 导入用户数据
        for username, user_data in users_data.items():
            user = User(
                username=username,
                password=user_data.get('password', ''),
                email=user_data.get('email', '')
            )
            session.add(user)
        
        # 导入系统卡片
        for card_id, card in system_cards_data.items():
            system_card = SystemCard(
                id=card.id,
                unit_id=card.unit_id,
                front=card.front,
                back=card.back,
                created_at=card.created_at
            )
            session.add(system_card)
        
        # 导入用户卡片状态
        for username, states in user_card_states_data.items():
            for card_id, state in states.items():
                # 创建用户卡片状态
                user_state = UserCardState(
                    username=username,
                    card_id=card_id if not state.is_user_card else None,
                    is_viewed=state.is_viewed,
                    memory_stability=state.memory_state.stability if state.memory_state else None,
                    memory_difficulty=state.memory_state.difficulty if state.memory_state else None,
                    due_date=state.due_date,
                    learning_factor=state.learning_factor,
                    is_user_card=state.is_user_card
                )
                
                # 设置用户卡片数据
                if state.is_user_card and state.user_card_data:
                    user_state.set_user_card_data(state.user_card_data)
                
                # 设置复习记录
                if state.review_logs:
                    user_state.set_review_logs(state.review_logs)
                    
                session.add(user_state)
        
        # 导入用户FSRS参数
        for username, fsrs_param in user_fsrs_params_data.items():
            user_param = UserFSRSParam(
                username=username,
                params=json.dumps(fsrs_param.params),
                last_updated=fsrs_param.last_updated,
                optimization_count=fsrs_param.optimization_count
            )
            session.add(user_param)
            
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"迁移数据失败: {e}")
        return False
    finally:
        session.close() 