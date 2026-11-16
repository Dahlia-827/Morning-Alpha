Morning Alpha · 金融早餐

使用方法：
1. 确认电脑已安装 Python 3。
2. 双击“启动晨报.bat”。
3. 浏览器打开 http://localhost:8765

程序会抓取公开 RSS，并缓存 6 小时；打开网页时会自动读取最新内容。
如果某个资讯源暂时不可用，页面仍会显示其他来源的内容。

说明：
- 当前版本适合个人本地使用。
- 资讯只保留标题、摘要和原文链接，不复制新闻全文。
- 内容来自公开资讯源，重要信息请回到原文或官方渠道核实。

GitHub Pages 公网版：
1. 将 outputs 文件夹中的全部内容上传到 GitHub 仓库根目录。
2. 在仓库 Settings > Pages > Build and deployment > Source 中选择 GitHub Actions。
3. 在 Actions 页面手动运行一次“Update and publish Morning Alpha”。
4. 后续 GitHub Actions 会按计划更新新闻缓存并重新发布网页。

来源标记：
- 国内可访问：优先使用中国大陆官方或主流财经来源。
- 可能需代理：海外来源，点击前请留意网络环境。

微博等平台建议只接入公开官方账号或公开内容，不抓取登录后内容，也不复制全文。
