# 🔍 Railway-8620 代码细节面试 Q&A 大全（按技术栈分类）

> **用途**：应对"面试官打开你的 GitHub 仓库、指着具体代码提问"的场景——比如"我看你用了 POST 传信息，传的是什么信息？"这类**代码细节题**。
> **与 interview-qa.md 的区别**：那份是宏观架构题（"介绍下项目"、"最难的点"），这份是**微观代码题**（"这行代码是干嘛的"、"为什么这么写"）。
> **使用方法**：每个板块先看 B 站视频复习底层知识 → 再过本项目的 Q&A → 最后回到源码对照。

---

## 📺 关于 B 站链接的说明

每个板块标题下的 B 站链接都是**真实视频直链**，且**优先选了 2025–2026 年新发布的**（技术迭代快，老视频容易过时）。点开即可看，括号里标了播放量/作者/发布时间便于判断。

| 标准 | 说明 |
|---|---|
| 优先 2025–2026 年发布 | 框架版本、API 写法不会过时 |
| **优先短视频（≤1 小时）** | 复习用，别选十几小时的系统课 |
| 面试速成看"面试"系列 | JWT 面试、GIL 面试、响应式原理面试 |

> 💡 视频终究会过时，建议以官方文档为主、视频为辅。链接失效时直接在 B 站搜板块关键词即可。

---

## 目录

1. [HTTP 协议与 RESTful 设计](#一http-协议与-restful-设计)
2. [FastAPI 框架](#二fastapi-框架)
3. [Pydantic 数据校验](#三pydantic-数据校验)
4. [SSE 与流式传输](#四sse-与流式传输)
5. [Python 异步编程（asyncio）](#五python-异步编程asyncio)
6. [Python 语言特性（生成器/装饰器/描述符）](#六python-语言特性)
7. [LangChain / LangGraph / Agent](#七langchain--langgraph--agent)
8. [数据库与 SQL（SQLite/SQLAlchemy）](#八数据库与-sql)
9. [Web 安全（JWT/CORS/注入）](#九web-安全)
10. [前端 Vue 3 / TypeScript](#十前端-vue-3--typescript)
11. [Docker 与 Nginx 部署](#十一docker-与-nginx-部署)
12. [测试（pytest/Mock）](#十二测试pytestmock)
13. [Git 与工程化](#十三git-与工程化)

---

# 一、HTTP 协议与 RESTful 设计

> 📺 **B 站复习**：[HTTP 协议 5 分钟讲透（9月）](https://www.bilibili.com/video/BV1yKYJ61Ed8/) · [HTTP 高频响应码精讲（9月）](https://www.bilibili.com/video/BV1EyY36mEkD/) · [RESTful API 凭什么火了 20 多年（9月）](https://www.bilibili.com/video/BV1SjeB6yEuX/) · [API 设计最佳实践（郭宏志 8月）](https://www.bilibili.com/video/BV1dHMQ6tEYG/)

## Q1. 我看你项目里用了 POST 来传信息，传的是什么信息？

> 两个 POST 接口，传的都是**聊天的核心数据**：
>
> 1. `POST /chat/stream`——请求体是 JSON：`{"message": "用户的问题", "session_id": "会话UUID"}`，请求头带 `Authorization: Bearer <JWT>`。message 是要发给 LLM 的内容，session_id 用于定位多轮对话的历史。
> 2. `POST /auth/login`——这个传的是 **Form 格式**（`application/x-www-form-urlencoded`），不是 JSON，因为用的是 FastAPI 的 `OAuth2PasswordRequestForm`，它要求表单编码。前端对应用 `FormData` 提交。
>
> 为什么聊天用 POST 而不是 GET：① message 是用户输入的自由文本，可能很长（上限 8000 字符），GET 的 URL 长度有限制；② 语义上这是"提交一个任务"而非"获取资源"；③ 避免敏感内容出现在 URL 和服务器日志里。

## Q2. 为什么 /chat/sessions 用 GET、重命名用 PUT、删除用 DELETE？这是 RESTful 吗？

> 是的，按 RESTful 语义设计的：
>
> | 方法 | 路径 | 语义 | 幂等 |
> |---|---|---|---|
> | GET | /chat/sessions | 读取资源（列表） | 是 |
> | GET | /chat/sessions/{id} | 读取单个资源 | 是 |
> | PUT | /chat/sessions/{id} | 更新资源（重命名） | 是 |
> | DELETE | /chat/sessions/{id} | 删除资源 | 是 |
> | POST | /chat | 创建/提交（发起对话） | 否 |
>
> **幂等性**指"同一请求执行多次和执行一次效果相同"：GET/PUT/DELETE 幂等（重复删一个已删的资源，结果还是不存在），POST 不幂等（重复提交会创建多个对话）。

## Q3. 422 状态码是什么？你项目哪里返回的？

> 422 = Unprocessable Entity，"请求格式正确但内容校验失败"。我的项目里所有 Pydantic 校验失败都返回 422：比如 session_id 传了非法字符（正则不匹配）、message 为空或超 8000 字符、重命名标题超 100 字。
>
> 和 400 的区别：400 是"请求本身格式错误"（如 JSON 语法坏了），422 是"格式对但语义校验不通过"。FastAPI 的 Pydantic 校验失败默认返回 422。

## Q4. 401 和 403 有什么区别？你的项目怎么用的？

> - **401 Unauthorized**：没登录或凭证无效——"我不知道你是谁"。我的项目里 JWT 缺失/过期/伪造时返回 401，前端收到后清除 token 跳登录页。
> - **403 Forbidden**：登录了但没权限——"我知道你是谁，但你不能干这个"。我的会话接口里，访问别人的 thread_id 时返回的是业务层的 `{"ok": false, "error": "无权限"}`（HTTP 仍是 200），这是设计取舍：把越权当作正常业务分支处理，避免给攻击者探测信息。
>
> 严格 RESTful 应该用 403，但业务层 JSON 响应的好处是前端处理逻辑统一（都看 ok 字段）。

## Q5. 你的接口为什么路径里有 {thread_id:path}？path 是什么？

> 这是 FastAPI 的**路径参数转换器**。默认 `{thread_id}` 只匹配不含 `/` 的一段路径；加 `:path` 后可以匹配含 `/` 的多级路径。
>
> 我的 thread_id 格式是 `user_4_1815fbee-67f1-...`，虽然当前不含 `/`，但用 `:path` 有两个好处：① 防止未来 thread_id 格式变化导致路由误切分；② URL 编码后的特殊字符不会被路由拒绝。前端请求时用 `encodeURIComponent(threadId)` 编码配合。

## Q6. 请求头里你都用了什么？各自干嘛的？

> - `Authorization: Bearer <JWT>`——身份凭证，get_current_user 依赖解析它
> - `Content-Type: application/json`——聊天接口的请求体格式
> - `Content-Type: multipart/form-data`——登录接口（OAuth2 表单）
> - 响应头 `Content-Type: text/event-stream`——SSE 流式响应的标识
>
> 另外爬虫子项目里还用了 `Origin`/`Referer`/`User-Agent`/`Sec-Fetch-*`——模拟浏览器请求头绕过 12306 的基础反爬。

---

# 二、FastAPI 框架

> 📺 **B 站复习**（都是 1 小时内的短视频，适合复习）：[10 分钟学会 FastAPI（Indently 8月）](https://www.bilibili.com/video/BV1g88967E18/) · [10 分钟入门 FastAPI 实战示例（8月）](https://www.bilibili.com/video/BV1G38w6BEKN/) · [FastAPI 入门 36 分钟（零到全栈 7月）](https://www.bilibili.com/video/BV1LW3K63ExS/) · [1 小时精通 FastAPI 知识点（科科 48min）](https://www.bilibili.com/video/BV1JTCQBQERg/) · [依赖注入 DI 18 分钟（9月）](https://www.bilibili.com/video/BV1Yato6REW6/) · [请求中间件 18 分钟（9月）](https://www.bilibili.com/video/BV1Yato6RE2U/) · [中间件必看 10 分钟（1月）](https://www.bilibili.com/video/BV1yizsBGEco/)

## Q1. 为什么选 FastAPI 而不是 Flask / Django？

> ① **原生异步**——ASGI 架构，SSE 流式和 async 端点是刚需；② **自动校验**——Pydantic 集成，请求体校验和 Swagger 文档免费获得；③ **类型提示驱动**——IDE 补全和静态检查友好；④ 轻量——Django 的大而全（ORM/Admin/Auth）对这个项目是负担。Flask 同步模型做 SSE 要额外折腾 gevent，FastAPI 原生支持。

## Q2. Depends 是什么？你项目里怎么用的？

> 依赖注入机制：路由函数的参数声明 `Depends(函数)`，FastAPI 在调用路由前自动执行该函数并把返回值注入。
>
> 我项目两处核心使用：
> 1. `current_user: User = Depends(get_current_user)`——鉴权。get_current_user 内部解析 JWT → 查库 → 返回 User 对象或抛 401。任何路由加了这行参数就自动受保护；
> 2. `db: Session = Depends(database.get_db)`——数据库会话。get_db 是生成器，yield 会话、finally 关闭，保证请求结束必释放。
>
> 好处：① 业务代码不用管"怎么拿到用户/连接"，只管用；② 测试时用 `app.dependency_overrides[get_current_user] = lambda: fake_user` 一行替换，我的 API 测试全靠这个绕过真实认证。

## Q3. lifespan 是什么？你项目里干了什么？

> 应用生命周期钩子——`@asynccontextmanager` 装饰的函数，yield 之前是启动逻辑、之后是关闭逻辑。
>
> 我的 lifespan：启动时**什么都不做**（Agent 懒加载，避免空 API key 崩启动）；关闭时两步清理——`_agent_service.close()` 释放 Agent 持有的 SQLite 连接，`_agent_executor.shutdown(wait=True)` 优雅关闭线程池（等在跑的任务结束）。
>
> 对应 Spring 的 @PostConstruct/@PreDestroy。

## Q4. app.mount 是干嘛的？

> 挂载子应用/静态文件服务。我的用法：`app.mount("/maps", StaticFiles(directory=_maps_dir))`——把磁盘上的地图目录映射为 `/maps` URL 路径，浏览器请求 `/maps/T35_route.html` 时直接返回磁盘文件。
>
> StaticFiles 自动处理 Content-Type、缓存头、路径穿越攻击防护（`../` 会被拦）。比手写 FileResponse 路由省事且安全。

## Q5. include_router 是什么？为什么 auth 要单独一个 router？

> router 是路由分组。auth.py 里 `APIRouter(prefix="/auth", tags=["auth"])` 定义了一组认证路由，主文件 `app.include_router(auth.router)` 挂载进来。
>
> 好处：① 认证逻辑独立成模块，主文件不膨胀；② prefix 统一加前缀；③ tags 让 Swagger 文档分组展示。我的 auth.py 和 api.py 是两个文件，靠 router 组合。

## Q6. 中间件是什么？和 Depends 什么区别？

> 中间件是**所有请求**进出的统一关卡（洋葱模型）；Depends 只作用于**声明了它的路由**。
>
> 我项目用 CORSMiddleware 给所有响应加跨域放行头。选择标准：所有请求都要的（CORS）→ 中间件；部分路由要的（鉴权）→ Depends；单函数的 → 装饰器（如工具日志 @log_tool_call）。
>
> 对应 Spring：中间件 ≈ Filter，Depends ≈ HandlerInterceptor/AOP。

## Q7. Swagger 文档是怎么来的？

> FastAPI 自动生成——启动后访问 `/docs` 就是交互式 API 文档。它从三处提取信息：路由路径和方法、Pydantic 模型（请求体/响应体结构）、tags 分组。`response_model=Token` 这样的声明会让文档显示响应结构。OAuth2PasswordRequestForm 还让 /docs 页面出现"Authorize"按钮，可以直接在文档里登录测试。

---

# 三、Pydantic 数据校验

> 📺 **B 站复习**：[Pydantic for LLM 官方课程（吴恩达 9月）](https://www.bilibili.com/video/BV1w1hv6EE4A/) · [Pydantic 用于 LLM 工作流（吴恩达 1.2万 5月）](https://www.bilibili.com/video/BV1SMRpBmEyG/) · [Pydantic 数据验证完整教程（2025-10）](https://www.bilibili.com/video/BV1B5yqBCEPT/)

## Q1. Pydantic 是什么？为什么需要它？

> 数据校验和序列化库。FastAPI 里它承担三件事：① 解析请求体（JSON → Python 对象）；② 校验（类型不对/规则不满足 → 自动 422）；③ 生成 JSON Schema（Swagger 文档的数据来源）。
>
> 没有它就得手写 `if not isinstance(...)` 一堆判断，而且错误响应格式不统一。

## Q2. field_validator 是怎么工作的？

> 字段级校验钩子：**字段解析后、路由函数执行前**自动运行。返回值是清洗后的值（我用来 strip 空格），抛 ValueError 则 FastAPI 转 422。
>
> 我项目三个校验器：session_id 正则白名单（防注入）、message 非空+长度限制、重命名标题非空+长度限制。校验发生在路由函数之前——非法请求在入口就被拦，不浪费 Agent 资源。

## Q3. ClassVar 是什么？为什么你的正则要加它？（⭐ 你踩过坑）

> `typing.ClassVar` 标记"这是类变量，不是实例字段"。**必须加**，因为 Pydantic v2 的规则：BaseModel 里的类属性默认都当字段处理，字段必须有类型注解——无注解属性会报 PydanticUserError。
>
> 我踩的坑更深：最初写的是 `_SESSION_ID_RE = re.compile(...)`（`_` 前缀 + 无注解），Pydantic 把它判定为"私有属性"，包装成 ModelPrivateAttr 并从 __dict__ 移走。关键的不对称：**类级访问（cls.xxx）返回包装对象不解包，实例级访问才返回真值**——而 field_validator 必然是 classmethod（校验在实例创建前），只能用 cls，于是 .match() 抛 AttributeError，所有 /chat 请求 500。
>
> 最终修复：ClassVar 注解 + 去掉下划线。去掉下划线还有个好处——如果将来有人误删 ClassVar，Pydantic 会在类定义时立刻报错（无下划线+无注解=响亮报错），而不是像有下划线那样静默埋雷到运行时。

## Q4. model_dump 和 JSON 序列化什么关系？

> `model_dump()` 把模型实例转成 dict（只含字段，ClassVar 和私有属性都不出现），配合 `json.dumps` 完成序列化。我项目里 SSE 响应就是 `json.dumps({'content': ...}, ensure_ascii=False)`——ensure_ascii=False 让中文按 UTF-8 直传而不是转义成 \uXXXX。

## Q5. 私有属性和类常量什么区别？

> **存储和共享范围不同**：类常量（ClassVar）存在类上，全类共享一份，cls 直接访问；私有属性（_ 前缀 + PrivateAttr）存在每个实例的 `__pydantic_private__` 里，各实例独立，设计上通过 self 访问。
>
> 我的正则是"全类共享的不变量"，所以用类常量——语义正确且避开 cls 访问私有属性的坑。

---

# 四、SSE 与流式传输

> 📺 **B 站复习**：[SSE 才是 AI 流式输出的答案（1.3万 6月）](https://www.bilibili.com/video/BV15F7J6dEdm/) · [用 FastAPI 讲透 SSE 流式响应（6月）](https://www.bilibili.com/video/BV1if7E64Ex5/) · [SSE vs WebSocket 面试（9月）](https://www.bilibili.com/video/BV1MZYT6pEsE/) · [7 分钟了解 SSE（1.4万）](https://www.bilibili.com/video/BV12auGzHEK2/)

## Q1. SSE 是什么？数据格式是什么？

> Server-Sent Events，基于 HTTP 的**服务器单向推送**协议。响应头 `Content-Type: text/event-stream`，数据格式：
>
> ```
> data: {"content": "前"}\n\n
> data: {"content": "进"}\n\n
> data: [DONE]\n\n
> ```
>
> `data:` 是字段前缀，`\n\n`（空行）是事件边界，`[DONE]` 是借 OpenAI 约定的自定义结束哨兵。前端用 `split('\n\n')` 切事件、`JSON.parse` 取内容。

## Q2. SSE 和 WebSocket 什么区别？为什么选 SSE？

> SSE 是 HTTP 上的**单向**推送（服务器→客户端），WebSocket 是独立协议的**双向**通道。我的场景只需要服务器往客户端推 token，SSE 更轻：不用协议升级、不用心跳、Nginx 代理友好、断线浏览器自动重连。OpenAI 的流式 API 也是 SSE。

## Q3. StreamingResponse 是怎么工作的？

> FastAPI 的流式响应类：传入一个生成器，它**每 yield 一段就立刻发给客户端**，而不是攒齐再发。我的 generate() 是 async 生成器，每次 yield 一个 SSE 事件。Starlette 在事件循环里迭代这个生成器——这也是为什么生成器里的阻塞操作必须走 executor。

## Q4. Nginx 代理 SSE 有什么坑？

> `proxy_buffering off`——Nginx 默认攒响应缓冲再发，会把流式变成"卡半天突然出一大段"。还要 `proxy_read_timeout 300s` 匹配后端的单块超时。这是 SSE 上生产的经典坑，我配置里都处理了。

## Q5. [DONE] 标记是干嘛的？

> SSE 协议没有"流结束"标志，连接断开分不清是正常结束还是异常中断。`[DONE]` 放在 generate() 的 try/except **之外**——后端活着就必发。所以它的**缺席**就意味着进程崩溃或断网（后端无法控制的中断），沉默本身就是信号。前端收到后跳过不显示，等下一次 read 的 done 退出循环。

---

# 五、Python 异步编程（asyncio）

> 📺 **B 站复习**：[asyncio 小白速通（1万 2025-11）](https://www.bilibili.com/video/BV1KmUpB8EJ3/) · [async+await+future 高频面试考点（4.2万）](https://www.bilibili.com/video/BV1JsLDzAEGu/) · [15 分钟看懂 GIL（9356）](https://www.bilibili.com/video/BV1RHz4B8EE8/) · [FastAPI 没加 async 性能入土（1万）](https://www.bilibili.com/video/BV1gn7DzXEEj/)

## Q1. 什么是事件循环？为什么阻塞代码会冻结它？

> 事件循环是 async 程序的调度器——**单线程**不断轮询"哪个任务就绪了就执行哪个"。它高效的前提是：每个任务在等待 I/O 时主动 `await` 让出控制权。
>
> 如果在事件循环线程里写了阻塞代码（如同步网络请求卡 30 秒），这个线程被占死——**所有**其他任务的 await 无法恢复、新请求无法接收，整个服务冻结。这就是为什么我的 async 端点里所有阻塞调用都必须 run_in_executor 扔线程池。

## Q2. async/await 到底是什么意思？

> `async def` 定义协程函数——调用它返回协程对象，**不执行函数体**；`await` 表示"这里要等一个异步操作的结果，等待期间让出线程给事件循环"。
>
> 关键：await 只能等"可等待对象"（协程、Task、Future）。`await run_in_executor(...)` 是把同步阻塞操作包成 Future 来等——等待期间事件循环自由，这就是不冻结的原因。

## Q3. run_in_executor 是干嘛的？为什么必须用 lambda？

> 把同步阻塞函数扔到线程池执行，返回 awaitable。两个细节：
> 1. **必须包 lambda**：`run_in_executor(pool, agent.stream(...))` 是错的——这是先在当前线程调用 stream() 再把返回值交给池子，阻塞已经发生了。正确写法 `run_in_executor(pool, lambda: agent.stream(...))`，交给池子的是"未执行的函数"；
> 2. **生成器的惰性**：agent.stream() 返回生成器对象本身不耗时，真正的重活在每次 next() 里——所以我的代码建流和每次取块**分别**走 executor，取块循环里每次 next() 都单独 run_in_executor + 300 秒超时。

## Q4. GIL 是什么？影响你的项目吗？

> 全局解释器锁——CPython 里同一时刻只有一个线程执行 Python 字节码。**只影响 CPU 密集任务**（假并行）；I/O 等待时 GIL 会释放，所以 I/O 密集的多线程是真并发。
>
> 我项目的负载全是 I/O（等 LLM 响应、等网络、读写 SQLite），8 线程的等待时间互相重叠——这就是 5 并发总耗时约等于单请求 2 倍而非 5 倍的原因。如果是 CPU 密集（本地跑模型），线程方案就废了，得上多进程。

## Q5. asyncio.wait_for 是干嘛的？

> 给 awaitable 加超时：超时抛 asyncio.TimeoutError。我用了两层——建流 60 秒（LLM 慢连接）、单块 300 秒（工具执行慢）。超时后线程里的任务其实还在跑（线程杀不死），只是请求提前返回 error 事件。

## Q6. 同步 def 端点和 async def 端点，FastAPI 怎么区别对待？

> - `def` 端点：FastAPI 自动用 run_in_threadpool 扔进 Starlette 线程池（默认 40 线程）执行——阻塞安全，类似 Spring MVC 每请求一线程；
> - `async def` 端点：直接在事件循环上执行——阻塞代码是毒药。
>
> 我项目 /chat 用 def（一问一答，阻塞安全且代码最简）、/chat/stream 用 async（需要 wait_for 逐块超时和优雅降级）。没统一是因为统一会让两端点争抢同一个自建线程池，失去故障隔离。

---

# 六、Python 语言特性

> 📺 **B 站复习**：[迭代器与生成器（9月）](https://www.bilibili.com/video/BV1JwtZ6NEAo/) · [装饰器/正则/元类/单例 29 个面试考点（9月）](https://www.bilibili.com/video/BV1S6to6JEVq/) · [深入探讨 Python 描述符（1214 3月）](https://www.bilibili.com/video/BV1nLAszcEEf/) · [双下划线到底是什么（2.9万）](https://www.bilibili.com/video/BV1tf7c6YExq/)

## Q1. yield 是什么？和 return 什么区别？

> yield 把函数变成**生成器**：调用时不执行函数体，返回生成器对象；每次 next() 执行到下一个 yield，**交出值并原地暂停**（局部变量和执行位置都保留）；下次 next() 从暂停处恢复。
>
> return 是"算完所有结果一次性返回"，yield 是"要一个产一个"。我的 generate() 靠它实现"LLM 吐一个 token 就发一个 SSE 事件"——如果用 return 收集完整列表，就得等全部生成完才能响应，流式就死了。

## Q2. 装饰器是什么？你项目哪里用了？

> 装饰器是"接收函数返回新函数"的语法糖，用于不修改原函数的前提下增强行为。
>
> 我项目两处：① `@log_tool_call`——记录每次工具调用的参数/结果/耗时到日志；② `@field_validator` / `@classmethod`（Pydantic 的校验钩子）。关键细节：log_tool_call 里必须加 `@functools.wraps(func)`——保留原函数的 __name__/__doc__，否则 LangChain 通过函数名内省工具时会拿到 "wrapper"，工具就失效了。

## Q3. 单下划线和双下划线开头的变量有什么区别？

> - `_x` 单下划线：**约定**"内部使用"，外部能访问但 `import *` 会跳过、IDE 会警告——靠自觉不靠强制；
> - `__x` 双下划线：**名字改写**（name mangling）——自动变成 `_类名__x`，目的是防止子类意外覆盖，不是禁止访问；
> - `__x__` 双下划线前后都有：**魔法方法**（dunder），语言协议钩子（__init__、__getattr__ 等），不要自己发明。
>
> 和 Java 的 private 本质不同：Java 编译器强制，Python 靠约定 + 工具链（linter/IDE 警告）。哲学是"成年人互信"。

## Q4. __getattr__ 和 __setattr__ 是什么？你项目哪里用了？

> 魔法方法：`__getattr__` 在**常规属性查找失败时**触发，`__setattr__` 在**赋值时**触发。
>
> 我项目 `_SettingsProxy` 靠这两个实现配置热更新代理：`__getattr__` 把属性读取转发给内部的 _settings 对象（reload 后所有读取自动拿新值）；`__setattr__` 区分内部状态（_ 开头）和配置项。另外 Pydantic 的 BaseModel 也重写了 __getattr__——我踩的 ModelPrivateAttr 坑就发生在它的私有属性查找逻辑里。

## Q5. 描述符协议是什么？（⭐ 你踩坑的底层原理）

> 描述符是实现了 `__get__`/`__set__`/`__delete__` 的类，放在类属性位置时**拦截属性的访问/赋值**。Python 的 property、classmethod、ORM 字段底层都是描述符。
>
> 我踩的 ModelPrivateAttr 坑：Pydantic 把 `_` 前缀无注解的类属性包装成 ModelPrivateAttr 存进 `__private_attributes__`。实测发现它**不是描述符**（没有 __get__）——Pydantic 对类级访问（ModelMetaclass.__getattr__）直接返回包装对象不解包，对实例级访问（BaseModel.__getattr__）才从 `__pydantic_private__` 取真值。我的 validator 是 classmethod 用 cls 访问，拿到包装对象，调 .match() 就崩。修复：ClassVar 注解 + 去掉下划线。

## Q6. 生成器和迭代器的区别？

> 迭代器是实现了 `__iter__` 和 `__next__` 的对象；生成器是**用 yield 简写出来的迭代器**——解释器自动帮你生成状态机（记住执行位置和局部变量），不用手写。Java 里没有 yield，同等效果要手写 Iterator 状态机（state 变量 + switch 跳转）。

## Q7. with 语句和上下文管理器是什么？

> `with` 调用对象的 `__enter__`/`__exit__`，保证资源必释放（无论是否异常）。我项目：`with open(...) as f` 读文件、`with _agent_lock:` 抢锁（自动释放）、`@asynccontextmanager` 装饰的 lifespan（yield 前启动后关闭）。对应 Java 的 try-with-resources。

---

# 七、LangChain / LangGraph / Agent

> 📺 **B 站复习**：[LangGraph+MCP+RAG 多智能体实战（9月）](https://www.bilibili.com/video/BV1hoaA6CErz/) · [LangChain+LangGraph 16 个实战章节](https://www.bilibili.com/video/BV1Lsht6UEMA/) · [10 分钟搞懂 ReAct Agent](https://www.bilibili.com/video/BV1nqaA64EAJ/) · [LangGraph 智能体实战（尚硅谷 66.5万）](https://www.bilibili.com/video/BV1z3NY66EY1/)

## Q1. ReAct 循环是什么？你的项目里怎么跑的？

> ReAct = Reasoning + Acting：LLM 先推理"我需要什么信息"，调工具获取，看着结果继续推理，直到能回答。
>
> LangGraph 内部是两节点图：LLM 节点 ⇄ 工具节点。终止条件：LLM 输出**不带 tool_calls** 的回答。实测：问"Z227 的信息"跑两轮（调 query_train_info → 组织回答）；"查信息并画地图"跑三轮（system_prompt 里有顺序规则）。

## Q2. tool_calls 是什么结构？

> LLM 输出的 AIMessage 里带的字段：`[{name: "query_train_info", args: {train_codes: ["Z227"]}, id: "call_xxx"}]`——工具名、参数、调用 ID。OpenAI 协议要求：带 tool_calls 的消息后面必须紧跟对应 ID 的 tool 角色消息，否则下次请求 API 直接拒绝——这就是我"中断修复"机制要解决的问题。

## Q3. Checkpointer 是什么？怎么工作的？

> LangGraph 的状态持久化抽象。SqliteSaver 实现：ReAct 每步结束，全量对话状态经 msgpack 序列化写入 checkpoints 表（按 thread_id 索引）。下次同 thread_id 请求取最新快照恢复——多轮记忆的物理本质是"数据库记得你，每次请求把历史重新喂给 LLM"。

## Q4. 工具的 description 为什么重要？

> 它是**给 LLM 看的 API 文档**——LLM 靠它决定"什么时候调这个工具、传什么参数"。我写清了输入格式（"车次列表 ['Z227']"）来降低传参错误率。工具设计三原则：description 写清楚、返回格式化文本而非 JSON、查不到返回提示而非抛异常。

## Q5. system_prompt 里写了什么？

> 角色设定 + 工具使用指南。指南处理模糊和组合场景，比如"用户同时要查信息和画地图时，先调 query_train_info 再调 generate_route_map"——没有这条 LLM 可能只调一个工具或顺序错乱。本质是**编译期**注入路由规则，比运行时重试便宜。

## Q6. LLM 的 API key 配置在哪？怎么加载的？

> `.env` 文件，支持两种写法：直接值 `llm_api_key=sk-xxx`，或环境变量引用 `llm_api_key="HSFZ_API_KEY"`（settings.py 的 _resolve_env_var_refs 用正则判断"值像不像环境变量名"，是就去 os.environ 取真值）。引用方式的好处：.env 可以进 Git，真实 key 放系统环境变量。当前配置：火山方舟 coding 接口 + deepseek-v4-flash。

---

# 八、数据库与 SQL

> 📺 **B 站复习**：[SQL 注入原理与实战（2.7万 2025-11）](https://www.bilibili.com/video/BV1WqUUBAET5/) · [预写日志 WAL 提升性能原理（1178）](https://www.bilibili.com/video/BV1awZRBXE12/) · [SQLAlchemy 核心教程（5月）](https://www.bilibili.com/video/BV14qRxBWEpg/) · [用故事讲透索引/事务/锁（9月）](https://www.bilibili.com/video/BV1G7466MEQf/)

## Q1. SQL 注入怎么防的？（⭐ 必考）

> 核心是**参数化查询**：`?` 占位符 + 参数单独传，数据库把用户输入当"数据"转义，不可能逃逸成 SQL 语法。我项目所有含用户输入的 SQL 都参数化：
>
> ```python
> conn.execute("SELECT ... WHERE thread_id=?", (thread_id,))   # ✅
> # 对应 Java 的 PreparedStatement
> ```
>
> 危险写法是 f-string 拼接：`f"...WHERE thread_id='{thread_id}'"`——用户传 `abc' OR '1'='1` 就能越权。另外叠了两层：入口正则白名单（恶意字符到不了 SQL）、thread_id 前缀校验（防越权）。三层独立，纵深防御。

## Q2. WAL 模式是什么？为什么开？

> Write-Ahead Logging——SQLite 的读写分离日志模式。默认模式写库锁全库（读写互斥），8 线程并发会频繁 database is locked；WAL 下写入追加到 -wal 文件、读者读主库+wal 合并视图，**读写不互斥**。配套 busy_timeout=30000（撞锁等待重试）和 check_same_thread=False（连接跨线程）。20 线程并发测试验证无锁错误。
>
> 细节：WAL 数据写入即持久化（读者看合并视图），SQLite 自动 checkpoint（默认累计 4MB）才搬回主库——搬移是整理不是保存。

## Q3. 为什么有的表用 ORM、有的用原生 SQL？

> 按库的管理者分：`users.db` 是我自己的库，用 SQLAlchemy ORM（User 模型、get_db 会话）；`chat_history_check_pointer` 这个库的**主人是 LangGraph 的 SqliteSaver**（它用裸 sqlite3 管自己的表），我的 session_meta 表放同一个文件里，跟着用裸 sqlite3 + 原生 SQL——为一个 3 字段的表引入第二套 ORM 是负收益，且和旁边 LangGraph 的风格一致。
>
> 对应 Java：schema.sql 里的原生 DDL vs JPA 实体类，按场景分工。

## Q4. 事务是什么？你项目哪里用了 commit？

> 事务保证一组操作要么全成功要么全回滚。我的 delete_session 里三条 DELETE（checkpoints + writes + session_meta）后统一 `conn.commit()`——保证三表删除的原子性，不会出现"标题删了但对话还在"的中间态。rename_session 的 UPSERT 后也 commit。
>
> SELECT 不需要 commit（只读），所以 get_session_messages 里没有。

## Q5. rowcount 是什么？你项目哪里用了？

> Cursor 的属性：最近一次 DML 影响的行数。delete_session 里用它判断"会话是否存在"：`deleted == 0` → 返回"会话不存在"。对应 Java 的 executeUpdate 返回值。

## Q6. 为什么 session_meta 能和 LangGraph 的表放同一个库？

> SqliteSaver 只管理自己的 checkpoints/writes 两张表，不会动其他表——同一个文件里建自己的表互不干扰。收益：省一个数据库文件和一套连接管理。风险：LangGraph 大版本升级动库结构的概率极低（它只操作自己的表）。

---

# 九、Web 安全

> 📺 **B 站复习**：[JWT 真的能替代 Session 吗（4064 9月）](https://www.bilibili.com/video/BV1fKeg6mEt8/) · [一个视频入门密码学：加密/哈希/签名（9月）](https://www.bilibili.com/video/BV1a6bg6oESg/) · [CORS 跨域配置（FastAPI 9月）](https://www.bilibili.com/video/BV1f5b46UEhT/) · [CSRF 攻击原理与防范（1100 7月）](https://www.bilibili.com/video/BV1jE346NESz/) · [XSS 攻击到底有多狠（7月）](https://www.bilibili.com/video/BV1PnNE6gEfe/)

## Q1. JWT 的结构是什么？怎么验证的？

> 三段式：`Header.Payload.Signature`（base64url 编码，点号分隔）。Header 声明算法（HS256），Payload 存 sub（用户名）和 exp（过期时间），Signature 是前两段的 HMAC 签名。
>
> 验证流程：decode 时用密钥重算签名比对（防篡改）→ 检查 exp（防过期）→ 取 sub 查库（确认用户存在）。我显式指定 `algorithms=["HS256"]` 防算法混淆攻击。安全底线：SECRET_KEY 未配置直接抛错，拒绝静默用弱密钥。

## Q2. 为什么密码用 argon2 不用 bcrypt/md5？

> argon2 是**内存困难型**哈希（2015 密码哈希竞赛冠军）——攻击者用 GPU 并行爆破时受内存带宽限制，比 bcrypt（CPU 困难型）更抗专用硬件。md5/SHA 直接淘汰（太快了）。用法：注册 `ph.hash()`，登录 `ph.verify()` 只捕获 VerifyMismatchError。测试坑：库里存明文会抛 InvalidHashError（不是 VerifyMismatchError）导致 500——夹具必须用 ph.hash() 造数据。

## Q3. CORS 是什么？你怎么配的？

> 浏览器同源策略：页面从 A 域加载，默认禁止向 B 域发请求。CORS 是后端**主动声明**"允许来自 xxx 的跨域请求"（响应头 Access-Control-Allow-Origin）。
>
> 我的配置：`CORSMiddleware` + 白名单从环境变量读（默认只放行 Vite dev server 的 8620 端口），支持逗号分隔多来源。`allow_credentials=True` 必须开——否则带 Authorization 头的跨域请求被浏览器拒。实际上我的项目开发走 Vite 代理、生产走 Nginx 反代，页面和 API 同源，CORS 是兜底配置。

## Q4. token 放 localStorage 有什么风险？

> XSS 风险：如果页面被注入恶意脚本，能读到 localStorage 里的 token。缓解：Vue 模板默认转义插值、v-html 只用于受控的 markdown 渲染。更安全的 HttpOnly cookie（JS 读不到）需要额外处理 CSRF 和跨域凭证。个人项目权衡后选 localStorage，生产会重新评估——这是有争议的取舍，面试主动说出来是加分项。

## Q5. XSS 和 CSRF 的区别？

> XSS：攻击者注入恶意**脚本**到页面，在受害者浏览器执行（偷 token、伪造操作）——防法是输出转义 + CSP。CSRF：攻击者诱导受害者**已登录的浏览器**向目标站发请求（借身份）——防法是 CSRF token / SameSite cookie。我的项目：Vue 转义防 XSS；token 放 localStorage（CSRF 拿不到它，因为 CSRF 只能"带 cookie 发请求"不能"读 localStorage"）——所以 localStorage 方案天然免疫 CSRF，这是它相对 cookie 方案的一个优势。

---

# 十、前端 Vue 3 / TypeScript

> 📺 **B 站复习**：[Vue3 从入门到精通（老杜 10.6万）](https://www.bilibili.com/video/BV1fRwtzKEoN/) · [Vue3 极简教程（图灵 71.7万）](https://www.bilibili.com/video/BV13tjqzmEDZ/) · [Vue3 响应式原理面试（Proxy 5月）](https://www.bilibili.com/video/BV1q4Gt6rEtu/) · [路由守卫从全局到组件（9月）](https://www.bilibili.com/video/BV1mJ47z2EuX/)

## Q1. ref 和 reactive 什么区别？你用的哪个？

> `ref` 包装任意类型（访问要 .value），`reactive` 只包装对象（直接访问但整体替换会失去响应性）。我全用 ref——组合式 API 的推荐做法，统一心智。核心场景：`messages = ref([])` 消息数组，每次 SSE 收到 token 就 `msg.content = assistantMessage`，Vue 的响应式系统自动触发重渲染——**打字机效果就是数据流驱动渲染，没有定时器**。

## Q2. 组合式 API（setup）是什么？和选项式什么区别？

> Vue 3 的写法：`<script setup>` 里直接写逻辑，按**功能**组织代码（相关的状态和方法在一起），而不是选项式的按类型分散（data 一堆、methods 一堆）。我项目全部用 `<script setup>` + TypeScript。

## Q3. 路由守卫怎么写的？

> `router.beforeEach` 全局前置守卫：白名单（/login /register）直接放行，已登录访问登录页跳 /chat，其余路径检查 token——无效则 logout 并跳登录页带 redirect 参数（登录后回跳）。组件全部动态 `import()` 实现代码分割。另外 App.vue 还有 30 秒定时器巡检 token 过期——覆盖"长时间停留页面、守卫不触发"的场景。

## Q4. Pinia 是什么？为什么需要？

> Vue 3 官方状态管理。我的 auth store 存 token/username + login/register/logout 动作 + isLoggedIn 计算属性。为什么需要：token 被路由守卫、axios 拦截器、多个组件共同使用——集中存放，logout 一处调用全部同步失效。

## Q5. axios 拦截器做了什么？

> 双拦截器：**请求拦截**——发前检查 token 过期（过期就取消请求跳登录）、塞 Authorization 头；**响应拦截**——401 统一清除凭证跳登录。baseURL 为空（相对路径），开发走 Vite 代理、生产走 Nginx 反代，同一份代码环境无关。
>
> 注意：聊天流式接口没用 axios 用的原生 fetch——因为需要 response.body.getReader() 逐块读，axios 攒齐才回调。

## Q6. v-html 有 XSS 风险吗？

> 有，v-html 不转义直接插入 DOM。我的用法是受控的：内容经过 marked（markdown 渲染）+ 自己的地图卡片替换，来源是 LLM 回答而非用户直接输入（用户输入走文本插值）。严格生产环境应该加 DOMPurify 消毒——这是已知可改进点。

## Q7. 前端怎么处理 SSE 的分包问题？（⭐ 你修过的 bug）

> 两个层面的跨包问题：① **字节级**——UTF-8 汉字 3 字节可能被切在两个网络包，TextDecoder 开 `{stream: true}` 让解码器缓冲不完整序列；② **事件级**——一个 `data: {...}\n\n` 可能被切在两个包，我维护跨 read 的 buffer，split 后 `lines.pop()` 把最后一段（可能是半个事件）留缓冲与下次拼接。修复后用 7 字节极端分包模拟验证：40 个事件全部完整解析 0 失败。

---

# 十一、Docker 与 Nginx 部署

> 📺 **B 站复习**：[40 分钟精通 Docker（技术爬爬虾 69.1万）](https://www.bilibili.com/video/BV1THKyzBER6/) · [都 2026 了还不会写 Dockerfile（5519）](https://www.bilibili.com/video/BV1eKiRBeEPi/) · [Nginx 三大功能配置（技术蛋老师 22.2万）](https://www.bilibili.com/video/BV1TZ421b7SD/) · [Nginx 高并发架构拆解（27.5万）](https://www.bilibili.com/video/BV1gMX1YSEtm/)

## Q1. Dockerfile 的多阶段构建是什么？为什么用？

> 前端 Dockerfile 两个 FROM：第一阶段 node:22-alpine 跑 npm build 产出 dist/；第二阶段 nginx:alpine 只 COPY 构建产物。**好处：最终镜像不含 Node 和 node_modules**，体积从几百 MB 降到几十 MB。后端 Dockerfile 的层缓存技巧：requirements.txt 先 COPY 单独 pip install，代码改动不触发依赖重装。

## Q2. 两个容器怎么通信的？

> Docker Compose 创建的网络里，**服务名就是 DNS**：Nginx 配置 `proxy_pass http://backend:8000`——backend 是 compose 里的服务名，Docker 内置 DNS 解析到后端容器 IP。宿主机访问用映射端口（8620→80）。

## Q3. volume 和 bind mount 什么区别？你怎么用的？

> volume 是 Docker 管理的存储（named volume），bind mount 是宿主机目录直接映射。我的用法：`maps_data` named volume 共享地图（后端写、Nginx 只读挂载 `:ro`）；`./chat_history:/app/chat_history` bind mount 持久化对话到宿主机（容器重建不丢）。

## Q4. Nginx 在你的架构里干了什么？

> 四件事：① 托管 Vue 构建产物（try_files 回退 index.html 支持 SPA 路由）；② 反代 /auth /chat 到 backend 容器；③ **SSE 关键配置**——proxy_buffering off（默认缓冲会破坏流式）+ read_timeout 300s；④ /maps/ 直接读共享卷静态出图，不经后端。

## Q5. 为什么地图走 Nginx 不走后端？

> 静态文件服务是 Nginx 的强项（sendfile 零拷贝、缓存头），后端 Python 进程不该被静态请求占用。实现：后端生成地图写共享卷 → Nginx 只读挂载同一卷 → /maps/ alias 直接出文件。本地开发没有 Nginx，Vite 代理 /maps 到后端的 StaticFiles——两端都配了，环境无关。

---

# 十二、测试（pytest/Mock）

> 📺 **B 站复习**：[2026 最强 pytest 项目实战（7月）](https://www.bilibili.com/video/BV1hTgh6NECF/) · [pytest 为什么要用 fixture（9月）](https://www.bilibili.com/video/BV1SytL6vE29/) · [mock 是什么怎么用（2875 5月）](https://www.bilibili.com/video/BV1TGReByEVb/) · [unittest 单元测试（3万）](https://www.bilibili.com/video/BV1bawPesEZL/)

## Q1. Mock 是什么？为什么需要？

> 用假对象替换真实依赖，让测试**只验证自己的代码逻辑**、不依赖外部服务（LLM/网络/真实库）。我的 API 测试 Mock 掉数据库和 Agent——测的是路由、校验、状态转换。边界划得很清楚：**外部依赖 Mock，内部逻辑真实**（并发测试用真 SqliteSaver、格式测试用官方序列化器）。

## Q2. fixture 是什么？autouse 是什么？

> fixture 是测试的前置准备（可注入给测试函数）。autouse=True 的 fixture **自动作用于所有测试**——我的 conftest 里有一个：每个测试前后重置 RAGFlow 客户端单例，防止某个测试的 mock 残留污染后续测试。

## Q3. dependency_overrides 是什么？

> FastAPI 的测试专用机制：`app.dependency_overrides[get_current_user] = lambda: fake_user` 一行替换依赖注入的真实实现。比 mock.patch 更精准——只影响依赖注入点。用完必须 `del app.dependency_overrides[...]` 清理，否则污染后续测试。

## Q4. 怎么测试流式接口？

> TestClient 发 POST /chat/stream，Mock 的 agent.stream 返回 `[(真 AIMessage, {})]`——**必须用真 AIMessage**，因为后端有 isinstance 检查，MagicMock 过不了。断言响应的 Content-Type 是 text/event-stream、响应体含 `data: {...}` 格式和 [DONE] 结尾。

## Q5. 怎么测并发安全？

> 真实 SqliteSaver + 假 LLM（FakeMessagesListChatModel，不联网）+ 20 线程并发 invoke。三个断言：无 database is locked 异常、不同 thread_id 状态互不串话、连接确实开了 WAL。假 LLM 让测试不依赖真实 API key，CI 也能跑。

---

# 十三、Git 与工程化

> 📺 **B 站复习**：[Git+Github 核心概念大串讲（技术爬爬虾 96.4万 5月）](https://www.bilibili.com/video/BV1ySLc6QEcB/) · [2026 最新 Git 教程（6358）](https://www.bilibili.com/video/BV19bPkzKEhq/) · [为什么每个开发者都要懂 CI/CD（6949）](https://www.bilibili.com/video/BV1jf7n6NEXV/) · [GitHub Actions 完全指南（8月）](https://www.bilibili.com/video/BV1STbv6xE8w/)

## Q1. 你的 Git 工作流是什么样的？

> 单分支（master）+ 小步提交：每个功能/修复一个 commit，message 按规范写（feat/fix/docs/refactor 前缀 + 正文列要点）。推送前本地跑全量测试。commit 历史本身就是开发日志——面试官翻 commit 能看到真实的开发过程。

## Q2. GitHub Actions 是什么？你怎么用的？

> GitHub 的自动化平台：仓库里放 .yml 配置，GitHub 在指定事件（push/PR/定时 cron）触发时在免费云服务器上执行命令。我的 CI 四个并行 job：Ruff lint → Python 3.10/3.11 矩阵测试+覆盖率 → 前端 type-check+build → Docker 双镜像构建验证。配了 concurrency 组（同分支新 push 取消旧跑）。公开仓库免费额度不限时。

## Q3. .gitignore 里都排除了什么？为什么？

> 敏感文件（.env 含 API key）、运行时产物（__pycache__、*.db、日志、chat_history、生成的地图 HTML）、大文件（node_modules、dist、12306 原始数据）、构建产物。原则：**源码进 Git，一切可再生的东西不进**。

---

# 附：高频"代码指认题"速查表

面试官指着代码最可能问的 15 个点，一句话答案：

| 指着什么 | 一句话答案 |
|---|---|
| `POST /chat/stream` | 传用户消息+会话ID，SSE 流式返回 LLM 回答 |
| `yield` | 生成器：产出一个 SSE 事件就暂停，实现逐 token 推送 |
| `_SENTINEL = object()` | 结束标记：替代 StopIteration（穿越 Future 会变 RuntimeError） |
| `run_in_executor` | 把同步阻塞代码扔线程池，保护事件循环 |
| `ClassVar[re.Pattern]` | 类常量标记：告诉 Pydantic 这不是字段（踩过 ModelPrivateAttr 坑） |
| `Depends(get_current_user)` | 依赖注入鉴权：解析 JWT 查库返回用户 |
| `?` 占位符 | SQL 参数化防注入，用户输入当数据不当代码 |
| `PRAGMA journal_mode=WAL` | SQLite 读写分离，多线程不互相阻塞 |
| `thread_id = user_{id}_{session_id}` | 双重隔离：用户间 + 会话间的对话记忆隔离 |
| `invoke(input=None)` | 从 checkpoint 断点继续，补完中断的工具执行 |
| `msgpack` | 二进制序列化：checkpoint 的存储格式，比 JSON 小且快 |
| `getReader()` | 前端拿 ReadableStream 逐块读 SSE，axios 做不到 |
| `TextDecoder({stream:true})` | 跨包缓冲不完整字节序列，防中文乱码 |
| `proxy_buffering off` | Nginx 不攒响应，SSE 实时到达浏览器 |
| `ClassVar` + 去掉 `_` | Pydantic 类常量的正确写法，让配置错误在类定义时就暴露 |
