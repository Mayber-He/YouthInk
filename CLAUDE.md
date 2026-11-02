# YouthInk 项目约定

> 完整开发规范见 [docs/development.md](docs/development.md)，本文件只记录 Claude Code 必须遵守的规则。

## Git 提交信息

所有提交必须遵循 Conventional Commits 中文规范：

```text
type(scope): 中文描述
```

- **type**（必须）：小写英文，见下方允许列表。
- **scope**（必须）：小写英文，使用本次改动所属的功能模块，不使用 `T1`、`T20` 之类的任务编号。
- **中文描述**（必须）：动词开头，简明扼要，不加句号；必须是中文，不得写英文描述。
- **正文**（可选）：与标题之间空一行，用 `-` 列表说明细节；正文同样使用中文。

### 允许的 type

| Type | 用途 |
|---|---|
| `feat` | 新增功能或业务逻辑 |
| `fix` | 修复缺陷或 Bug |
| `refactor` | 重构，既不新增功能也不修复缺陷 |
| `docs` | 仅文档变更 |
| `style` | 代码格式调整，不影响逻辑 |
| `perf` | 性能优化 |
| `test` | 新增或修改测试 |
| `build` | 构建系统、打包或依赖调整 |
| `chore` | 启动脚本、仓库配置等杂项 |
| `revert` | 撤销此前的提交 |

### 常用 scope

- **生成链路**：`generation`、`context`、`prompt`、`outline`、`chapter`
- **数据与记忆**：`memory`、`rag`、`constraint`
- **质量审查**：`consistency`
- **前端**：`frontend`
- **工程**：`repo`、`build`、`docs`（配合 `plan` / `dev` 等子域）
- **应用级**：`app`

新增模块时使用该模块的目录名或功能名作为 scope，保持全仓库一致。

### 示例

```text
feat(generation): 场景生成后做确定性重复检测并落库
fix(memory): 重新定稿时原子替换记忆并阻止过期条目复活
fix(context): 衔接证据只校验在用字段并降级不注入
refactor(prompt): 精简并重排写作提示词并以核心设定替代全书梗概
chore(repo): 忽略 loop 文件夹
```
