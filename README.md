# FSRS应用 - Render部署指南

## 部署准备

### 1. 环境变量设置
在Render平台上，您需要设置以下环境变量：

- `SECRET_KEY`: 用于Flask会话加密的密钥（已配置为自动生成）
- `FLASK_DEBUG`: 设置为"False"用于生产环境
- `RENDER`: 设置为"True"，已配置
- `USE_DATABASE`: 设置为"True"，已配置
- `DATABASE_URL`: PostgreSQL数据库连接URL，已配置
- `PYTHON_VERSION`: 设置为"3.9"或更高版本，已配置

### 2. 数据库配置
应用程序已配置为使用PostgreSQL数据库进行数据存储。数据库连接信息已在render.yaml中设置，无需额外配置。

## 部署步骤

1. 在Render仪表板中，点击"New +"并选择"Web Service"
2. 连接您的Git仓库
3. 填写以下信息:
   - **Name**: fsrs-app（或您喜欢的名称）
   - **Environment**: Python
   - **Build Command**: `pip install -r fsrs_web/requirements.txt`
   - **Start Command**: `cd fsrs_web && gunicorn -c gunicorn_config.py app:app`

4. 环境变量设置已在render.yaml中自动配置：
   - `SECRET_KEY`: 自动生成
   - `FLASK_DEBUG`: False
   - `RENDER`: True
   - `USE_DATABASE`: True
   - `DATABASE_URL`: 已配置为指向PostgreSQL数据库

5. 点击"Create Web Service"启动部署

## 故障排除

如果遇到问题，请检查以下事项:

1. 查看Render日志以了解任何错误信息
2. 确保所有必需的环境变量已正确设置
3. 确认数据库连接是否正常工作
4. 验证Python版本与应用兼容（建议3.9+）

## 数据库迁移

- 应用程序会在第一次启动时自动尝试将数据从文件系统迁移到数据库。
- 如果迁移失败，您可以在日志中看到相关信息。
- 迁移完成后，旧的文件系统数据将被保留，但不再使用。

## 注意事项

- 初次部署后，系统将自动创建数据库表结构。
- 如果您需要从本地环境导入数据，可以先将应用部署到Render，然后上传数据到本地文件系统路径，应用会自动尝试迁移到数据库。
- 在render.yaml文件中配置了健康检查路径，确保您的应用主页(`/`)可以在未登录状态下正常访问，否则需要修改健康检查路径。 
