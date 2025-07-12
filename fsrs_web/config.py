import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 基础路径配置
BASE_DIR = Path(__file__).resolve().parent

# 在Render上使用持久化存储
if os.environ.get('RENDER', ''):
    DATA_DIR = Path('/data')
else:
    DATA_DIR = BASE_DIR / 'data'

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)

# 文件路径配置
CARD_STATES_FILE = DATA_DIR / 'card_states.pkl'
USERS_FILE = DATA_DIR / 'users.json'

# Flask配置
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_for_development_only')
DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' 