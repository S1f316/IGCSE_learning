import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 基础路径配置
BASE_DIR = Path(__file__).resolve().parent

# 本地开发使用文件存储
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

# 文件路径配置(仅用于本地开发)
CARD_STATES_FILE = DATA_DIR / 'card_states.pkl'
USERS_FILE = DATA_DIR / 'users.json'

# 数据库配置
# 优先使用环境变量中的数据库URL，否则使用默认连接字符串
DATABASE_URL = os.environ.get(
    'DATABASE_URL', 
    'postgresql://chusheng_db_5djd_user:CEVrhJEIfditwICZpC4xfRwW0hXxFzJo@dpg-d1ov19ur433s73cpu850-a.singapore-postgres.render.com/chusheng_db_5djd'
)

# 判断是否使用数据库存储(在Render平台上或明确设置了USE_DATABASE环境变量时使用)
USE_DATABASE = os.environ.get('RENDER', '') or os.environ.get('USE_DATABASE', '').lower() == 'true'

# Flask配置
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_for_development_only')
DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' 