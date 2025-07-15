#!/usr/bin/env python3
"""
一次性脚本：
将旧版 `card_states.pkl`（扁平字典格式）迁移到数据库。
运行前确保：
  * 环境变量 `USE_DATABASE=true` 且 `DATABASE_URL` 指向有效的 PostgreSQL
  * `pip install -r fsrs_web/requirements.txt` 已完成
用法：
  python scripts/migrate_old_pickle.py
"""
from __future__ import annotations
import os
import sys
import pickle
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / 'fsrs_web' / 'data' / 'card_states.pkl'

# 将 fsrs_web 加入 import 路径，使 pickled 类能正确反序列化
sys.path.insert(0, str(BASE_DIR / 'fsrs_web'))

try:
    # 注册 Card/MemoryState 等类定义
    import app as fsrs_app  # type: ignore  # noqa: F401
except Exception as e:
    print(f"❌ 无法导入 fsrs_app: {e}")
    sys.exit(1)

from models.storage import StorageAdapter  # type: ignore  # noqa: E402

if not DATA_FILE.exists():
    print(f"❌ 未找到数据文件: {DATA_FILE}")
    sys.exit(1)

with open(DATA_FILE, 'rb') as f:
    all_data = pickle.load(f)

if not isinstance(all_data, dict):
    print("❌ 未识别的数据格式，迁移终止")
    sys.exit(1)

# 判断新旧格式
if 'system_cards' in all_data and 'user_card_states' in all_data:
    system_cards = all_data['system_cards']
    user_card_states = all_data.get('user_card_states', {})
    user_fsrs_params = all_data.get('user_fsrs_params', {})
    print("✅ 检测到新格式 pickle，直接保存")
else:
    system_cards = all_data
    user_card_states = {}
    user_fsrs_params = {}
    print("ℹ️  检测到旧格式 pickle，已转换为新结构")

print(f"📦 准备导入系统卡片数量: {len(system_cards)}")

# 调用 StorageAdapter 保存到数据库
print("⏳ 正在写入数据库……")
StorageAdapter.save_cards(system_cards, user_card_states, user_fsrs_params)
print("✅ 写入完成！") 