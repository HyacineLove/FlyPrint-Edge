# PRP PDF 文件协议

## API

- `GET /api/v1/files?page=1&page_size=20`
  - `Authorization: Bearer <PRP Token>`
  - `1 <= page_size <= 50`
  - 返回 `items`、`page`、`page_size`、`total`
- `GET /api/v1/files/{id}/content`
  - Token 只进入 Authorization 请求头
  - 必须返回 `Content-Type`、`Content-Length`、`Content-Disposition` 和 `X-Content-SHA256`

文件项字段固定为 `id`、`name`、`media_type`、`size`、`sha256`、`created_at`、`expires_at`、`last_downloaded_at`。响应中出现访问凭证或未知字段时，Edge 拒绝该响应。

## Edge 下载与预览

1. `PRPClient` 校验基础 URL，不允许 userinfo、query 或 fragment。
2. 下载写入目标文件同目录的 `.part`，流式执行 50 MiB 本地上限、长度和 SHA-256 校验。
3. 全部校验通过后使用原子替换发布本地源文件。
4. `PRPFileSelectionManager` 独占本地路径；公开会话只保存 `source_origin=prp` 和文件公开元数据。
5. `/api/preview` 对 PRP 源使用会话绑定的本地路径；Cloud 与第三方源继续使用既有下载分支，不进行失败回退或换源。
6. 标准 PDF 建立后释放源路径记录；换选、退出和失败会清理 `.part` 与未确认源文件。

PDF 检查点不开放打印。`/api/print` 对 `source_origin=prp` 在 Cloud 或 IPP 调用前返回 `print_not_available_in_slice`。

## 验证

```powershell
node --experimental-default-type=module --test tests/js/identity-session.test.mjs tests/js/prp-files.test.mjs
py -m unittest discover -s tests -p "test_*.py"
```

当前结果：JS 4 项通过；Python 231 项通过，1 项跳过。浏览器可见的登录、列表、选择和预览仍作为 PDF 检查点的最后人工验收项。
