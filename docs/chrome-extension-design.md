# Jable Downloader Chrome Extension Design Doc

## 1. 项目目标

构建一个基于 Chrome Extension Manifest V3 的纯前端插件，用于在支持的视频页面中：

- 识别当前页面是否可下载
- 提取视频标题、封面、m3u8 地址
- 下载 m3u8、key、ts 分片
- 在前端完成 AES 解密、分片合并
- 导出 mp4 文件
- 提供任务列表、进度显示、失败重试、历史记录

约束：

- 不依赖任何 Python/Node 后端服务
- 所有逻辑运行在浏览器扩展环境中
- 以 Chrome 为主目标浏览器
- 优先支持 `jable.tv`
- 代码结构必须可扩展，未来支持更多站点

## 2. 分期目标

### Phase 1: 最小可行版本

目标：完成“当前页面可下载”的最短闭环。

功能范围：

- 识别当前 tab 是否是支持页面
- 提取：
  - `title`
  - `coverUrl`
  - `m3u8Url`
  - `pageUrl`
  - `videoId`
- 在 popup 中展示当前视频信息
- 点击下载后：
  - 拉取 m3u8
  - 解析 ts 分片
  - 获取 key 和 iv
  - 顺序下载 ts
  - 前端解密
  - 合并为 Blob
  - 触发浏览器下载 mp4
- 展示下载进度
- 下载失败后显示错误信息
- 支持取消当前任务
- 使用本地存储保存最近任务记录

不做：

- 断点续传
- 后台长期稳定下载
- 多任务并发下载
- 浏览器关闭后恢复
- 复杂的任务调度
- 多站点支持

### Phase 2: 增强版本

目标：把插件升级为完整下载器。

功能范围：

- 多任务队列
- 并发分片下载
- 失败重试
- 暂停 / 恢复
- 历史任务持久化
- 下载配置项
- 更多站点 provider
- 更可靠的大文件处理
- 更强的错误恢复策略

## 3. 技术栈

- 标准：Chrome Extension Manifest V3
- 语言：TypeScript
- 构建工具：Vite
- UI：React
- 样式：CSS Modules 或普通 CSS
- 状态管理：Zustand 或轻量自定义 store
- 存储：
  - `chrome.storage.local` 用于轻量状态
  - `IndexedDB` 用于任务元数据和中间数据
- m3u8 解析：
  - 优先使用 `m3u8-parser`
  - 若不引库，自己实现简化 parser
- AES 解密：
  - 优先 Web Crypto API
  - 必要时引入轻量 AES-CBC 实现
- 文件导出：
  - `chrome.downloads.download`
  - 文件来源使用 Blob URL

## 4. 总体架构

插件由四层组成：

### 4.1 UI Layer

负责 popup 页面和 options 页面。

职责：

- 展示当前页面识别结果
- 展示任务列表
- 展示进度、状态、错误
- 接收用户点击操作
- 调用 background service worker

### 4.2 Content Script Layer

注入到页面中，负责页面信息提取。

职责：

- 判断是否为支持页面
- 从 DOM 和页面源码中提取 metadata
- 必要时监听页面动态内容
- 向 background 返回结构化数据

### 4.3 Background Layer

作为核心编排器。

职责：

- 接收 popup 发起的下载命令
- 调用 downloader core
- 管理任务状态
- 将进度广播给 popup
- 保存任务记录

### 4.4 Core Layer

纯逻辑模块，不依赖 DOM。

职责：

- provider 解析结果建模
- m3u8 下载和解析
- key 获取
- ts 下载
- AES 解密
- Blob 合并
- 进度事件回调

## 5. 推荐目录结构

```text
chrome-jable-downloader/
  public/
    manifest.json
    icons/
  src/
    background/
      index.ts
      taskManager.ts
      messageBus.ts
    content/
      index.ts
      extractors/
        jable.ts
    core/
      downloader/
        downloadTask.ts
        playlistLoader.ts
        segmentFetcher.ts
        decryptor.ts
        merger.ts
      provider/
        base.ts
        jableProvider.ts
      storage/
        taskRepo.ts
        settingsRepo.ts
      models/
        task.ts
        video.ts
        playlist.ts
        message.ts
      utils/
        http.ts
        blob.ts
        crypto.ts
        url.ts
        logger.ts
    popup/
      main.tsx
      App.tsx
      components/
        CurrentVideoCard.tsx
        TaskList.tsx
        TaskRow.tsx
        ProgressBar.tsx
      store/
        popupStore.ts
    options/
      main.tsx
      App.tsx
    styles/
      popup.css
      common.css
```

## 6. Manifest 设计

### 6.1 manifest.json 要求

必须包含：

- `manifest_version: 3`
- `name`
- `version`
- `action.default_popup`
- `background.service_worker`
- `permissions`
- `host_permissions`
- `content_scripts`

### 6.2 建议权限

```json
{
  "permissions": [
    "storage",
    "downloads",
    "tabs",
    "scripting",
    "activeTab"
  ],
  "host_permissions": [
    "*://*.jable.tv/*",
    "*://*/*.m3u8*",
    "*://*/*.ts*"
  ]
}
```

说明：

- `downloads`：保存 mp4
- `storage`：保存任务和设置
- `tabs` / `activeTab`：识别当前页
- `host_permissions`：用于拉取 m3u8 / ts / key

## 7. 核心模块设计

### 7.1 数据模型

#### VideoMetadata

```ts
type VideoMetadata = {
  site: "jable"
  pageUrl: string
  videoId: string
  title: string
  coverUrl?: string
  m3u8Url: string
}
```

#### DownloadTask

```ts
type DownloadTaskStatus =
  | "idle"
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "canceled"

type DownloadTask = {
  id: string
  videoId: string
  title: string
  pageUrl: string
  coverUrl?: string
  m3u8Url: string
  status: DownloadTaskStatus
  progress: number
  totalSegments?: number
  downloadedSegments?: number
  error?: string
  fileName?: string
  createdAt: number
  updatedAt: number
}
```

#### PlaylistInfo

```ts
type PlaylistInfo = {
  playlistUrl: string
  segmentUrls: string[]
  keyUrl?: string
  iv?: string
}
```

### 7.2 Provider 抽象

#### Provider 接口

```ts
interface VideoProvider {
  canHandle(url: string): boolean
  extractFromDocument(doc: Document, pageUrl: string): Promise<VideoMetadata | null>
}
```

#### JableProvider

职责：

- 判断是否匹配 `jable.tv/videos/...`
- 从页面中获取：
  - `og:title`
  - `og:image`
  - `m3u8 url`
- 生成 `videoId`

提取策略：

1. 先取 `meta[property="og:title"]`
2. 再取 `meta[property="og:image"]`
3. 从 HTML 或 script 文本中用正则找 `.m3u8`
4. 若找不到，返回 null

注意：

- provider 仅负责“提取元数据”
- 不负责下载

### 7.3 Content Script 设计

职责：

- 注入页面后判断当前页面是否支持
- 调用 `JableProvider.extractFromDocument`
- 监听来自 background 的消息
- 返回 metadata

消息协议：

#### 请求

```ts
type ExtractVideoRequest = {
  type: "EXTRACT_VIDEO"
}
```

#### 响应

```ts
type ExtractVideoResponse = {
  type: "EXTRACT_VIDEO_RESULT"
  success: boolean
  data?: VideoMetadata
  error?: string
}
```

### 7.4 Background Task Manager

职责：

- 接收 popup “开始下载”
- 维护内存任务表
- 调 downloader core
- 把进度同步给 popup
- 把最终结果写入 storage

接口：

```ts
class TaskManager {
  createTask(metadata: VideoMetadata): Promise<DownloadTask>
  startTask(taskId: string): Promise<void>
  cancelTask(taskId: string): Promise<void>
  getTasks(): Promise<DownloadTask[]>
  subscribe(listener: (tasks: DownloadTask[]) => void): () => void
}
```

Phase 1 限制：

- 同一时间只允许一个 running task
- 若已有 running task，新任务进入 pending 或直接提示

Phase 2 可扩展：

- 多任务队列
- 并发数配置

### 7.5 Downloader Core

#### playlistLoader.ts

职责：

- 拉取 m3u8 文本
- 解析 segment URL 列表
- 解析 key URL 和 iv

输入：

- `m3u8Url`

输出：

- `PlaylistInfo`

#### segmentFetcher.ts

职责：

- 顺序下载 segment
- 返回 `ArrayBuffer`

输入：

- segment url
- headers / credentials policy

输出：

- `ArrayBuffer`

#### decryptor.ts

职责：

- AES-CBC 解密 ts 内容
- 支持无加密和有加密两种路径

输入：

- encrypted bytes
- key bytes
- iv bytes

输出：

- decrypted bytes

#### merger.ts

职责：

- 将多个 Uint8Array 合并为 Blob
- 生成 Blob URL

输入：

- 分片数组

输出：

- `Blob`

#### downloadTask.ts

职责：

- 编排整个下载过程
- 发进度事件

伪流程：

```ts
1. load playlist
2. if encrypted:
   2.1 fetch key
3. for each segment:
   3.1 fetch segment
   3.2 decrypt if needed
   3.3 append to chunks
   3.4 emit progress
4. merge chunks to Blob
5. trigger chrome.downloads.download
6. emit success
```

## 8. 下载策略设计

### 8.1 Phase 1

- 单任务
- 单线程顺序下载
- 全量内存合并
- 完成后一次性导出

优点：

- 实现简单
- 容易调试

缺点：

- 大文件占内存
- 下载速度一般

### 8.2 Phase 2

- 支持并发下载 ts
- 控制最大并发数
- 使用分段缓存
- 尝试 IndexedDB/OPFS 临时存储
- 支持失败重试与恢复

## 9. 状态持久化设计

### 9.1 Phase 1

使用 `chrome.storage.local` 保存：

- 最近任务列表
- 任务状态摘要
- 用户设置

不保存：

- 已下载的 segment 二进制
- 半成品视频内容

### 9.2 Phase 2

使用 IndexedDB 保存：

- task metadata
- playlist info
- segment progress
- key metadata
- 错误日志
- 可恢复下载上下文

## 10. UI 设计

### 10.1 Popup 页面结构

#### 区块 1：当前页面

显示：

- 是否识别为支持站点
- 标题
- 封面
- m3u8 是否提取成功
- “下载当前视频”按钮

#### 区块 2：任务列表

每个任务显示：

- 标题
- 状态
- 进度条
- 百分比
- 错误信息
- 操作按钮：
  - 取消
  - 重试
  - 删除记录

#### 区块 3：设置入口

- 默认文件名规则
- 并发数（Phase 2）
- 调试模式

## 11. 文件命名规则

默认命名：

```text
{videoId}.mp4
```

可配置扩展：

```text
{title}.mp4
{videoId}-{title}.mp4
```

文件名清洗规则：

- 去除非法字符 `/ \\ : * ? " < > |`
- 限制最大长度
- 空标题时回退到 `videoId`

## 12. 错误处理策略

错误分类：

- `UNSUPPORTED_PAGE`
- `METADATA_NOT_FOUND`
- `M3U8_FETCH_FAILED`
- `PLAYLIST_PARSE_FAILED`
- `KEY_FETCH_FAILED`
- `SEGMENT_FETCH_FAILED`
- `DECRYPT_FAILED`
- `MERGE_FAILED`
- `DOWNLOAD_SAVE_FAILED`
- `TASK_CANCELED`

要求：

- 所有错误必须可映射成用户可读消息
- popup 中显示短错误
- debug 模式可查看详细错误

## 13. 与当前 Python 项目的映射关系

当前 Python 逻辑与插件模块映射：

- `Jtask._run()`
  -> `content provider + core/downloadTask`
- `save_metainfo()`
  -> `taskRepo.saveTask()`
- `load_history()`
  -> `taskRepo.listTasks()`
- `_get_m3u8()`
  -> `playlistLoader + segmentFetcher + decryptor + merger`
- `TaskInfo / DownloadInfo`
  -> `models/task.ts + models/video.ts + models/playlist.ts`

目标不是复刻文件结构，而是复刻能力边界。

## 14. Phase 1 开发任务拆分

### Task 1: 工程初始化

产出：

- Vite + TypeScript Chrome Extension 项目
- manifest
- popup
- background
- content script 通路打通

### Task 2: Jable 页面识别与 metadata 提取

产出：

- `JableProvider`
- content script 能返回 `VideoMetadata`

### Task 3: Popup 展示当前页面信息

产出：

- 显示标题、封面、下载按钮
- 未识别页面时显示空状态

### Task 4: m3u8 下载与解析

产出：

- 能获取 segment 列表
- 能获取 key 和 iv

### Task 5: ts 下载、解密、合并

产出：

- 生成 mp4 Blob
- 触发下载

### Task 6: 单任务状态管理

产出：

- pending/running/success/failed/canceled
- popup 中可见进度

### Task 7: 最近任务历史

产出：

- `chrome.storage.local` 保存最近任务
- popup 重开后仍可看到记录

## 15. Phase 2 开发任务拆分

### Task 1: 多任务队列

### Task 2: 并发下载

### Task 3: 失败重试

### Task 4: 暂停/恢复

### Task 5: IndexedDB 持久化

### Task 6: 更强的 provider 抽象

### Task 7: 大文件优化

### Task 8: 调试面板和日志系统

## 16. 代码生成约束

以下规则是给代码生成器的硬约束：

- 必须使用 TypeScript
- 必须使用 Manifest V3
- 必须按模块拆分，不允许把所有逻辑堆在一个文件
- provider、downloader、storage、UI 必须分层
- 业务逻辑尽量放在 `src/core`
- `content script` 不承担下载逻辑
- `popup` 不承担下载逻辑
- `background` 作为任务编排中心
- 所有消息协议必须有明确类型定义
- 所有 task 状态更新必须通过统一 task manager
- 错误必须结构化，不允许只 `console.error`
- 代码要保留扩展多站点能力

## 17. 给 Vibe Code 的生成提示词

下面这段可以直接给代码生成器：

```text
请生成一个基于 Chrome Extension Manifest V3 的 TypeScript 项目，用于实现一个纯前端视频下载插件，目标站点先支持 jable.tv。

要求：
1. 不依赖任何后端服务。
2. 使用 Vite + TypeScript。
3. 项目结构必须分层：
   - src/content
   - src/background
   - src/core/provider
   - src/core/downloader
   - src/core/storage
   - src/core/models
   - src/popup
4. content script 负责提取当前页面的视频 metadata：
   - title
   - coverUrl
   - m3u8Url
   - videoId
   - pageUrl
5. background 负责管理下载任务。
6. popup 负责展示当前页面信息和任务列表。
7. Phase 1 先只实现：
   - 单任务下载
   - 顺序下载 ts
   - AES-CBC 解密
   - 合并为 Blob
   - 触发浏览器下载
   - 进度显示
   - 取消任务
   - 最近任务记录保存在 chrome.storage.local
8. 定义清晰的 TypeScript 类型：
   - VideoMetadata
   - DownloadTask
   - PlaylistInfo
   - Message types
9. 提供一个 JableProvider：
   - 从页面 meta 标签提取 title 和 cover
   - 从页面源码中提取 m3u8 地址
10. 代码需可扩展到多站点 provider。
11. UI 简洁清晰，popup 中至少包括：
   - 当前视频卡片
   - 下载按钮
   - 任务列表
   - 进度条
   - 错误提示
12. 所有模块都需要有最小可运行实现，不要只输出接口定义。
13. 优先保证代码结构清晰，再保证功能完整。
```

## 18. 下一步建议

最合理的下一步不是直接生成“完整版”，而是先让代码生成器产出 Phase 1 最小可运行工程：

- manifest
- popup
- content script
- background
- `JableProvider`
- `TaskManager`
- 单任务下载闭环

这一步通了，再进入第二轮生成，补 Phase 2。
