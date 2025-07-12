# FSRS应用 - Render部署指南

## 部署准备

### 1. 环境变量设置
在Render平台上，您需要设置以下环境变量：

- `SECRET_KEY`: 用于Flask会话加密的密钥（必须设置，建议使用随机生成的字符串）
- `FLASK_DEBUG`: 设置为"False"用于生产环境
- `RENDER`: 设置为"True"，用于启用Render特定配置
- `PYTHON_VERSION`: 设置为"3.9"或更高版本

### 2. 持久化存储
应用配置为使用Render的持久化存储，数据文件将保存在`/data`目录中。确保在Render仪表板中添加一个持久化磁盘，并将其挂载到`/data`路径。

## 部署步骤

1. 在Render仪表板中，点击"New +"并选择"Web Service"
2. 连接您的Git仓库
3. 填写以下信息:
   - **Name**: fsrs-app（或您喜欢的名称）
   - **Environment**: Python
   - **Build Command**: `pip install -r fsrs_web/requirements.txt`
   - **Start Command**: `cd fsrs_web && gunicorn -c gunicorn_config.py app:app`

4. 添加环境变量：
   - `SECRET_KEY`: 设置安全的随机字符串
   - `FLASK_DEBUG`: False
   - `RENDER`: True

5. 添加持久化磁盘:
   - 点击"Advanced"，然后选择"Add Disk"
   - 磁盘名称: data
   - 挂载路径: /data
   - 大小: 1GB（可根据需要调整）

6. 点击"Create Web Service"启动部署

## 故障排除

如果遇到问题，请检查以下事项:

1. 查看Render日志以了解任何错误信息
2. 确保所有必需的环境变量已正确设置
3. 确认持久化磁盘已正确挂载到`/data`路径
4. 验证Python版本与应用兼容（建议3.9+）

## 注意事项

- 第一次部署后，系统将创建新的数据文件。如果您需要导入现有数据，可以使用Render的SSH功能连接到服务并手动上传数据文件。
- 在render.yaml文件中配置了健康检查路径，确保您的应用主页(`/`)可以在未登录状态下正常访问，否则需要修改健康检查路径。 