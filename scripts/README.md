# 管理脚本使用说明

## 脚本列表

### 1. migrate_old_pickle.py
**用途**: 将本地文件数据迁移到数据库
**用法**: 
```bash
python scripts/migrate_old_pickle.py
```
**说明**: 一次性脚本，将 `card_states.pkl` 和 `users.json` 中的数据迁移到 PostgreSQL 数据库

### 2. add_system_card.py
**用途**: 添加新的系统卡片并为所有用户创建默认状态
**用法**:
```bash
python scripts/add_system_card.py <unit_id> <front_content> <back_content>
```
**示例**:
```bash
python scripts/add_system_card.py unit1 "新单词" "新单词的解释"
```
**说明**: 
- 自动生成卡片ID
- 为所有现有用户创建该卡片的默认状态
- 新用户注册时会自动获得所有系统卡片

### 3. fix_missing_card_states.py
**用途**: 为现有用户创建缺失的卡片状态
**用法**:
```bash
python scripts/fix_missing_card_states.py
```
**说明**: 检查所有用户是否都有所有系统卡片的状态，如果没有则创建

## 环境要求

所有脚本都需要以下环境变量：
```bash
export USE_DATABASE=true
export DATABASE_URL="postgresql://..."
```

## 使用场景

### 新用户注册
- 自动为新用户创建所有系统卡片的默认状态
- 无需手动操作

### 添加新系统卡片
1. 使用 `add_system_card.py` 添加新卡片
2. 脚本会自动为所有现有用户创建该卡片的默认状态
3. 新用户注册时会自动获得该卡片

### 修复数据不一致
如果发现某些用户缺少卡片状态：
```bash
python scripts/fix_missing_card_states.py
```

## 注意事项

1. 所有脚本都会连接到线上数据库
2. 脚本执行前请确保数据库连接正常
3. 建议在执行前备份数据库
4. 脚本会自动处理重复数据，不会创建重复记录 