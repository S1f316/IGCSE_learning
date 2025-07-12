import os

# 工作进程数量 - 可以根据应用需求调整
workers = int(os.environ.get('GUNICORN_WORKERS', '2'))

# 每个工作进程的线程数
threads = int(os.environ.get('GUNICORN_THREADS', '2'))

# 超时设置
timeout = 120

# 绑定地址
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# 工作模式
worker_class = 'sync'

# 限制请求行的大小
limit_request_line = 0

# 应用程序模块路径
app = 'app:app' 