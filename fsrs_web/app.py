import os
import pickle
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, jsonify, session, flash
from collections import defaultdict
from functools import wraps
import math
import random
import re
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from io import BytesIO
from PIL import Image
import uuid

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入配置
from config import DATA_DIR, CARD_STATES_FILE, USERS_FILE, SECRET_KEY, DEBUG, USE_DATABASE

# 尝试导入FSRS模块
try:
    # 首先尝试从models目录导入
    from fsrs_web.models.fsrs import FSRS, Card, ReviewLog as FsrsReviewLog
except ImportError:
    try:
        # 如果上面失败，尝试从相对路径导入
        from models.fsrs import FSRS, Card, ReviewLog as FsrsReviewLog
    except ImportError:
        # 如果仍然无法导入，直接从文件导入
        import importlib.util
        import dataclasses
        from typing import List, Optional, Dict
        import math
        import random
        import json
        import os
        
        # 定义必要的类
        @dataclasses.dataclass
        class MemoryState:
            stability: float
            difficulty: float
            
            def __str__(self):
                return f"稳定性: {self.stability:.2f}, 难度: {self.difficulty:.2f}"
        
        @dataclasses.dataclass
        class ReviewLog:
            timestamp: datetime
            rating: int
            elapsed_days: float
            scheduled_days: int
        
        @dataclasses.dataclass
        class Card:
            id: str
            unit_id: str
            front: str
            back: str
            created_at: datetime
            due_date: datetime
            memory_state: Optional[MemoryState] = None
            review_logs: List[ReviewLog] = dataclasses.field(default_factory=list)
            is_viewed: bool = False  # 标记卡片是否已查看
            tags: List[str] = dataclasses.field(default_factory=list)  # 卡片标签
            learning_factor: float = 1.0  # 学习因子
            
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
        
        # 增强版FSRS
        class FSRS:
            # FSRS 默认参数
            DEFAULT_PARAMS = [
                0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94,
                2.18, 0.05, 0.34, 1.26, 0.29, 2.61
            ]
            
            # 记忆状态初始值
            INIT_STABILITY = 1.0
            INIT_DIFFICULTY = 5.0
            
            def __init__(self, desired_retention=0.9, maximum_interval=36500, params=None):
                self.desired_retention = desired_retention
                self.maximum_interval = maximum_interval
                self.w = params if params is not None else self.DEFAULT_PARAMS
            
            def next_interval(self, stability, learning_factor=1.0):
                interval = stability * math.log(self.desired_retention) * -1.0 * learning_factor
                fuzz = random.uniform(0.95, 1.05)
                interval *= fuzz
                interval = min(interval, self.maximum_interval)
                return max(1, round(interval))
            
            def _forgetting_curve(self, stability, elapsed_days):
                """遗忘曲线，计算给定稳定性和经过天数下的记忆保留率"""
                if elapsed_days <= 0:
                    return 1.0
                return math.exp(-elapsed_days / stability)
            
            def predict_retention(self, card, days_in_future):
                """预测未来某天的记忆保留率"""
                if not card.memory_state:
                    return 0.0
                
                stability = card.memory_state.stability
                return self._forgetting_curve(stability, days_in_future)
            
            def predict_recall_probability(self, cards, days):
                """预测多张卡片在未来多个时间点的记忆概率"""
                results = {}
                for card in cards:
                    if card.memory_state:
                        probs = [self.predict_retention(card, day) for day in days]
                        results[card.id] = probs
                return results
            
            def estimate_workload(self, cards, days=30):
                """估计未来一段时间内每天的复习量"""
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                workload = [0] * days
                
                for card in cards:
                    if card.due_date:
                        due_day = (card.due_date - today).days
                        if 0 <= due_day < days:
                            workload[due_day] += 1
                
                return workload
            
            def review_card(self, card, rating, review_time=None):
                # 确保有复习时间
                actual_review_time = review_time if review_time is not None else datetime.now()
                
                # 确保卡片有必要的属性
                if not hasattr(card, 'tags'):
                    card.tags = []
                if not hasattr(card, 'learning_factor'):
                    card.learning_factor = 1.0
                
                # 如果是新卡片，先初始化
                if not card.memory_state:
                    card.memory_state = MemoryState(stability=self.INIT_STABILITY, difficulty=self.INIT_DIFFICULTY)
                    elapsed_days = 0
                    scheduled_days = 0
                else:
                    # 计算实际间隔天数
                    last_review_time = card.review_logs[-1].timestamp if card.review_logs else card.created_at
                    elapsed_days = (actual_review_time - last_review_time).total_seconds() / (24 * 3600)
                    
                    # 计划间隔
                    scheduled_days = (card.due_date - last_review_time).days if hasattr(card, 'due_date') and card.due_date else 0
                
                # 根据评分调整稳定性
                if rating == 1:
                    new_stability = card.memory_state.stability * 0.5
                elif rating == 2:
                    new_stability = card.memory_state.stability * 0.8
                elif rating == 3:
                    new_stability = card.memory_state.stability * 1.2
                else:  # rating == 4
                    new_stability = card.memory_state.stability * 1.5
                
                # 更新记忆状态
                card.memory_state.stability = max(1.0, new_stability)
                
                # 计算下次复习间隔
                next_interval_days = self.next_interval(card.memory_state.stability)
                card.due_date = actual_review_time + timedelta(days=next_interval_days)
                
                # 记录本次复习
                card.review_logs.append(ReviewLog(
                    timestamp=actual_review_time,
                    rating=rating,
                    elapsed_days=elapsed_days,
                    scheduled_days=next_interval_days
                ))
                
                return card

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['DEBUG'] = DEBUG
app.secret_key = 'fsrs_demo_secret_key'  # 用于session

# 用户数据存储
users_file = os.path.join(os.path.dirname(__file__), 'data', 'users.json')

# 确保用户数据目录存在
os.makedirs(os.path.dirname(users_file), exist_ok=True)

# 加载用户数据
def load_users():
    if StorageAdapter is not None:
        return StorageAdapter.load_users()
    else:
        if os.path.exists(users_file):
            try:
                with open(users_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

# 保存用户数据
def save_users(users):
    if StorageAdapter is not None:
        StorageAdapter.save_users(users)
    else:
        with open(users_file, 'w') as f:
            json.dump(users, f, indent=4)

# 密码哈希函数
def hash_password(password):
    # 在实际应用中，应该使用更安全的密码哈希方法，如bcrypt
    return hashlib.sha256(password.encode()).hexdigest()

# 用户认证相关函数和装饰器
def login_required(f):
    """确保用户已登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # 保存当前URL以便登录后重定向回来
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册页面"""
    if 'logged_in' in session:
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # 加载现有用户
        users = load_users()
        
        # 验证输入
        if username in users:
            error = '用户名已存在，请选择其他用户名'
        elif password != confirm_password:
            error = '两次输入的密码不一致'
        elif len(password) < 8:
            error = '密码长度至少为8个字符'
        elif not re.search(r'[a-zA-Z]', password) or not re.search(r'[0-9]', password):
            error = '密码必须包含字母和数字'
        else:
            # 创建新用户
            users[username] = {
                'password': hash_password(password),
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_login': None,
                'study_mode': 'medium'  # 设置默认学习模式为中等模式
            }
            
            # 保存用户数据
            save_users(users)
            
            # 为新用户创建所有系统卡片的默认状态
            if USE_DATABASE and StorageAdapter is not None:
                try:
                    # 引入 User 以便在数据库中创建新用户记录
                    from models.database import get_db_session, SystemCard, User, UserCardState
                    session_db = get_db_session()
                    try:
                        # 如果用户已存在则跳过创建
                        existing_user = session_db.query(User).filter_by(username=username).first()
                        if not existing_user:
                            # 创建数据库中的用户记录
                            new_user = User(
                                username=username,
                                password=hash_password(password)
                            )
                            session_db.add(new_user)

                        # 获取所有系统卡片
                        db_system_cards = session_db.query(SystemCard).all()
                        
                        # 为新用户创建所有系统卡片的默认状态
                        for card in db_system_cards:
                            user_state = UserCardState(
                                username=username,
                                card_id=card.id,
                                is_viewed=False,
                                due_date=card.created_at,
                                learning_factor=1.0,
                                is_user_card=False
                            )
                            session_db.add(user_state)
                        
                        session_db.commit()
                        print(f"为新用户 {username} 创建了 {len(db_system_cards)} 张系统卡片的默认状态")
                        # 刷新内存中的系统卡片与用户卡片状态，确保新注册用户立即可见
                        try:
                            load_cards()
                        except Exception as refresh_err:
                            print(f"刷新卡片数据失败: {refresh_err}")
                    except Exception as e:
                        session_db.rollback()
                        print(f"为新用户创建卡片状态失败: {e}")
                    finally:
                        session_db.close()
                except Exception as e:
                    print(f"导入数据库模块失败: {e}")
            else:
                # 文件存储模式：为新用户创建默认卡片状态
                if username not in user_card_states:
                    user_card_states[username] = {}
                
                # 为所有系统卡片创建默认状态
                for card_id, card in system_cards.items():
                    user_card_states[username][card_id] = CardState(
                        card_id=card_id,
                        is_viewed=False,
                        due_date=card.created_at,
                        learning_factor=1.0,
                        is_user_card=False
                    )
                
                save_cards()
                print(f"为新用户 {username} 创建了 {len(system_cards)} 张系统卡片的默认状态")
            
            # 自动登录
            session['logged_in'] = True
            session['username'] = username
            
            # 重定向到首页
            return redirect(url_for('index'))
    
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录页面"""
    # 如果用户已经登录，直接重定向到首页
    if 'logged_in' in session:
        return redirect(url_for('index'))
        
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # 检查是否为管理员账号
        if username == 'S1f' and password == 'Yifan316':
            session['logged_in'] = True
            session['username'] = username
            session['is_admin'] = True
            return redirect(url_for('admin'))
        
        # 加载用户数据
        users = load_users()
        
        # 验证用户名和密码
        if username in users and users[username]['password'] == hash_password(password):
            session['logged_in'] = True
            session['username'] = username
            session['is_admin'] = False
            
            # 更新最后登录时间
            users[username]['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            save_users(users)
            
            # 获取登录后要重定向的页面
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            error = '用户名或密码错误'
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    """用户登出"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    """管理员界面"""
    # 检查是否为管理员
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    # 加载所有用户数据
    users = load_users()
    
    return render_template('admin.html', users=users)

@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    """管理员添加用户"""
    if not session.get('is_admin'):
        return jsonify({'status': 'error', 'message': '权限不足'})
    
    username = request.form.get('username')
    password = request.form.get('password')
    if not username or not password:
        return jsonify({'status': 'error', 'message': '用户名和密码不能为空'})
    
    users = load_users()
    
    if username in users:
        return jsonify({'status': 'error', 'message': '用户名已存在'})
    
    # 添加新用户
    users[username] = {
        'password': hash_password(password),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_login': None,
        'study_mode': 'medium'  # 设置默认学习模式为中等模式
    }
    
    save_users(users)
    return jsonify({'status': 'success', 'message': '用户添加成功'})

@app.route('/admin/delete_user', methods=['POST'])
def admin_delete_user():
    """管理员删除用户"""
    if not session.get('is_admin'):
        return jsonify({'status': 'error', 'message': '权限不足'})
    
    username = request.form.get('username')
    if not username:
        return jsonify({'status': 'error', 'message': '用户名不能为空'})
    
    if username == 'S1f':
        return jsonify({'status': 'error', 'message': '不能删除管理员账号'})
    
    users = load_users()
    
    if username not in users:
        return jsonify({'status': 'error', 'message': '用户不存在'})
    
    # 删除用户
    del users[username]
    save_users(users)
    
    return jsonify({'status': 'success', 'message': '用户删除成功'})

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """个人资料页面"""
    # 获取用户信息
    users = load_users()
    username = session.get('username')
    
    if username not in users:
        flash('用户不存在', 'error')
        return redirect(url_for('logout'))
    
    user_data = users[username]
    
    # 处理表单提交
    if request.method == 'POST':
        # 验证当前密码
        current_password = request.form.get('current_password')
        if current_password:
            if hash_password(current_password) != user_data['password']:
                flash('当前密码不正确', 'error')
                return redirect(url_for('profile'))
            
            # 更新用户名
            new_username = request.form.get('username')
            if new_username and new_username != username:
                # 检查用户名是否已存在
                if new_username in users and new_username != username:
                    flash('用户名已存在', 'error')
                    return redirect(url_for('profile'))
                
                # 更新用户名 - 同时更新卡片数据
                user_data_copy = user_data.copy()
                users.pop(username)
                users[new_username] = user_data_copy
                
                # 更新卡片所有权
                if username in user_card_states:
                    user_card_states[new_username] = user_card_states[username]
                    del user_card_states[username]
                    save_cards()
                
                session['username'] = new_username
            
            # 更新密码
            new_password = request.form.get('new_password')
            if new_password:
                users[new_username if new_username else username]['password'] = hash_password(new_password)
            
            # 更新学习模式
            study_mode = request.form.get('study_mode')
            if study_mode:
                users[new_username if new_username else username]['study_mode'] = study_mode
            
            # 处理头像上传
            if 'avatar' in request.files:
                avatar_file = request.files['avatar']
                if avatar_file.filename:
                    # 确保目录存在
                    avatar_dir = os.path.join(os.path.dirname(__file__), 'static', 'avatars')
                    os.makedirs(avatar_dir, exist_ok=True)
                    
                    try:
                        # 读取和处理图像
                        img_data = avatar_file.read()
                        img = Image.open(BytesIO(img_data))
                        
                        # 获取裁剪参数
                        crop_x = request.form.get('crop_x', type=float, default=0)
                        crop_y = request.form.get('crop_y', type=float, default=0)
                        crop_width = request.form.get('crop_width', type=float, default=img.width)
                        crop_height = request.form.get('crop_height', type=float, default=img.height)
                        
                        # 裁剪图像
                        if crop_width > 0 and crop_height > 0:
                            img = img.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
                        
                        # 调整大小为标准尺寸 (例如 200x200)
                        img = img.resize((200, 200), Image.Resampling.LANCZOS)
                        
                        # 保存头像文件
                        filename = f"{new_username if new_username else username}_{int(datetime.now().timestamp())}.jpg"
                        avatar_path = os.path.join(avatar_dir, filename)
                        img.save(avatar_path, "JPEG", quality=95)
                        
                        # 更新用户数据
                        users[new_username if new_username else username]['avatar'] = f"avatars/{filename}"
                    except Exception as e:
                        print(f"处理头像出错: {e}")
                        flash('头像处理失败，请尝试其他图片', 'error')
            
            # 保存用户数据
            save_users(users)
            flash('个人资料已更新', 'success')
            return redirect(url_for('profile'))
    
    # 获取学习统计数据
    stats = {
        'total_words': 0,
        'total_reviews': 0,
        'avg_retention': 0,
        'streak_days': 0
    }
    
    # 计算已学习单词总数
    cards = get_user_cards()
    if isinstance(cards, dict):
        viewed_cards = [card for card_id, card in cards.items() if hasattr(card, 'is_viewed') and card.is_viewed]
        stats['total_words'] = len(viewed_cards)
        
        # 计算总复习次数
        total_reviews = sum(len(card.review_logs) for card in viewed_cards if hasattr(card, 'review_logs'))
        stats['total_reviews'] = total_reviews
        
        # 计算平均记忆保留率
        if viewed_cards:
            retention_sum = sum(card.retention_rate for card in viewed_cards if hasattr(card, 'retention_rate'))
            stats['avg_retention'] = round(retention_sum / max(1, len(viewed_cards)) * 100)
        
        # 获取连续学习天数
        # 从review_data函数获取
        review_stats = {}
        for card_id, card in cards.items():
            if hasattr(card, 'review_logs') and card.review_logs:
                for log in card.review_logs:
                    timestamp = int(log.timestamp.timestamp())
                    date_key = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                    review_stats[date_key] = review_stats.get(date_key, 0) + 1
        
        # 计算连续天数
        if review_stats:
            dates = sorted(review_stats.keys())
            current_streak = 1
            for i in range(1, len(dates)):
                date1 = datetime.strptime(dates[i-1], '%Y-%m-%d')
                date2 = datetime.strptime(dates[i], '%Y-%m-%d')
                if (date2 - date1).days == 1:
                    current_streak += 1
                else:
                    current_streak = 1
            stats['streak_days'] = current_streak
    
    # 获取用户头像
    avatar_url = None
    if 'avatar' in user_data:
        avatar_url = url_for('static', filename=user_data['avatar'])
    
    # 获取用户学习模式
    user_mode = user_data.get('study_mode', 'medium')  # 默认为中等模式
    
    return render_template('profile.html', stats=stats, avatar_url=avatar_url, user_mode=user_mode)

# 初始化FSRS
fsrs = FSRS()

# 存储文件路径
# 尝试多个可能的位置
possible_paths = [
    os.path.join(os.path.dirname(__file__), 'data'),  # fsrs_web/data
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data'),  # 项目根目录/data
    os.path.dirname(__file__)  # fsrs_web目录
]

# 使用配置中的数据路径
storage_file = CARD_STATES_FILE

# 确保数据目录存在
os.makedirs(os.path.dirname(storage_file), exist_ok=True)
print(f"找到数据文件: {storage_file}")

print(f"使用数据文件路径: {storage_file}")

# 导入存储适配器
try:
    from models.storage import StorageAdapter
except ImportError:
    try:
        from fsrs_web.models.storage import StorageAdapter
    except ImportError:
        print("无法导入StorageAdapter，将使用默认文件存储")
        StorageAdapter = None

# 卡片数据结构改进
# 系统将维护两种卡片：
# 1. 系统基础卡片(system_cards): 所有用户共享的基础单词库
# 2. 用户卡片状态(user_card_states): 用户对卡片的学习状态，以及用户自己添加的卡片
system_cards = {}  # 格式: {card_id: Card}
user_card_states = {}  # 格式: {username: {card_id: CardState}}

@dataclass
class CardState:
    """卡片学习状态"""
    card_id: str  # 关联的卡片ID
    is_viewed: bool = False  # 是否已查看
    memory_state: Optional["MemoryState"] = None  # 记忆状态
    review_logs: List["ReviewLog"] = field(default_factory=list)  # 复习记录
    due_date: Optional[datetime] = None  # 下次复习时间
    learning_factor: float = 1.0  # 学习因子
    is_user_card: bool = False  # 是否是用户自己添加的卡片
    user_card_data: Optional[Dict] = None  # 如果是用户自己添加的卡片，存储卡片内容
    
    @property
    def retention_rate(self) -> float:
        """计算记忆保留率"""
        if not self.review_logs:
            return 0.0
        good_ratings = sum(1 for log in self.review_logs if log.rating >= 3)
        return good_ratings / len(self.review_logs)

# 添加用户FSRS参数
class UserFSRSParams:
    """用户独立的FSRS参数"""
    def __init__(self, params=None):
        self.params = params if params is not None else FSRS.DEFAULT_PARAMS
        self.last_updated = datetime.now()
        self.optimization_count = 0

# 在load_users函数后添加用户FSRS参数存储
user_fsrs_params = {}  # 格式: {username: UserFSRSParams}

# 在load_cards函数中添加加载用户FSRS参数的逻辑
def load_cards():
    """加载卡片数据"""
    global system_cards, user_card_states, user_fsrs_params
    
    # 如果可用，使用存储适配器
    if StorageAdapter is not None:
        system_cards, user_card_states, user_fsrs_params = StorageAdapter.load_cards(
            system_cards_class=Card, 
            card_state_class=CardState, 
            user_fsrs_params_class=UserFSRSParams
        )
        print(f"已加载 {len(system_cards)} 张系统卡片")
        print(f"已加载 {len(user_card_states)} 个用户的卡片状态")
        print(f"已加载 {len(user_fsrs_params)} 个用户的FSRS参数")
        
        # 打印每个用户的卡片数量
        for username, states in user_card_states.items():
            print(f"用户 {username} 有 {len(states)} 个卡片状态")
            
            # 统计每个单元的卡片数量
            unit_counts = defaultdict(int)
            for card_id, state in states.items():
                if state.is_user_card and state.user_card_data:
                    unit_counts[state.user_card_data.get('unit_id', 'unknown')] += 1
                elif card_id in system_cards:
                    unit_counts[system_cards[card_id].unit_id] += 1
            
            # 打印单元统计
            if unit_counts:
                print(f"用户 {username} 各单元卡片数量:")
                for unit_id, count in unit_counts.items():
                    print(f"  {unit_id}: {count} 张卡片")
    else:
        # 使用旧的文件存储方式
        if os.path.exists(storage_file):
            try:
                with open(storage_file, 'rb') as f:
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
                            print("已加载新格式数据")
                        # 检查是否是中间格式(用户分离的字典)
                        elif any(isinstance(v, dict) for v in all_data.values()):
                            print("检测到中间格式数据，正在转换为新格式...")
                            # 将所有卡片转换为系统卡片
                            system_cards = {}
                            user_card_states = {}
                            
                            for username, cards_dict in all_data.items():
                                # 为每个用户创建卡片状态字典
                                user_card_states[username] = {}
                                
                                for card_id, card in cards_dict.items():
                                    # 将卡片添加到系统卡片
                                    if card_id not in system_cards:
                                        # 创建一个不包含用户特定状态的卡片副本
                                        system_card = Card(
                                            id=card.id,
                                            unit_id=card.unit_id,
                                            front=card.front,
                                            back=card.back,
                                            created_at=card.created_at
                                        )
                                        system_cards[card_id] = system_card
                                    
                                    # 创建用户卡片状态
                                    card_state = CardState(
                                        card_id=card_id,
                                        is_viewed=card.is_viewed if hasattr(card, 'is_viewed') else False,
                                        memory_state=card.memory_state if hasattr(card, 'memory_state') else None,
                                        review_logs=card.review_logs if hasattr(card, 'review_logs') else [],
                                        due_date=card.due_date if hasattr(card, 'due_date') else card.created_at,
                                        learning_factor=card.learning_factor if hasattr(card, 'learning_factor') else 1.0
                                    )
                                    user_card_states[username][card_id] = card_state
                        else:
                            # 旧格式，转换为新格式
                            print("检测到旧格式卡片数据，正在转换为新格式...")
                            system_cards = all_data
                            
                            # 获取所有用户
                            users = load_users()
                            if users:
                                # 为每个用户创建卡片状态
                                for username in users:
                                    user_card_states[username] = {}
                                    for card_id, card in system_cards.items():
                                        # 创建默认卡片状态
                                        user_card_states[username][card_id] = CardState(
                                            card_id=card_id,
                                            is_viewed=False,
                                            due_date=card.created_at
                                        )
                            else:
                                # 如果没有用户，创建默认用户
                                user_card_states['default'] = {}
                                for card_id, card in system_cards.items():
                                    user_card_states['default'][card_id] = CardState(
                                        card_id=card_id,
                                        is_viewed=False,
                                        due_date=card.created_at
                                    )
                    
                print(f"已加载 {len(system_cards)} 张系统卡片")
                print(f"已加载 {len(user_card_states)} 个用户的卡片状态")
                print(f"已加载 {len(user_fsrs_params)} 个用户的FSRS参数")
                
                # 打印每个用户的卡片数量
                for username, states in user_card_states.items():
                    print(f"用户 {username} 有 {len(states)} 个卡片状态")
                    
                    # 统计每个单元的卡片数量
                    unit_counts = defaultdict(int)
                    for card_id, state in states.items():
                        if state.is_user_card and state.user_card_data:
                            unit_counts[state.user_card_data.get('unit_id', 'unknown')] += 1
                        elif card_id in system_cards:
                            unit_counts[system_cards[card_id].unit_id] += 1
                    
                    # 打印单元统计
                    if unit_counts:
                        print(f"用户 {username} 各单元卡片数量:")
                        for unit_id, count in unit_counts.items():
                            print(f"  {unit_id}: {count} 张卡片")
                
            except Exception as e:
                print(f"加载卡片数据失败: {e}")
                import traceback
                traceback.print_exc()
                system_cards = {}
                user_card_states = {}
                user_fsrs_params = {}
        else:
            system_cards = {}
            user_card_states = {}
            user_fsrs_params = {}

def save_cards():
    """保存卡片数据"""
    if StorageAdapter is not None:
        # 使用存储适配器保存数据
        StorageAdapter.save_cards(system_cards, user_card_states, user_fsrs_params)
    else:
        # 使用旧的文件存储方式
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(storage_file), exist_ok=True)
            
            # 将数据打包为新格式
            all_data = {
                'system_cards': system_cards,
                'user_card_states': user_card_states,
                'user_fsrs_params': user_fsrs_params
            }
            
            with open(storage_file, 'wb') as f:
                pickle.dump(all_data, f)
            print(f"已保存 {len(system_cards)} 张系统卡片和 {len(user_card_states)} 个用户的卡片状态")
        except Exception as e:
            print(f"保存卡片数据失败: {e}")

def get_user_cards():
    """获取当前用户可见的所有卡片"""
    username = session.get('username')
    if not username or username not in user_card_states:
        return {}
    
    result = {}
    user_states = user_card_states[username]
    
    # 添加系统卡片
    for card_id, card in system_cards.items():
        if card_id in user_states:
            state = user_states[card_id]
            # 创建卡片副本，并添加用户状态
            card_copy = Card(
                id=card.id,
                unit_id=card.unit_id,
                front=card.front,
                back=card.back,
                created_at=card.created_at,
                due_date=state.due_date if state.due_date else card.created_at
            )
            # 手动设置其他属性
            card_copy.memory_state = state.memory_state
            card_copy.review_logs = state.review_logs
            card_copy.is_viewed = state.is_viewed
            card_copy.learning_factor = state.learning_factor
            result[card_id] = card_copy
    
    # 添加用户自己的卡片
    for card_id, state in user_states.items():
        if state.is_user_card and state.user_card_data:
            # 创建用户卡片
            created_at = state.user_card_data.get('created_at', datetime.now())
            user_card = Card(
                id=card_id,
                unit_id=state.user_card_data.get('unit_id', ''),
                front=state.user_card_data.get('front', ''),
                back=state.user_card_data.get('back', ''),
                created_at=created_at,
                due_date=state.due_date if state.due_date else created_at
            )
            # 手动设置其他属性
            user_card.memory_state = state.memory_state
            user_card.review_logs = state.review_logs
            user_card.is_viewed = state.is_viewed
            user_card.learning_factor = state.learning_factor
            result[card_id] = user_card
    
    return result

def get_card(card_id):
    """获取卡片"""
    cards = get_user_cards()
    return cards.get(card_id)

def update_card(card):
    """更新卡片"""
    username = session.get('username')
    if not username:
        return None
    
    # 确保用户有卡片状态字典
    if username not in user_card_states:
        user_card_states[username] = {}
    
    # 检查是否是系统卡片
    if card.id in system_cards:
        # 更新用户对系统卡片的状态
        if card.id not in user_card_states[username]:
            user_card_states[username][card.id] = CardState(card_id=card.id)
        
        state = user_card_states[username][card.id]
        state.is_viewed = card.is_viewed
        state.memory_state = card.memory_state
        state.review_logs = card.review_logs
        state.due_date = card.due_date
        state.learning_factor = card.learning_factor
    else:
        # 如果不是系统卡片，检查是否是用户卡片
        if card.id in user_card_states[username] and user_card_states[username][card.id].is_user_card:
            # 更新用户卡片状态
            state = user_card_states[username][card.id]
            state.is_viewed = card.is_viewed
            state.memory_state = card.memory_state
            state.review_logs = card.review_logs
            state.due_date = card.due_date
            state.learning_factor = card.learning_factor
            
            # 更新用户卡片数据
            if state.user_card_data:
                state.user_card_data['front'] = card.front
                state.user_card_data['back'] = card.back
        else:
            # 新的用户卡片
            user_card_states[username][card.id] = CardState(
                card_id=card.id,
                is_viewed=card.is_viewed,
                memory_state=card.memory_state,
                review_logs=card.review_logs,
                due_date=card.due_date,
                learning_factor=card.learning_factor,
                is_user_card=True,
                user_card_data={
                    'unit_id': card.unit_id,
                    'front': card.front,
                    'back': card.back,
                    'created_at': card.created_at
                }
            )
    
    save_cards()
    return card

def get_due_cards(current_time=None):
    """获取需要复习的卡片"""
    cards = get_user_cards()
    actual_time = current_time if current_time is not None else datetime.now()
    # 只返回已查看且到期的卡片
    return [card for card in cards.values() if hasattr(card, 'is_viewed') and card.is_viewed and card.due_date <= actual_time]

def get_cards_by_unit(unit_id):
    """获取指定单元的卡片"""
    cards = get_user_cards()
    return [card for card in cards.values() if card.unit_id == unit_id]

def get_learned_words_count():
    """获取已学习的单词数量"""
    cards = get_user_cards()
    return sum(1 for card in cards.values() if hasattr(card, 'review_logs') and len(card.review_logs) > 0)

# 加载卡片数据
load_cards()

# 修改主页路由，添加登录要求
@app.route('/')
@login_required
def index():
    """首页 - 选择学习或复习"""
    # 获取需要复习的卡片数量
    due_cards = get_due_cards()
    
    # 获取今日任务统计
    total_tasks, completed_tasks = get_daily_tasks_stats()
    
    # 计算已学习单词数量
    learned_words_count = get_learned_words_count()
    # FSRS参数调整所需的基础单词数量
    fsrs_adjustment_threshold = 50
    
    return render_template('index.html', 
                          due_cards_count=len(due_cards),
                          total_tasks=total_tasks,
                          completed_tasks=completed_tasks,
                          learned_words_count=learned_words_count,
                          fsrs_adjustment_threshold=fsrs_adjustment_threshold)

@app.route('/learn')
@login_required
def learn():
    """学习新内容页面 - 显示单元列表"""
    return render_template('learn.html')

@app.route('/review')
@login_required
def review():
    """复习内容页面"""
    # 获取需要复习的卡片
    due_cards = get_due_cards()
    
    # 初始化session中的复习状态
    if 'cards_reviewed' not in session:
        session['cards_reviewed'] = 0
    
    # 计算已学习单词数量
    learned_words_count = get_learned_words_count()
    # FSRS参数调整所需的基础单词数量
    fsrs_adjustment_threshold = 50
    
    if not due_cards:
        return render_template('review.html', 
                              cards_reviewed=session['cards_reviewed'],
                              total_cards=session['cards_reviewed'],
                              learned_words_count=learned_words_count,
                              fsrs_adjustment_threshold=fsrs_adjustment_threshold,
                              card=None)
    
    # 取第一张卡片显示
    card = due_cards[0]
    
    # 计算过期天数
    now = datetime.now()
    overdue_days = (now - card.due_date).days if now > card.due_date else 0
    
    # 如果卡片过期，调整稳定性
    if overdue_days > 0:
        # 根据过期天数调整稳定性，过期越久稳定性下降越多
        # 这里采用Anki类似的处理方式，但使用更平滑的衰减
        user_fsrs = get_user_fsrs()  # 获取用户特定的FSRS实例
        adjusted_stability = card.memory_state.stability if card.memory_state else user_fsrs.INIT_STABILITY
        if overdue_days > 0:
            decay_factor = 1.0 / (1.0 + 0.1 * overdue_days)  # 平滑衰减函数
            adjusted_stability *= decay_factor
            adjusted_stability = max(user_fsrs.INIT_STABILITY * 0.5, adjusted_stability)  # 确保不会低于初始稳定性的一半
    else:
        user_fsrs = get_user_fsrs()  # 获取用户特定的FSRS实例
        adjusted_stability = card.memory_state.stability if card.memory_state else user_fsrs.INIT_STABILITY
    
    # 使用调整后的稳定性计算间隔
    user_fsrs = get_user_fsrs()  # 获取用户特定的FSRS实例
    hard_interval = user_fsrs.next_interval(adjusted_stability * 0.8 if adjusted_stability else user_fsrs.INIT_STABILITY * 0.8)
    good_interval = user_fsrs.next_interval(adjusted_stability * 1.0 if adjusted_stability else user_fsrs.INIT_STABILITY * 1.0)
    easy_interval = user_fsrs.next_interval(adjusted_stability * 1.3 if adjusted_stability else user_fsrs.INIT_STABILITY * 1.3)
    
    return render_template('review.html', 
                          card=card,
                          hard_interval=hard_interval,
                          good_interval=good_interval,
                          easy_interval=easy_interval,
                          overdue_days=overdue_days,
                          learned_words_count=learned_words_count,
                          fsrs_adjustment_threshold=fsrs_adjustment_threshold,
                          cards_reviewed=session['cards_reviewed'],
                          total_cards=session['cards_reviewed'] + len(due_cards))

@app.route('/api/search')
@login_required
def search():
    """搜索API"""
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify([])
    
    # 搜索结果
    results = []
    
    # 在卡片中搜索
    for card_id, card in get_user_cards().items():
        front_lower = card.front.lower()
        if query in front_lower:
            # 添加单元信息
            unit_name = "未知单元"
            if hasattr(card, 'unit_id'):
                unit_id = card.unit_id
                if unit_id == 'unit1':
                    unit_name = 'Number'
                elif unit_id == 'unit2':
                    unit_name = 'Algebra'
                # 可以继续添加其他单元的映射
            
            results.append({
                'id': card_id,
                'front': card.front,
                'back': card.back,
                'unit': unit_name,
                'unit_id': card.unit_id if hasattr(card, 'unit_id') else None
            })
    
    # 按照匹配度排序（完全匹配的排在前面）
    results.sort(key=lambda x: 0 if x['front'].lower() == query else 1)
    
    return jsonify(results[:10])  # 限制返回前10个结果

@app.route('/unit/<unit_id>')
@login_required
def unit(unit_id):
    """单元学习页面"""
    unit_cards = get_cards_by_unit(unit_id)
    print(f"单元 {unit_id} 的卡片数量: {len(unit_cards)}")
    
    # 打印前3张卡片的信息
    for i, card in enumerate(unit_cards[:3]):
        print(f"单元 {unit_id} 的卡片 {i+1}:")
        print(f"  ID: {card.id}")
        print(f"  正面内容: {card.front[:50]}...")
    
    # 获取单元名称
    unit_names = {
        'unit1': 'Number',
        'unit2': 'Algebra',
        'unit3': 'Geometry',
        'unit4': 'Unit 4',
        'unit5': 'Unit 5',
        'unit6': 'Unit 6',
        'unit7': 'Unit 7',
        'unit8': 'Unit 8',
        'unit9': 'Unit 9'
    }
    unit_name = unit_names.get(unit_id, "Unit")
    
    # 计算已学习单词数量
    learned_words_count = get_learned_words_count()
    # FSRS参数调整所需的基础单词数量
    fsrs_adjustment_threshold = 50
    
    return render_template('unit.html', 
                          unit_id=unit_id,
                          unit_name=unit_name,
                          cards=unit_cards,
                          learned_words_count=learned_words_count,
                          fsrs_adjustment_threshold=fsrs_adjustment_threshold)

@app.route('/word_stats')
@login_required
def word_stats():
    """单词状态页面 - 显示单元列表"""
    # 单元名称映射
    unit_names = {
        'unit1': 'Number',
        'unit2': 'Algebra',
        'unit3': 'Geometry',
        'unit4': 'Unit 4',
        'unit5': 'Unit 5',
        'unit6': 'Unit 6',
        'unit7': 'Unit 7',
        'unit8': 'Unit 8',
        'unit9': 'Unit 9'
    }
    
    # 获取每个单元的统计信息
    unit_stats = {}
    for unit_id in unit_names.keys():
        unit_cards = get_cards_by_unit(unit_id)
        viewed_cards = [card for card in unit_cards if hasattr(card, 'is_viewed') and card.is_viewed]
        unit_stats[unit_id] = {
            'total': len(unit_cards),
            'viewed': len(viewed_cards)
        }
    
    return render_template('word_stats.html', units=unit_names, unit_stats=unit_stats)

@app.route('/unit_stats/<unit_id>')
@login_required
def unit_stats(unit_id):
    """特定单元的单词状态页面"""
    # 单元名称映射
    unit_names = {
        'unit1': 'Number',
        'unit2': 'Algebra',
        'unit3': 'Geometry',
        'unit4': 'Unit 4',
        'unit5': 'Unit 5',
        'unit6': 'Unit 6',
        'unit7': 'Unit 7',
        'unit8': 'Unit 8',
        'unit9': 'Unit 9'
    }
    
    # 检查单元是否存在
    if unit_id not in unit_names:
        return redirect(url_for('word_stats'))
    
    # 获取该单元的已查看卡片
    unit_cards = get_cards_by_unit(unit_id)
    viewed_cards = [card for card in unit_cards if hasattr(card, 'is_viewed') and card.is_viewed]
    
    unit_name = unit_names[unit_id]
    return render_template('unit_stats.html', 
                          unit_id=unit_id, 
                          unit_name=unit_name,
                          viewed_cards=viewed_cards)

@app.route('/daily_plan')
@login_required
def daily_plan():
    """今日计划页面"""
    # 获取今日任务
    tasks = get_daily_tasks()
    
    # 计算统计数据
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task['completed'])
    
    # 获取已复习卡片数量
    cards_reviewed = session.get('cards_reviewed', 0)
    
    # 获取学习进度
    learned_words = session.get('learned_words', {})
    
    return render_template('daily_plan.html',
                          tasks=tasks,
                          total_tasks=total_tasks,
                          completed_tasks=completed_tasks,
                          cards_reviewed=cards_reviewed,
                          learned_words=learned_words)

def get_daily_tasks_stats():
    """获取今日任务统计"""
    tasks = get_daily_tasks()
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task['completed'])
    return total_tasks, completed_tasks

def get_daily_tasks():
    """获取今日任务列表"""
    tasks = []
    
    # 单元名称映射
    unit_names = {
        'unit1': 'Number',
        'unit2': 'Algebra',
        'unit3': 'Geometry',
        'unit4': 'Unit 4',
        'unit5': 'Unit 5',
        'unit6': 'Unit 6',
        'unit7': 'Unit 7',
        'unit8': 'Unit 8',
        'unit9': 'Unit 9'
    }
    
    # 获取今日需要复习的卡片
    due_cards = get_due_cards()
    
    # 如果有需要复习的卡片，添加复习任务
    if due_cards:
        # 获取已复习的卡片数量
        reviewed_today = session.get('cards_reviewed', 0)
        
        # 计算总卡片数
        total_cards = len(due_cards)
        
        # 创建复习任务
        review_task = {
            'type': 'review',
            'icon': '🔄',
            'title': '复习单词',
            'description': f'今日需要复习 {total_cards} 个单词',
            'completed': reviewed_today >= total_cards,
            'progress': total_cards,  # 用于前端显示 x/y
            'action_url': url_for('review'),
            'action_text': '开始复习'
        }
        
        tasks.append(review_task)
    
    # 添加学习新单词任务
    # 获取所有未查看的卡片
    unviewed_cards = []
    cards = get_user_cards()
    if isinstance(cards, dict):
        for card_id, card in cards.items():
            if not hasattr(card, 'is_viewed') or not card.is_viewed:
                unviewed_cards.append(card)
    else:
        print(f"Warning: cards is not a dictionary, it's a {type(cards)}")
        unviewed_cards = []
    
    if unviewed_cards:
        # 按单元分组
        unit_cards = defaultdict(list)
        for card in unviewed_cards:
            unit_cards[card.unit_id].append(card)
        
        # 只选择前3个单元作为今日任务
        top_units = sorted(unit_cards.items(), key=lambda x: len(x[1]), reverse=True)[:3]
        
        for unit_id, unit_cards_list in top_units:
            # 获取已学习的卡片数量
            learned_count = 0
            if 'learned_words' in session and unit_id in session['learned_words']:
                learned_count = session['learned_words'][unit_id]
            
            unit_name = unit_names.get(unit_id, f'单元 {unit_id}')
            # 每天学习固定30个新单词
            daily_learn_count = 30
            
            tasks.append({
                'type': 'learn',
                'icon': '📚',
                'title': f'学习 {unit_name}',
                'description': f'学习 {daily_learn_count} 个新单词',
                'completed': learned_count >= daily_learn_count,
                'action_url': url_for('unit', unit_id=unit_id),
                'action_text': '开始学习',
                'total_words': daily_learn_count,
                'learned_words': min(learned_count, daily_learn_count)
            })
    
    return tasks

@app.route('/mark_as_viewed/<card_id>', methods=['POST'])
@login_required
def mark_as_viewed(card_id):
    """标记卡片为已查看"""
    card = get_card(card_id)
    
    if not card:
        return jsonify({'status': 'error', 'message': '卡片不存在'})
    
    # 检查是否是首次查看
    first_view = not hasattr(card, 'is_viewed') or not card.is_viewed
    
    # 标记为已查看
    card.is_viewed = True
    
    # 如果是首次查看，将到期日期设置为当前时间，使其进入复习队列
    if first_view:
        card.due_date = datetime.now()
        print(f"卡片 {card_id} 首次查看，已设置为当前时间，加入复习队列")
    
    # 更新卡片
    update_card(card)
    
    # 更新session中的学习进度
    if 'learned_words' not in session:
        session['learned_words'] = {}
    
    if card.unit_id not in session['learned_words']:
        session['learned_words'][card.unit_id] = 0
    
    # 只有首次查看时才增加计数
    if first_view:
        session['learned_words'][card.unit_id] += 1
        session.modified = True
    
    return jsonify({'status': 'success'})

# 获取用户的FSRS实例
def get_user_fsrs():
    """获取当前用户的FSRS实例"""
    username = session.get('username')
    if not username:
        return fsrs  # 返回默认FSRS实例
    
    # 获取用户学习模式
    users = load_users()
    user_data = users.get(username, {})
    study_mode = user_data.get('study_mode', 'medium')  # 默认为中等模式
    
    # 根据学习模式设置参数
    if study_mode == 'long_term':
        desired_retention = 0.95
        maximum_interval = 36500
    elif study_mode == 'cram':
        desired_retention = 0.80
        maximum_interval = 30
    else:  # medium
        desired_retention = 0.90
        maximum_interval = 365
    
    # 如果用户没有自己的FSRS参数，创建一个
    if username not in user_fsrs_params:
        user_fsrs_params[username] = UserFSRSParams()
    
    # 返回用户特定的FSRS实例，使用学习模式对应的参数
    return FSRS(
        desired_retention=desired_retention,
        maximum_interval=maximum_interval,
        params=user_fsrs_params[username].params
    )

# 修改rate_card函数，使用用户特定的FSRS实例
@app.route('/rate_card', methods=['POST'])
@login_required
def rate_card():
    """评分卡片"""
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '无效的请求数据'})
    
    card_id = data.get('card_id')
    rating = data.get('rating')
    if not card_id:
        return jsonify({'status': 'error', 'message': '未提供卡片ID'})
    
    if not isinstance(rating, int) or rating < 1 or rating > 4:
        return jsonify({'status': 'error', 'message': '无效的评分'})
    
    card = get_card(card_id)
    if not card:
        return jsonify({'status': 'error', 'message': '卡片不存在'})
    
    # 确保卡片有必要的属性
    if not hasattr(card, 'tags'):
        card.tags = []
    
    if not hasattr(card, 'learning_factor'):
        card.learning_factor = 1.0
    
    try:
        # 获取当前时间
        now = datetime.now()
        
        # 创建复习记录
        if not hasattr(card, 'review_logs'):
            card.review_logs = []
        
        # 根据评分更新记忆状态
        if not hasattr(card, 'memory_state'):
            card.memory_state = None
        
        # 计算过期天数
        overdue_days = (now - card.due_date).days if now > card.due_date else 0
        
        # 获取用户特定的FSRS实例
        user_fsrs = get_user_fsrs()
        
        # 如果卡片过期，调整稳定性
        if overdue_days > 0 and card.memory_state:
            # 根据过期天数调整稳定性，过期越久稳定性下降越多
            decay_factor = 1.0 / (1.0 + 0.1 * overdue_days)  # 平滑衰减函数
            card.memory_state.stability *= decay_factor
            card.memory_state.stability = max(user_fsrs.INIT_STABILITY * 0.5, card.memory_state.stability)  # 确保不会低于初始稳定性的一半
        
        # 更新记忆状态
        updated_card = user_fsrs.review_card(card, rating)
        card.memory_state = updated_card.memory_state
        
        # 计算下次复习时间
        interval_days = user_fsrs.next_interval(card.memory_state.stability)
        card.due_date = now + timedelta(days=interval_days)
        
        # 添加复习记录，直接使用顶层导入的 FsrsReviewLog
        review_log = FsrsReviewLog(
            timestamp=now,
            rating=rating,
            elapsed_days=overdue_days,
            scheduled_days=interval_days,
        )
        card.review_logs.append(review_log)
        
        # 更新卡片
        update_card(card)
        
        # 更新会话中的复习计数
        if 'cards_reviewed' not in session:
            session['cards_reviewed'] = 0
        session['cards_reviewed'] += 1
        session.modified = True
        
        return jsonify({
            'status': 'success',
            'next_due': card.due_date.strftime('%Y-%m-%d'),
            'interval_days': interval_days,
            'stability': card.memory_state.stability,
            'difficulty': card.memory_state.difficulty,
            'overdue_days': overdue_days
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'处理评分时出错: {str(e)}'})

@app.route('/reset_session', methods=['POST'])
@login_required
def reset_session():
    """重置今日学习进度相关的会话数据和今天的复习记录"""
    # 获取今天的日期（0点0分0秒）
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 清除会话中的学习进度
    if 'learned_words' in session:
        del session['learned_words']
    if 'cards_reviewed' in session:
        del session['cards_reviewed']
    
    # 移除今天添加的所有复习记录，并将今天标记为已学习的单词重置为未学习
    cards_modified = False
    username = session.get('username')
    if username and username in user_card_states:
        for card_id, state in list(user_card_states[username].items()): # 使用list()避免在迭代时修改字典
            # 处理复习记录
            if hasattr(state, 'review_logs') and state.review_logs:
                # 过滤出今天之前的复习记录
                new_logs = [log for log in state.review_logs if log.timestamp < today]
                if len(new_logs) != len(state.review_logs):
                    state.review_logs = new_logs
                    cards_modified = True
    
    # 如果有修改，保存卡片数据
    if cards_modified:
        save_cards()
    
    # 重定向回首页
    return redirect(url_for('index'))

@app.route('/api/review_data')
@login_required
def review_data():
    """获取复习数据，用于热图显示"""
    # 获取查询参数
    start_date_str = request.args.get('start', '')
    end_date_str = request.args.get('end', '')
    
    # 默认显示过去一年的数据
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # 如果提供了日期参数，则使用提供的日期
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        except:
            pass
    
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except:
            pass
    
    # 初始化结果数据
    result = {
        'title': '复习热图',
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d'),
        'data': {}
    }
    
    # 遍历所有卡片，收集复习记录
    cards = get_user_cards()
    if isinstance(cards, dict):
        for card_id, card in cards.items():
            if hasattr(card, 'review_logs') and card.review_logs:
                for log in card.review_logs:
                    log_date = log.timestamp.strftime('%Y-%m-%d')
                    if log_date in result['data']:
                        result['data'][log_date] += 1
                    else:
                        result['data'][log_date] = 1
    
    # 计算统计数据
    total_reviews = sum(result['data'].values())
    avg_reviews = round(total_reviews / max(1, len(result['data'])), 1)
    
    # 添加统计数据
    result['stats'] = {
        'totalReviews': total_reviews,
        'averageDailyReviews': avg_reviews
    }
    
    # 计算连续学习天数
    if result['data']:
        dates = sorted(result['data'].keys())
        current_streak = 1
        max_streak = 1
        
        # 计算当前连续天数
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        if today in dates:
            # 今天已经学习
            current_date = datetime.strptime(today, '%Y-%m-%d')
            streak_count = 1
            
            while True:
                prev_date = (current_date - timedelta(days=streak_count)).strftime('%Y-%m-%d')
                if prev_date in dates:
                    current_streak += 1
                    streak_count += 1
                else:
                    break
        elif yesterday in dates:
            # 昨天学习了，但今天还没有
            current_date = datetime.strptime(yesterday, '%Y-%m-%d')
            streak_count = 1
            
            while True:
                prev_date = (current_date - timedelta(days=streak_count)).strftime('%Y-%m-%d')
                if prev_date in dates:
                    current_streak += 1
                    streak_count += 1
                else:
                    break
        else:
            # 既没有今天也没有昨天的记录
            current_streak = 0
        
        # 计算最长连续天数
        for i in range(1, len(dates)):
            date1 = datetime.strptime(dates[i-1], '%Y-%m-%d')
            date2 = datetime.strptime(dates[i], '%Y-%m-%d')
            
            if (date2 - date1).days == 1:
                max_streak += 1
            else:
                max_streak = 1
        
        result['stats']['currentStreak'] = current_streak
        result['stats']['maxStreak'] = max_streak
    else:
        result['stats']['currentStreak'] = 0
        result['stats']['maxStreak'] = 0
    
    return jsonify(result)

# 修改fsrs_analytics路由，支持用户特定的FSRS参数
@app.route('/fsrs_analytics')
@login_required
def fsrs_analytics():
    """FSRS分析页面"""
    # 获取所有卡片
    all_cards = list(get_user_cards().values())
    
    # 计算已学习单词数量
    learned_words_count = sum(1 for card in all_cards if hasattr(card, 'review_logs') and len(card.review_logs) > 0)
    
    # FSRS参数调整所需的基础单词数量
    fsrs_adjustment_threshold = 50
    
    # 计算记忆保留率
    retention_rates = []
    for card in all_cards:
        if hasattr(card, 'review_logs') and len(card.review_logs) > 1:
            good_ratings = sum(1 for log in card.review_logs if log.rating >= 3)
            retention_rate = good_ratings / len(card.review_logs)
            retention_rates.append(retention_rate)
    
    avg_retention = round(sum(retention_rates) / max(1, len(retention_rates)) * 100) if retention_rates else 0
    
    # 统计每天的复习次数
    daily_reviews = {}
    cards = get_user_cards()
    for card_id, card in cards.items():
        if hasattr(card, 'review_logs'):
            for log in card.review_logs:
                log_date = log.timestamp.strftime('%Y-%m-%d')
                daily_reviews[log_date] = daily_reviews.get(log_date, 0) + 1
    
    # 计算平均每日复习量
    avg_daily_reviews = round(sum(daily_reviews.values()) / max(1, len(daily_reviews))) if daily_reviews else 0
    
    # 计算稳定性分布
    stability_distribution = {
        '0-1': 0,
        '1-7': 0,
        '7-30': 0,
        '30-90': 0,
        '90-180': 0,
        '180+': 0
    }
    
    for card in all_cards:
        if hasattr(card, 'memory_state') and card.memory_state:
            stability = card.memory_state.stability
            if stability < 1:
                stability_distribution['0-1'] += 1
            elif stability < 7:
                stability_distribution['1-7'] += 1
            elif stability < 30:
                stability_distribution['7-30'] += 1
            elif stability < 90:
                stability_distribution['30-90'] += 1
            elif stability < 180:
                stability_distribution['90-180'] += 1
            else:
                stability_distribution['180+'] += 1
    
    # 获取最近复习的卡片
    recent_cards = []
    for card_id, card in cards.items():
        if hasattr(card, 'review_logs') and card.review_logs and hasattr(card, 'due_date'):
            # 获取最后一次复习时间
            last_review = max(log.timestamp for log in card.review_logs)
            recent_cards.append({
                'id': card_id,
                'front': card.front,
                'last_review': last_review,
                'due_date': card.due_date,
                'stability': card.memory_state.stability if hasattr(card, 'memory_state') and card.memory_state else 0
            })
    
    # 按最近复习时间排序
    recent_cards.sort(key=lambda x: x['last_review'], reverse=True)
    recent_cards = recent_cards[:10]  # 只取前10个
    
    # 计算复习间隔分布
    interval_distribution = {
        '0-1': 0,
        '1-7': 0,
        '7-30': 0,
        '30-90': 0,
        '90-180': 0,
        '180+': 0
    }
    
    for card in all_cards:
        if hasattr(card, 'review_logs') and len(card.review_logs) > 1:
            # 计算最近两次复习的间隔
            sorted_logs = sorted(card.review_logs, key=lambda x: x.timestamp)
            for i in range(1, len(sorted_logs)):
                interval = (sorted_logs[i].timestamp - sorted_logs[i-1].timestamp).days
                if interval < 1:
                    interval_distribution['0-1'] += 1
                elif interval < 7:
                    interval_distribution['1-7'] += 1
                elif interval < 30:
                    interval_distribution['7-30'] += 1
                elif interval < 90:
                    interval_distribution['30-90'] += 1
                elif interval < 180:
                    interval_distribution['90-180'] += 1
                else:
                    interval_distribution['180+'] += 1
    
    # 获取用户FSRS参数
    username = session.get('username')
    user_params = None
    if username and username in user_fsrs_params:
        user_params = user_fsrs_params[username].params
    else:
        user_params = FSRS.DEFAULT_PARAMS
    
    # 准备FSRS参数数据
    params_data = [
        {"description": "记忆稳定性权重", "value": user_params[0], "default": FSRS.DEFAULT_PARAMS[0]},
        {"description": "难度权重", "value": user_params[1], "default": FSRS.DEFAULT_PARAMS[1]},
        {"description": "记忆强化系数", "value": user_params[2], "default": FSRS.DEFAULT_PARAMS[2]},
        {"description": "遗忘惩罚系数", "value": user_params[3], "default": FSRS.DEFAULT_PARAMS[3]},
        {"description": "复习间隔系数", "value": user_params[4], "default": FSRS.DEFAULT_PARAMS[4]},
        {"description": "记忆衰减率", "value": user_params[5], "default": FSRS.DEFAULT_PARAMS[5]}
    ]
    
    # 准备记忆曲线数据
    retention_days = list(range(0, 365, 30))  # 0, 30, 60, ..., 330
    retention_rates_curve = []
    
    # 使用用户的FSRS实例计算记忆曲线
    user_fsrs = get_user_fsrs()
    avg_stability = 30  # 假设平均稳定性为30天
    for day in retention_days:
        retention_rates_curve.append(user_fsrs._forgetting_curve(avg_stability, day))
    
    # 准备工作量预测数据
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    workload_days = [(today + timedelta(days=i)).strftime('%m-%d') for i in range(30)]
    workload_counts = [0] * 30
    
    for card in all_cards:
        if hasattr(card, 'due_date'):
            due_day = (card.due_date - today).days
            if 0 <= due_day < 30:
                workload_counts[due_day] += 1
    
    # 准备复习历史数据
    review_dates = sorted(daily_reviews.keys())[-30:] if daily_reviews else []  # 最近30天
    review_counts = [daily_reviews.get(date, 0) for date in review_dates]
    
    # 计算总统计数据
    stats = {
        'total': len(all_cards),
        'learned': learned_words_count,
        'due': len(get_due_cards()),
        'avg_stability': sum(card.memory_state.stability for card in all_cards if hasattr(card, 'memory_state') and card.memory_state) / max(1, sum(1 for card in all_cards if hasattr(card, 'memory_state') and card.memory_state))
    }
    
    # 准备复习历史数据
    review_history = {
        'dates': review_dates,
        'counts': review_counts
    }
    
    # 准备工作量预测数据
    workload = {
        'dates': workload_days,
        'counts': workload_counts
    }
    
    try:
        return render_template('fsrs_analytics.html',
                          learned_words_count=learned_words_count,
                          fsrs_adjustment_threshold=fsrs_adjustment_threshold,
                          avg_retention=avg_retention,
                          avg_daily_reviews=avg_daily_reviews,
                          stability_distribution=stability_distribution,
                          interval_distribution=interval_distribution,
                          recent_cards=recent_cards,
                          daily_reviews=daily_reviews,
                          params=params_data,
                          retention_days=retention_days,
                          retention_rates=retention_rates_curve,
                          stats=stats,
                          review_history=review_history,
                          workload=workload)
    except Exception as e:
        print(f"渲染模板出错: {e}")
        import traceback
        traceback.print_exc()
        return f"渲染模板出错: {str(e)}"

@app.route('/word_search')
@login_required
def word_search():
    """单词搜索页面"""
    query = request.args.get('q', '').strip()
    
    # 搜索卡片
    search_results = []
    cards = get_user_cards()
    for card_id, card in cards.items():
        # 提取卡片中的实际单词和含义
        front_text = card.front.lower()
        back_text = card.back.lower()
        
        # 如果查询字符串在前面或后面的文本中，添加到结果
        if query.lower() in front_text or query.lower() in back_text:
            # 提取单词名称 - 尝试从HTML中提取，如果失败则使用前50个字符
            word_name = front_text[:50]
            if '<h3 class="word">' in front_text:
                try:
                    word_name = front_text.split('<h3 class="word">')[1].split('</h3>')[0].strip()
                except:
                    pass
            
            search_results.append({
                'id': card_id,
                'word': word_name,
                'front': card.front,
                'back': card.back,
                'unit_id': card.unit_id,
                'is_viewed': card.is_viewed if hasattr(card, 'is_viewed') else False,
                'due_date': card.due_date.strftime('%Y-%m-%d') if hasattr(card, 'due_date') else '',
                'review_count': len(card.review_logs) if hasattr(card, 'review_logs') else 0
            })
    
    # 单元名称映射
    unit_names = {
        'unit1': 'Number',
        'unit2': 'Algebra',
        'unit3': 'Geometry',
        'unit4': 'Unit 4',
        'unit5': 'Unit 5',
        'unit6': 'Unit 6',
        'unit7': 'Unit 7',
        'unit8': 'Unit 8',
        'unit9': 'Unit 9'
    }
    
    # 按单元分组结果
    grouped_results = {}
    for result in search_results:
        unit_id = result['unit_id']
        unit_name = unit_names.get(unit_id, f'单元 {unit_id}')
        
        if unit_name not in grouped_results:
            grouped_results[unit_name] = []
        
        grouped_results[unit_name].append(result)
    
    return render_template('word_search.html', 
                          query=query,
                          grouped_results=grouped_results,
                          total_results=len(search_results))

@app.route('/api/word_suggestions')
@login_required
def word_suggestions():
    """获取单词建议的API"""
    query = request.args.get('q', '').strip().lower()
    
    if not query or len(query) < 1:
        return jsonify([])
    
    # 从所有卡片中提取单词
    suggestions = set()
    cards = get_user_cards()
    for card_id, card in cards.items():
        # 提取单词
        word = ""
        if '<h3 class="word">' in card.front:
            try:
                word = card.front.split('<h3 class="word">')[1].split('</h3>')[0].strip()
            except:
                word = card.front[:50]
        else:
            # 如果没有HTML标记，使用前50个字符
            word = card.front[:50]
        
        # 如果单词包含查询字符串，添加到建议中
        if query in word.lower():
            suggestions.add(word)
    
    # 限制返回的建议数量
    suggestions_list = list(suggestions)
    suggestions_list.sort()
    return jsonify(suggestions_list[:10])

@app.route('/add_word/<unit_id>', methods=['GET', 'POST'])
@login_required
def add_word(unit_id):
    """添加新单词"""
    if request.method == 'POST':
        front = request.form.get('front', '').strip()
        back = request.form.get('back', '').strip()
        tags = request.form.get('tags', '').strip()
        
        if not front or not back:
            flash('单词和含义不能为空', 'error')
            return redirect(url_for('add_word', unit_id=unit_id))
        
        # 生成新的卡片ID
        card_id = f"{unit_id}_{str(uuid.uuid4())[:8]}"
        now = datetime.now()
        
        # 创建新卡片
        new_card = Card(
            id=card_id,
            unit_id=unit_id,
            front=front,
            back=back,
            created_at=now,
            due_date=now,
            tags=tags.split(',') if tags else []
        )
        
        # 保存为用户自己的卡片
        username = session.get('username')
        if username:
            if username not in user_card_states:
                user_card_states[username] = {}
            
            # 创建用户卡片状态
            user_card_states[username][card_id] = CardState(
                card_id=card_id,
                is_viewed=True,  # 新添加的卡片默认为已查看
                due_date=now,
                is_user_card=True,
                user_card_data={
                    'unit_id': unit_id,
                    'front': front,
                    'back': back,
                    'created_at': now
                }
            )
            
            save_cards()
        
        flash('单词添加成功', 'success')
        return redirect(url_for('unit', unit_id=unit_id))
    
    return render_template('add_word.html', unit_id=unit_id)

@app.route('/edit_word/<card_id>', methods=['GET', 'POST'])
@login_required  
def edit_word(card_id):
    """编辑现有单词"""
    card = get_card(card_id)
    if not card:
        if request.method == 'GET':
            flash('卡片不存在', 'error')
            return redirect(url_for('learn'))
        return jsonify({'status': 'error', 'message': '卡片不存在'})
    
    if request.method == 'GET':
        # 从卡片内容中提取现有信息
        word = ''
        pos = ''
        chinese = ''
        english = ''
        
        # 从正面提取单词和词性
        if '<h3 class="word">' in card.front:
            try:
                word = card.front.split('<h3 class="word">')[1].split('</h3>')[0].strip()
            except:
                pass
        
        if '<div class="part-of-speech">' in card.front:
            try:
                pos = card.front.split('<div class="part-of-speech">')[1].split('</div>')[0].strip()
            except:
                pass
        
        # 从背面提取中文和英文定义
        if '<div class="definition chinese">' in card.back:
            try:
                chinese = card.back.split('<div class="definition chinese">')[1].split('</div>')[0].strip()
            except:
                pass
        
        if '<div class="definition english">' in card.back:
            try:
                english = card.back.split('<div class="definition english">')[1].split('</div>')[0].strip()
            except:
                pass
        
        return render_template('edit_word.html', 
                             card=card, 
                             word=word, 
                             pos=pos, 
                             chinese=chinese, 
                             english=english)
    
    # 处理POST请求 - 更新单词
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '无效的请求数据'})
    
    try:
        word = data.get('word', '').strip()
        pos = data.get('pos', '').strip()
        chinese = data.get('chinese', '').strip()
        english = data.get('english', '').strip()
        
        if not word:
            return jsonify({'status': 'error', 'message': '单词不能为空'})
        
        # 检查是否与其他卡片的单词冲突（排除当前卡片）
        unit_cards = get_cards_by_unit(card.unit_id)
        for other_card in unit_cards:
            if other_card.id != card_id and '<h3 class="word">' in other_card.front:
                existing_word = other_card.front.split('<h3 class="word">')[1].split('</h3>')[0].strip().lower()
                if existing_word == word.lower():
                    return jsonify({'status': 'error', 'message': f'单词 "{word}" 已存在于该单元中'})
        
        # 更新卡片正面内容
        front_content = f"""<div class="word-card">
    <h3 class="word">{word}</h3>
    <div class="part-of-speech">{pos}</div>
</div>"""
        
        # 更新卡片背面内容
        back_content = f"""<div class="word-card">
    <h3 class="word">{word}</h3>
    <div class="part-of-speech">{pos}</div>
    <div class="definition chinese">{chinese}</div>
    <div class="definition english">{english}</div>
</div>"""
        
        # 更新卡片内容
        card.front = front_content
        card.back = back_content
        
        # 保存更新
        update_card(card)
        
        return jsonify({
            'status': 'success',
            'message': f'单词 "{word}" 已成功更新'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'更新单词时出错: {str(e)}'})

@app.route('/delete_word/<card_id>', methods=['POST'])
@login_required
def delete_word(card_id):
    """删除单词"""
    username = session.get('username')
    if not username:
        return jsonify({'status': 'error', 'message': '用户未登录'})
    
    try:
        # 检查卡片是否存在
        if username in user_card_states and card_id in user_card_states[username]:
            state = user_card_states[username][card_id]
            
            # 只允许删除用户自己添加的卡片
            if state.is_user_card:
                # 删除用户卡片
                del user_card_states[username][card_id]
                save_cards()
                
                return jsonify({
                    'status': 'success',
                    'message': '单词已成功删除'
                })
            else:
                return jsonify({'status': 'error', 'message': '不能删除系统卡片'})
        else:
            return jsonify({'status': 'error', 'message': '卡片不存在'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'删除卡片时出错: {str(e)}'})

@app.route('/restore_word/<card_id>', methods=['POST'])
@login_required
def restore_word(card_id):
    """还原单词到原始状态"""
    username = session.get('username')
    if not username:
        return jsonify({'status': 'error', 'message': '用户未登录'})
    
    try:
        # 获取系统卡片
        system_card = system_cards.get(card_id)
        if not system_card:
            return jsonify({'status': 'error', 'message': '系统卡片不存在'})
        
        # 检查用户卡片状态是否存在
        if username in user_card_states and card_id in user_card_states[username]:
            state = user_card_states[username][card_id]
            
            # 如果是用户自定义卡片，不能还原
            if state.is_user_card:
                return jsonify({'status': 'error', 'message': '用户自定义卡片不能还原'})
            
            # 还原卡片内容到系统原始状态
            state.is_viewed = False  # 重置查看状态
            state.memory_state = None  # 清除记忆状态
            state.review_logs = []  # 清除复习记录
            state.due_date = system_card.created_at  # 重置到期时间
            state.learning_factor = 1.0  # 重置学习因子
            
            # 保存更改
            save_cards()
            
            return jsonify({
                'status': 'success',
                'message': '单词已成功还原到原始状态'
            })
        else:
            return jsonify({'status': 'error', 'message': '用户卡片状态不存在'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'还原卡片时出错: {str(e)}'})

# ---------------------------------------------------------------------------
# 兼容性处理：某些 Flask 版本(<3.2) 不提供 app.before_serving 装饰器。
# 如果缺失，则动态创建一个简单的替代实现，立即调用目标函数，
# 并返回原函数以保持装饰器语义（只在应用启动时执行一次）。
# 这样既不影响 Render 上的高版本 Flask，也能让本地旧版本正常运行。

if not hasattr(app, "before_serving"):
    def _before_serving(func):  # type: ignore
        # 直接在注册阶段执行一次初始化逻辑
        func()
        return func

    # 动态挂载到 app 对象
    setattr(app, "before_serving", _before_serving)

# 应用初始化时执行数据迁移
if USE_DATABASE and StorageAdapter is not None:
    @app.before_serving  # type: ignore[attr-defined]
    def initialize_database():
        """第一次请求前初始化数据库"""
        # 尝试进行数据迁移
        if os.path.exists(storage_file) or os.path.exists(users_file):
            print("正在尝试将数据从文件迁移到数据库...")
            if StorageAdapter.migrate_data():
                print("数据迁移完成！")
            else:
                print("数据迁移失败，将继续使用文件存储。")

        # 仅在数据库无系统卡片时尝试初始化导入
        try:
            from pathlib import Path
            from import_word_list import import_from_excel, DEFAULT_EXCEL_PATH
            from models.database import get_db_session, SystemCard, UserCardState

            excel_path = os.environ.get("WORD_LIST_PATH", str(DEFAULT_EXCEL_PATH))

            sess = get_db_session()
            try:
                total_cards = sess.query(SystemCard).count()
                needs_overwrite = False
                if total_cards == 0:
                    needs_overwrite = True
                else:
                    # 检测旧版本数据(unit_id 没有前缀的情况)
                    sample = sess.query(SystemCard).first()
                    if sample and not str(sample.unit_id).lower().startswith("unit"):
                        print("检测到旧版本系统卡片(unit_id 无前缀)，将执行覆盖导入…")
                        needs_overwrite = True

                if needs_overwrite:
                    if Path(excel_path).exists():
                        added = import_from_excel(excel_path, overwrite=True)
                        print(f"系统卡片初始化/覆盖完成，导入 {added} 张。")
                        if added:
                            # 导入后刷新内存中的 system_cards / user_card_states
                            try:
                                load_cards()
                                print("已刷新内存缓存的系统卡片数据")
                            except Exception as refresh_err:
                                print(f"刷新内存系统卡片失败: {refresh_err}")
                    else:
                        print(f"首次部署：未找到 Excel 文件 {excel_path} ，跳过初始化导入 (请确保提供词汇表 Excel 文件) ")

                        try:
                            # 找出所有 unit_id 不以 'unit' 开头的系统卡片
                            from sqlalchemy import not_  # 本地导入，避免循环依赖
                            legacy_cards = sess.query(SystemCard).filter(not_(SystemCard.unit_id.ilike('unit%'))).all()
                            updated_count = 0

                            for card in legacy_cards:
                                old_unit = str(card.unit_id).strip()
                                new_unit = f"unit{old_unit}"

                                # 根据旧 card_id 推算新 card_id（保持后缀不变）
                                if card.id.startswith(f"{old_unit}_"):
                                    suffix = card.id.split('_', 1)[1]
                                    new_card_id = f"{new_unit}_{suffix}"
                                else:
                                    # 如果 card_id 格式异常，直接跳过，避免破坏数据
                                    print(f"⚠️ 跳过无法解析 card_id 的旧卡片: {card.id}")
                                    continue

                                # 若目标 ID 已存在，说明之前迁移过，直接跳过
                                if sess.get(SystemCard, new_card_id):
                                    print(f"⚠️ 目标卡片已存在，跳过: {new_card_id}")
                                    continue

                                # 更新 SystemCard 主键及 unit_id
                                setattr(card, 'unit_id', new_unit)
                                setattr(card, 'id', new_card_id)

                                # 同步更新所有关联的 UserCardState.card_id
                                sess.query(UserCardState).filter_by(card_id=f"{old_unit}_{suffix}").update({
                                    'card_id': new_card_id
                                }, synchronize_session=False)

                                updated_count += 1

                            if updated_count:
                                sess.commit()
                                print(f"✅ 已修复 {updated_count} 张系统卡片的 unit 前缀")

                                # 修复后刷新内存缓存
                                try:
                                    load_cards()
                                    print("已刷新内存缓存的系统卡片数据")
                                except Exception as refresh_err:
                                    print(f"刷新内存系统卡片失败: {refresh_err}")
                            else:
                                print("ℹ️ 未检测到需要修复的旧版系统卡片")
                        except Exception as fix_err:
                            sess.rollback()
                            print(f"❌ 修复 unit 前缀时出错: {fix_err}")
            finally:
                sess.close()
        except Exception as imp_err:
            print(f"启动时初始化系统卡片失败: {imp_err}")

# 在文件末尾添加端口绑定代码
if __name__ == '__main__':
    # 获取环境变量中的端口，如果不存在则使用默认的5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

def create_card_states_for_all_users(card_id, unit_id, front, back, created_at):
    """为所有现有用户创建指定系统卡片的默认状态"""
    if USE_DATABASE and StorageAdapter is not None:
        try:
            from models.database import get_db_session, User, UserCardState
            session_db = get_db_session()
            try:
                # 获取所有用户
                users = session_db.query(User).all()
                
                # 为每个用户创建该卡片的默认状态
                for user in users:
                    # 检查是否已存在
                    existing = session_db.query(UserCardState).filter_by(
                        username=user.username, 
                        card_id=card_id
                    ).first()
                    
                    if not existing:
                        user_state = UserCardState(
                            username=user.username,
                            card_id=card_id,
                            is_viewed=False,
                            due_date=created_at,
                            learning_factor=1.0,
                            is_user_card=False
                        )
                        session_db.add(user_state)
                
                session_db.commit()
                print(f"为 {len(users)} 个用户创建了卡片 {card_id} 的默认状态")
                return True
            except Exception as e:
                session_db.rollback()
                print(f"为用户创建卡片状态失败: {e}")
                return False
            finally:
                session_db.close()
        except Exception as e:
            print(f"导入数据库模块失败: {e}")
            return False
    else:
        # 文件存储模式
        try:
            # 为所有用户创建该卡片的默认状态
            for username in user_card_states:
                if card_id not in user_card_states[username]:
                    user_card_states[username][card_id] = CardState(
                        card_id=card_id,
                        is_viewed=False,
                        due_date=created_at,
                        learning_factor=1.0,
                        is_user_card=False
                    )
            
            save_cards()
            print(f"为 {len(user_card_states)} 个用户创建了卡片 {card_id} 的默认状态")
            return True
        except Exception as e:
            print(f"为用户创建卡片状态失败: {e}")
            return False