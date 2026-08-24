# MediaFlow 业务验收场景

> 文档编号：MF-ACCEPT-001  
> 格式：Gherkin 风格，可转换为自动化 E2E

## Feature 1：龙珠动画重命名

```gherkin
Feature: 导入方括号命名的动画

  Background:
    Given 监听目录 "/inbox/anime" 已配置
    And 动画媒体库根目录为 "/media/anime"
    And 默认命名模板为 "{title} S{season:02}E{episode:02}"
    And 自动执行已关闭

  Scenario: 视频与简繁字幕同步重命名
    Given 目录中存在稳定文件
      | filename |
      | [DBD-Raws][Dragon Ball][001][1080P][BDRip][HEVC-10bit][FLACx2].mkv |
      | [DBD-Raws][Dragon Ball][001][1080P][BDRip][HEVC-10bit][FLACx2].sc.ass |
      | [DBD-Raws][Dragon Ball][001][1080P][BDRip][HEVC-10bit][FLACx2].tc.ass |
    When 用户扫描目录
    Then 系统解析标题为 "Dragon Ball"
    And 解析绝对集数为 1
    And 字幕语言分别为 "zh-CN" 和 "zh-TW"
    When 用户确认条目标题为 "龙珠"
    And 设置绝对集 1 映射为 S01E01
    And 生成操作计划
    Then 计划包含目标文件
      | filename |
      | 龙珠 S01E01.mkv |
      | 龙珠 S01E01.sc.ass |
      | 龙珠 S01E01.tc.ass |
    When 用户执行计划
    Then 三个目标文件存在
    And 三个源文件按 move 策略不存在
    And 任务文件状态为 FILES_COMPLETED 或 SUCCESS
    And 每个操作都有成功记录
```

## Feature 2：目标冲突保护

```gherkin
Scenario: 目标视频已存在
  Given 目标路径已存在 "龙珠 S01E01.mkv"
  And 源文件仍存在
  When 系统生成操作计划
  Then 任务进入 CONFLICT
  And 计划项错误码为 TARGET_FILE_EXISTS
  And 页面不能直接执行计划
  And 源文件不变
  And 目标文件不变
```

## Feature 3：解析分辨率

```gherkin
Scenario Outline: 分辨率不得识别为绝对集数
  Given 文件名为 <filename>
  When 解析文件名
  Then 绝对集数应为 <episode>
  And 分辨率应为 <resolution>

  Examples:
    | filename | episode | resolution |
    | [Group][Show][001][1080P].mkv | 1 | 1080P |
    | [Group][Show][2160P].mkv | null | 2160P |
    | Show.S01E01.2160p.mkv | null | 2160p |
```

## Feature 4：元数据歧义

```gherkin
Scenario: 候选领先差不足
  Given 搜索关键词为 "Monster"
  And 第一候选得分为 88
  And 第二候选得分为 86
  When 搜索完成
  Then 系统不得自动选择
  And 任务进入 WAITING_CONFIRMATION
  And 确认原因为 MATCH_AMBIGUOUS
  And 页面显示两个候选及评分明细
```

## Feature 5：目录绑定

```gherkin
Scenario: 已绑定目录复用条目
  Given 目录 "/inbox/anime/Dragon Ball" 已绑定 Bangumi 条目 253
  When 该目录新增第 2 集并扫描
  Then 系统优先使用绑定条目
  And 不因同名候选自动切换到其他条目
  And 如果绑定条目获取失败，任务显示可重试错误而不是选择其他作品
```

## Feature 6：绝对集映射

```gherkin
Scenario: 批量顺序映射
  Given 任务包含绝对集 1, 2, 3, 4
  When 用户设置目标季为 1 且起始集为 1
  Then 映射结果为
    | source | season | episode |
    | 1 | 1 | 1 |
    | 2 | 1 | 2 |
    | 3 | 1 | 3 |
    | 4 | 1 | 4 |
  And 映射无目标冲突
```

```gherkin
Scenario: 特别篇目标冲突
  Given SP01 和 OVA01 都被映射到 S00E01
  When 校验映射
  Then 校验失败并返回 MAPPING_COLLISION
  And 不生成可执行计划
```

## Feature 7：字幕关联

```gherkin
Scenario: 字幕基础名和集号一致
  Given 视频 "Show.S01E01.mkv"
  And 字幕 "Show.S01E01.zh-CN.ass"
  When 计算字幕关联
  Then 字幕自动关联视频
  And 语言为 zh-CN
```

```gherkin
Scenario: 基础名相似但集号冲突
  Given 视频 "Show.S01E01.mkv"
  And 字幕 "Show.S01E02.zh-CN.ass"
  When 计算字幕关联
  Then 字幕不得关联该视频
  And 字幕标记为孤立或候选缺失
```

## Feature 8：硬链接保种

```gherkin
Scenario: 同一文件系统创建硬链接
  Given 源和目标父目录设备 ID 相同
  And 目标不存在
  When 使用 hardlink 执行计划
  Then 源文件存在
  And 目标文件存在
  And 源和目标 inode/device 相同
  And 回滚时只删除目标目录项
```

```gherkin
Scenario: 跨设备硬链接
  Given 源和目标设备 ID 不同
  When 预检 hardlink 计划
  Then 计划冲突代码为 HARDLINK_CROSS_DEVICE_NOT_SUPPORTED
  And 不执行任何文件修改
```

## Feature 9：跨设备移动

```gherkin
Scenario: 复制校验失败时保留源
  Given move 操作需要跨设备
  And 复制后的目标临时文件校验失败
  When 执行操作
  Then 源文件仍存在
  And 最终目标文件不存在
  And 操作记录状态为 FAILED
  And 错误码为 COPY_VERIFY_FAILED
```

```gherkin
Scenario: 复制成功后删除源
  Given move 操作需要跨设备
  When 临时复制、校验和最终改名成功
  Then 系统才删除源文件
  And 最终目标存在且校验一致
```

## Feature 10：计划失效

```gherkin
Scenario: 源文件在预览后发生变化
  Given 用户已生成有效计划
  When 源文件大小或 mtime 改变
  And 用户提交执行
  Then API 返回 409
  And 错误码为 SOURCE_FILE_CHANGED 或 PLAN_PREFLIGHT_FAILED
  And 不执行文件修改
```

## Feature 11：重复执行幂等

```gherkin
Scenario: 同一执行请求重复提交
  Given 计划已经执行成功
  When 客户端用相同 Idempotency-Key 再次提交执行
  Then 返回第一次执行结果
  And 不创建第二个目标文件
  And 不新增重复成功操作记录
```

## Feature 12：回滚

```gherkin
Scenario: 成功 move 可回滚
  Given move 操作成功且目标未被修改
  When 用户确认回滚
  Then 目标文件移动回原路径
  And 目标文件不存在
  And 操作记录 rollback_status 为 SUCCESS
  And 任务状态为 ROLLED_BACK
```

```gherkin
Scenario: 目标被修改时禁止默认回滚
  Given 文件操作成功后目标内容发生变化
  When 用户以 force=false 请求回滚
  Then 回滚停止
  And 错误说明目标已变化
  And 不删除或移动该目标
  And 任务状态为 ROLLBACK_FAILED 或需要人工处理
```

## Feature 13：崩溃恢复

```gherkin
Scenario: rename 完成但数据库未标记成功
  Given worker 在 rename 完成后、数据库提交前崩溃
  And 源不存在
  And 目标存在且校验一致
  When 服务重启并执行恢复对账
  Then 系统识别操作已经成功
  And 不再次执行 rename
  And 任务可以继续处理下一项
```

```gherkin
Scenario: 源和目标同时存在且状态不确定
  Given move 操作记录为 RUNNING
  And 源与目标都存在
  When 服务重启
  Then 任务进入 RECOVERY_REQUIRED
  And 系统不自动删除任何文件
```

## Feature 14：Emby 失败隔离

```gherkin
Scenario: Emby 离线
  Given 文件操作全部成功
  And Emby 服务器不可连接
  When 系统执行刷新任务并耗尽自动重试
  Then 媒体文件保持目标状态
  And 任务状态为 FILES_COMPLETED_EMBY_FAILED
  And 用户可以只重试 Emby 刷新
  And 系统不得重新执行文件计划
```

## Feature 15：路径安全

```gherkin
Scenario: 目标路径穿越
  Given 模板或用户输入生成目标 "../../etc/passwd"
  When 系统构建或预检计划
  Then 返回 PATH_OUTSIDE_ALLOWED_ROOT
  And 不创建目录或文件
```

```gherkin
Scenario: 符号链接父目录跳出目标根
  Given 目标根内存在指向外部目录的符号链接
  When 目标路径经过该链接
  Then realpath 校验失败
  And 不执行文件操作
```

## Feature 16：配置与密钥

```gherkin
Scenario: 读取集成配置不返回 Token
  Given TMDB Token 已配置
  When 管理员读取集成配置
  Then 响应仅显示 configured=true 和掩码
  And 不包含完整 Token
  And 日志中不包含完整 Token
```

## Feature 17：网络挂载稳定性

```gherkin
Scenario: 文件在稳定窗口内继续增长
  Given 文件第一次大小为 1 GB
  And 30 秒后大小变为 2 GB
  When 稳定性检查运行
  Then 文件保持 WAITING_STABLE
  And 不创建可执行计划
```

## Feature 18：电影和电视剧基础命名

```gherkin
Scenario: 电影命名
  Given 文件 "Oppenheimer.2023.2160p.mkv"
  And 用户确认条目 "奥本海默" 年份 2023
  When 生成计划
  Then 目标路径包含 "奥本海默 (2023)/奥本海默 (2023).mkv"
```

```gherkin
Scenario: 电视剧命名
  Given 文件 "Breaking.Bad.S02E03.1080p.mkv"
  And 用户确认条目 "绝命毒师" 年份 2008
  When 生成计划
  Then 目标路径包含 "绝命毒师 (2008)/Season 02/绝命毒师 S02E03.mkv"
```

## 19. 验收执行记录

每次 RC 验收记录：

- 版本和 Git SHA；
- Docker 镜像 digest；
- NAS/文件系统；
- 场景通过/失败；
- 文件操作前后哈希；
- 数据库备份；
- 未解决风险和发布决定。
