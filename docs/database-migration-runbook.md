# 数据库迁移与现有库接管

## 2026-10-07 的修复

新迁移版本：`20261007_schema_alignment`，前置版本为 `20260904_free_posts`。

- 历史迁移对重复定义的字段先检查存在性，修复空库升级时的 Duplicate column 错误；最终对齐迁移再校验字段类型与约束。
- 新版本使用固定的 `backend/alembic/schema_20261007.py` 快照，避免未来模型变动改变已有迁移含义。
- 补齐当前模型所需字段、表、索引、唯一约束及外键，修正已核查的 NTRP 类型、计数器类型和可空性。
- 保留历史多余字段、现有服务端默认值和字符集/排序规则，不删除业务数据。
- 变更前统一检查 NULL、NTRP 格式、唯一索引重复值和外键孤立记录；未审查过的类型转换直接报错。

## 现有无版本记录的线上库

当前数据库有 15 张业务表，但没有 `alembic_version`。不要直接 `upgrade head`，也不要直接 `stamp head`。

接管脚本默认只读。它要求显式提供 `DATABASE_URL`，检查全部预期表、字段和主键，使用固定快照核对结构。

在携带**本次代码**、配置好环境变量的后端容器中，工作目录为 `/app`：

```bash
python scripts/adopt_legacy_database.py
```

当新备份和恢复演练完成，应用写入与 Celery 任务已暂停后，执行接管：

```bash
python scripts/adopt_legacy_database.py --apply
python -m alembic current
python -m alembic upgrade head
```

脚本先校验全部计划，再执行对齐；对齐后重新核对字段/约束，成功才登记 `20261007_schema_alignment`。如果已有 `alembic_version` 表，脚本拒绝接管，转用正常迁移路径。

MySQL DDL 不可依赖事务整体回滚。失败可能已完成部分结构变更，但不会登记成功版本；保留报错及备份，排查后可重新检查/执行接管。不要通过强行 stamp 绕过失败。并发写入可能在预检查后引入约束冲突，因此实际迁移需要停写维护窗口。

新对齐迁移拒绝自动 downgrade，因为无法保证还原原始结构。应用镜像回滚需要检查旧版本与新结构的兼容性；数据库恢复必须使用经过验证的备份并处理备份之后的新写入。

实现参考 Alembic 官方的 [现有结构版本登记流程](https://alembic.sqlalchemy.org/en/latest/cookbook.html) 和 [MySQL alter_column 参数要求](https://alembic.sqlalchemy.org/en/latest/ops.html)：结构确认完成后才登记版本，修改字段时保留既有类型、默认值和可空性信息。

## 已有版本记录与空库

配置 `DATABASE_URL=mysql+asyncmy://...` 后，从后端目录执行：

```bash
python -m alembic upgrade head
```

空库会执行完整历史迁移链和最终对齐，得到当前 15 张业务表及 `alembic_version`。已有记录的库继续从原版本升级。对齐涉及数据库反射和数据校验，需要在线连接；不支持离线 `--sql` 生成。

## 隔离演练

集成测试：`backend/tests/test_migration_integration.py`。

需要三套专用数据库，名称必须以 `playnow_migration_` 开头：

- `MIGRATION_EMPTY_DATABASE_URL`：空库。
- `MIGRATION_LEGACY_DATABASE_URL`：从已验证线上备份恢复的库。
- `MIGRATION_REJECT_DATABASE_URL`：独立恢复副本，用于插入非法数据测试。当前测试夹具需要 users、clubs、booking_orders 中已有样例记录。

用只拥有这三套临时库权限的测试账户执行；环境变量通过权限 600 的临时环境文件传入容器。测试 URL 可以使用 `mysql+pymysql`，应用 `DATABASE_URL` 使用 `mysql+asyncmy`。

```bash
python -m unittest discover -s tests -p test_migration_integration.py -v
```

没有提供三个 URL 时，测试会跳过。切勿把线上数据备份或包含凭据的环境文件提交到仓库。

演练覆盖：

1. 空库从 base 升到 head，再次 upgrade 保持成功。
2. 恢复副本的只读预检不写入版本表、不改变数据。
3. 接管后字段、类型、可空性、索引、唯一约束和外键与当前模型一致。
4. 全表数据哈希一致，仅规范化 NTRP 字符串与 Decimal 的表示差异；历史多余字段仍保留。
5. 非法 NTRP、NULL 和重复结算单号在执行 DDL/登记版本前被拒绝。

2026-10-07 已在原服务器使用 3 套独立临时库、专用账户和一次性容器完成演练；临时库、账户、容器和代码目录均已清理。生产数据库只执行了只读预检，没有执行接管或迁移。

核查备份目录：`/var/backups/playnow/20261007-113859`，内有 `migration-rehearsal.log` 与 `migration-rehearsal.json`，权限仅允许 root 读取。实际发布前应重新备份及检查，不能把这次快照视为之后发布时的最新数据。
