"""
核心模块包初始化。
按分层架构组织: 
- api: HTTP/RESTful 路由, 仅处理请求/响应
- services: 业务逻辑服务(领域规则集中)
- domain: 领域模型与枚举(核心数据结构)
- infrastructure: 基础设施(存储、外部服务客户端)
- utils: 通用工具(鉴权、时间等)
- config: 配置加载与模型
"""